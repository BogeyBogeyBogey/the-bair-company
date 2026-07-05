#!/usr/bin/env python3
"""
Execute or dry-run HomePilot CRM/webhook sync batches.

The integration pack produces CRM CSV and webhook JSONL handoff artifacts. This
runner turns the webhook batch into an operator-controlled sync report with
idempotency, retry accounting, dead-letter output, and secret-safe evidence. It
reads customer-specific webhook URLs and API keys only from the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


WEBHOOK_URL_ENV = "HOMEPILOT_CRM_WEBHOOK_URL"
API_KEY_ENV = "HOMEPILOT_CRM_API_KEY"
SECRET_PATTERNS = {
    "api_key_assignment": re.compile(r"api[_-]?key\s*[:=]\s*['\"][^'\"]+", re.IGNORECASE),
    "bearer_token": re.compile(r"bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
Sender = Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _path_from_manifest(manifest: dict[str, Any], key: str) -> Path | None:
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    value = paths.get(key)
    return Path(value) if value else None


def _webhook_host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc
    except ValueError:
        return ""


def _headers(api_key: str, idempotency_key: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-HomePilot-Idempotency-Key": idempotency_key,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def default_sender(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"status_code": response.status, "body": body[:500]}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"status_code": exc.code, "body": body[:500], "error": f"http_{exc.code}"}
    except urllib.error.URLError as exc:
        return {"status_code": 0, "body": "", "error": str(exc.reason)[:300]}


def _scan_files(paths: list[Path]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(body):
                findings.append({"file": str(path), "pattern": label})
    return findings


def _validate_payloads(payloads: list[dict[str, Any]]) -> list[str]:
    failures = []
    keys = []
    for index, payload in enumerate(payloads, start=1):
        key = str(payload.get("idempotency_key") or "")
        if not key:
            failures.append(f"Payload {index} is missing idempotency_key.")
        keys.append(key)
        if payload.get("event_type") != "homepilot.opportunity.upsert":
            failures.append(f"Payload {index} has unexpected event_type {payload.get('event_type')!r}.")
        guardrails = payload.get("guardrails") if isinstance(payload.get("guardrails"), dict) else {}
        if guardrails.get("tenant_scoped") is not True or guardrails.get("module_scoped") is not True:
            failures.append(f"Payload {index} is missing tenant/module guardrails.")
    if len(keys) != len(set(keys)):
        failures.append("Duplicate webhook idempotency_key values detected.")
    return failures


def _dry_run_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "idempotency_key": payload.get("idempotency_key"),
        "event_type": payload.get("event_type"),
        "status": "dry_run",
        "attempts": 0,
        "http_status": None,
        "error": "",
    }


def _send_with_retries(
    payload: dict[str, Any],
    webhook_url: str,
    api_key: str,
    sender: Sender,
    max_attempts: int,
    timeout: int,
) -> dict[str, Any]:
    idempotency_key = str(payload.get("idempotency_key") or "")
    headers = _headers(api_key, idempotency_key)
    last: dict[str, Any] = {}
    for attempt in range(1, max_attempts + 1):
        last = sender(webhook_url, payload, headers, timeout)
        status_code = int(last.get("status_code") or 0)
        if 200 <= status_code < 300:
            return {
                "idempotency_key": idempotency_key,
                "event_type": payload.get("event_type"),
                "status": "sent",
                "attempts": attempt,
                "http_status": status_code,
                "error": "",
            }
        if status_code and status_code < 500:
            break
    return {
        "idempotency_key": idempotency_key,
        "event_type": payload.get("event_type"),
        "status": "failed",
        "attempts": min(max_attempts, max(1, int(last.get("attempts") or max_attempts))),
        "http_status": int(last.get("status_code") or 0) or None,
        "error": str(last.get("error") or last.get("body") or "delivery_failed")[:300],
    }


def render_runbook(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot CRM/Webhook Sync Report",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Mode: {report['mode']}",
        f"Webhook host: {report['credentials']['webhook_host'] or 'not configured'}",
        "",
        "## Summary",
        "",
        f"- Payloads: {report['summary']['payloads']}",
        f"- Sent: {report['summary']['sent']}",
        f"- Dry run: {report['summary']['dry_run']}",
        f"- Failed: {report['summary']['failed']}",
        "",
        "## Operating Rules",
        "",
        "- Use `HOMEPILOT_CRM_WEBHOOK_URL` and optional `HOMEPILOT_CRM_API_KEY` from the environment only.",
        "- Upsert by `idempotency_key`; do not create duplicate CRM records.",
        "- Failed rows are written to dead letter output for manual review.",
        "- Archive this report beside the integration manifest before production activation.",
        "",
    ]
    if report["failures"]:
        lines += ["## Failures", ""]
        lines.extend(f"- {failure}" for failure in report["failures"])
    if report["warnings"]:
        lines += ["## Warnings", ""]
        lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.append("")
    return "\n".join(lines)


def build_integration_sync_pack(
    integration_manifest_path: Path,
    out_dir: Path,
    live: bool = False,
    env: dict[str, str] | None = None,
    sender: Sender | None = None,
    max_attempts: int = 3,
    timeout: int = 20,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    manifest = load_json(integration_manifest_path)
    webhook_path = _path_from_manifest(manifest, "webhook_jsonl")
    payloads = read_jsonl(webhook_path) if webhook_path else []
    webhook_url = env.get(WEBHOOK_URL_ENV, "")
    api_key = env.get(API_KEY_ENV, "")
    sender = sender or default_sender
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "sync_report.json"
    runbook_path = out_dir / "SYNC_RUNBOOK.md"
    attempts_path = out_dir / "delivery_attempts.jsonl"
    dead_letter_path = out_dir / "dead_letter.jsonl"

    failures = _validate_payloads(payloads)
    warnings: list[str] = []
    attempts: list[dict[str, Any]] = []
    dead_letters: list[dict[str, Any]] = []
    if manifest.get("status") != "pass":
        failures.append(f"Integration manifest status is {manifest.get('status')!r}, expected pass.")
    if live and not webhook_url:
        failures.append(f"Live sync requires {WEBHOOK_URL_ENV}.")
    if not payloads:
        warnings.append("No webhook payloads available for sync.")

    if not failures:
        if live:
            for payload in payloads:
                result = _send_with_retries(payload, webhook_url, api_key, sender, max_attempts=max_attempts, timeout=timeout)
                attempts.append(result)
                if result["status"] == "failed":
                    dead_letters.append({"delivery": result, "payload": payload})
        else:
            attempts = [_dry_run_attempt(payload) for payload in payloads]

    if dead_letters:
        failures.append(f"{len(dead_letters)} webhook payload(s) failed delivery.")

    write_jsonl(attempts_path, attempts)
    write_jsonl(dead_letter_path, dead_letters)

    sent = sum(1 for item in attempts if item.get("status") == "sent")
    dry_run_count = sum(1 for item in attempts if item.get("status") == "dry_run")
    failed = sum(1 for item in attempts if item.get("status") == "failed")
    report = {
        "report_type": "homepilot_crm_webhook_sync",
        "created_at": utc_now(),
        "status": "pass" if not failures else "fail",
        "mode": "live" if live else "dry_run",
        "source_integration_manifest": str(integration_manifest_path),
        "credentials": {
            "webhook_url_env": WEBHOOK_URL_ENV,
            "webhook_url_configured": bool(webhook_url),
            "webhook_host": _webhook_host(webhook_url),
            "api_key_env": API_KEY_ENV,
            "api_key_configured": bool(api_key),
            "api_key_written": False,
            "auth_header_written": False,
        },
        "summary": {
            "payloads": len(payloads),
            "sent": sent,
            "dry_run": dry_run_count,
            "failed": failed,
            "dead_letters": len(dead_letters),
            "max_attempts": max_attempts,
            "live_api_calls_made": live and bool(attempts),
        },
        "checks": {
            "source_manifest": "pass" if manifest.get("status") == "pass" else "fail",
            "idempotency": "pass" if not any("idempotency" in failure for failure in failures) else "fail",
            "credentials": "pass" if (not live or bool(webhook_url)) else "fail",
            "delivery": "pass" if not failed else "fail",
        },
        "paths": {
            "sync_report": str(report_path),
            "runbook": str(runbook_path),
            "delivery_attempts": str(attempts_path),
            "dead_letter": str(dead_letter_path),
        },
        "failures": failures,
        "warnings": warnings,
    }
    write_json(report_path, report)
    write_text(runbook_path, render_runbook(report))
    secret_findings = _scan_files([report_path, runbook_path, attempts_path, dead_letter_path])
    if secret_findings:
        report["status"] = "fail"
        report["failures"] = [*report["failures"], f"Secret-like values found in sync artifacts: {secret_findings}"]
        write_json(report_path, report)
        write_text(runbook_path, render_runbook(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or dry-run HomePilot CRM/webhook sync")
    parser.add_argument("--integration-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    report = build_integration_sync_pack(
        integration_manifest_path=args.integration_manifest,
        out_dir=args.out_dir,
        live=args.live,
        max_attempts=args.max_attempts,
        timeout=args.timeout,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "mode": report["mode"],
        "summary": report["summary"],
        "sync_report": report["paths"]["sync_report"],
        "runbook": report["paths"]["runbook"],
        "failures": report["failures"],
        "warnings": report["warnings"],
    }, indent=2, ensure_ascii=False))
    if report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
