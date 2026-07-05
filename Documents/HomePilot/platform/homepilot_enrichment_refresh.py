#!/usr/bin/env python3
"""
Build or execute HomePilot enrichment refresh batches.

The enrichment plan explains source coverage and backlog. This runner turns
that backlog into auditable vendor/API refresh jobs with idempotency, dry-run
evidence, optional live webhook execution, retry accounting, dead-letter output,
and secret-safe reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ENDPOINT_ENV = "HOMEPILOT_ENRICHMENT_WEBHOOK_URL"
API_KEY_ENV = "HOMEPILOT_ENRICHMENT_API_KEY"
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _host(url: str) -> str:
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


def _requirements_by_key(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("key")): row
        for row in plan.get("source_requirements", [])
        if isinstance(row, dict) and row.get("key")
    }


def _job_priority(category: str, priority: str) -> int:
    category_rank = {
        "contact_provenance": 100,
        "geocode": 95,
        "parcel_boundary": 90,
        "imagery": 75,
        "building_age_energy": 70,
        "permit_history": 65,
        "pricing_estimate": 60,
    }
    priority_bonus = {"high": 10, "medium": 5, "low": 0}.get(priority, 0)
    return category_rank.get(category, 50) + priority_bonus


def build_refresh_jobs(plan: dict[str, Any], max_jobs: int | None = None) -> list[dict[str, Any]]:
    tenant = plan.get("tenant") if isinstance(plan.get("tenant"), dict) else {}
    tenant_id = str(tenant.get("id") or "")
    requirements = _requirements_by_key(plan)
    jobs = []
    for index, item in enumerate(plan.get("backlog", []), start=1):
        category = str(item.get("category") or "")
        requirement = requirements.get(category, {})
        property_id = str(item.get("property_id") or "")
        idempotency_key = f"homepilot:enrichment:{tenant_id}:{property_id}:{category}"
        jobs.append({
            "job_id": f"enrich_{index:04d}",
            "idempotency_key": idempotency_key,
            "event_type": "homepilot.enrichment.refresh",
            "tenant_id": tenant_id,
            "property_id": property_id,
            "address": str(item.get("address") or ""),
            "city": str(item.get("city") or ""),
            "category": category,
            "label": str(item.get("label") or requirement.get("label") or category),
            "priority": str(item.get("priority") or "medium"),
            "priority_score": _job_priority(category, str(item.get("priority") or "medium")),
            "recommended_sources": str(item.get("recommended_sources") or "; ".join(requirement.get("vendor_options", []))),
            "freshness_sla": str(requirement.get("freshness_sla") or ""),
            "license_review": str(requirement.get("license_review") or ""),
            "guardrails": {
                "tenant_scoped": bool(tenant_id),
                "license_review_required": True,
                "credentials_in_payload": False,
                "raw_owner_contact_in_payload": False,
            },
        })
    jobs.sort(key=lambda row: (-int(row["priority_score"]), row["property_id"], row["category"]))
    if max_jobs is not None:
        return jobs[:max_jobs]
    return jobs


def _validate_jobs(jobs: list[dict[str, Any]]) -> list[str]:
    failures = []
    keys = []
    for index, job in enumerate(jobs, start=1):
        key = str(job.get("idempotency_key") or "")
        keys.append(key)
        if not key:
            failures.append(f"Job {index} is missing idempotency_key.")
        if job.get("event_type") != "homepilot.enrichment.refresh":
            failures.append(f"Job {index} has unexpected event_type {job.get('event_type')!r}.")
        guardrails = job.get("guardrails") if isinstance(job.get("guardrails"), dict) else {}
        if guardrails.get("tenant_scoped") is not True or guardrails.get("credentials_in_payload") is not False:
            failures.append(f"Job {index} is missing required tenant/credential guardrails.")
        if not str(job.get("category") or ""):
            failures.append(f"Job {index} is missing category.")
        if not str(job.get("property_id") or ""):
            failures.append(f"Job {index} is missing property_id.")
    if len(keys) != len(set(keys)):
        failures.append("Duplicate enrichment idempotency_key values detected.")
    return failures


def _dry_run_attempt(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job.get("job_id"),
        "idempotency_key": job.get("idempotency_key"),
        "category": job.get("category"),
        "status": "dry_run",
        "attempts": 0,
        "http_status": None,
        "error": "",
    }


def _send_with_retries(
    job: dict[str, Any],
    endpoint_url: str,
    api_key: str,
    sender: Sender,
    max_attempts: int,
    timeout: int,
) -> dict[str, Any]:
    idempotency_key = str(job.get("idempotency_key") or "")
    headers = _headers(api_key, idempotency_key)
    last: dict[str, Any] = {}
    for attempt in range(1, max_attempts + 1):
        last = sender(endpoint_url, job, headers, timeout)
        status_code = int(last.get("status_code") or 0)
        if 200 <= status_code < 300:
            return {
                "job_id": job.get("job_id"),
                "idempotency_key": idempotency_key,
                "category": job.get("category"),
                "status": "sent",
                "attempts": attempt,
                "http_status": status_code,
                "error": "",
            }
        if status_code and status_code < 500:
            break
    return {
        "job_id": job.get("job_id"),
        "idempotency_key": idempotency_key,
        "category": job.get("category"),
        "status": "failed",
        "attempts": max_attempts,
        "http_status": int(last.get("status_code") or 0) or None,
        "error": str(last.get("error") or last.get("body") or "delivery_failed")[:300],
    }


def render_runbook(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Enrichment Refresh Runbook",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Mode: {report['mode']}",
        f"Endpoint host: {report['credentials']['endpoint_host'] or 'not configured'}",
        "",
        "## Summary",
        "",
        f"- Jobs: {report['summary']['jobs']}",
        f"- Sent: {report['summary']['sent']}",
        f"- Dry run: {report['summary']['dry_run']}",
        f"- Failed: {report['summary']['failed']}",
        f"- Dead letters: {report['summary']['dead_letters']}",
        "",
        "## Operating Rules",
        "",
        "- Use `HOMEPILOT_ENRICHMENT_WEBHOOK_URL` and optional `HOMEPILOT_ENRICHMENT_API_KEY` from the environment only.",
        "- Upsert/merge by `idempotency_key`; do not duplicate source records.",
        "- Keep vendor credentials out of payloads, reports, CSVs, and runbooks.",
        "- Failed jobs are written to dead_letter.jsonl for review and replay.",
        "- Refresh outputs must preserve tenant/module scope and source provenance.",
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


def build_enrichment_refresh_pack(
    enrichment_plan_path: Path,
    out_dir: Path,
    live: bool = False,
    env: dict[str, str] | None = None,
    sender: Sender | None = None,
    max_jobs: int | None = None,
    max_attempts: int = 3,
    timeout: int = 20,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    sender = sender or default_sender
    plan = load_json(enrichment_plan_path)
    jobs = build_refresh_jobs(plan, max_jobs=max_jobs)
    endpoint_url = env.get(ENDPOINT_ENV, "")
    api_key = env.get(API_KEY_ENV, "")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "enrichment_refresh_report.json"
    runbook_path = out_dir / "ENRICHMENT_REFRESH_RUNBOOK.md"
    jobs_jsonl_path = out_dir / "refresh_jobs.jsonl"
    jobs_csv_path = out_dir / "refresh_jobs.csv"
    attempts_path = out_dir / "delivery_attempts.jsonl"
    dead_letter_path = out_dir / "dead_letter.jsonl"

    failures = _validate_jobs(jobs)
    warnings: list[str] = []
    attempts: list[dict[str, Any]] = []
    dead_letters: list[dict[str, Any]] = []
    if plan.get("status") != "pass":
        failures.append(f"Enrichment plan status is {plan.get('status')!r}, expected pass.")
    if live and not endpoint_url:
        failures.append(f"Live enrichment refresh requires {ENDPOINT_ENV}.")
    if not jobs:
        warnings.append("No enrichment backlog jobs available for refresh.")

    if not failures:
        if live:
            for job in jobs:
                result = _send_with_retries(job, endpoint_url, api_key, sender, max_attempts=max_attempts, timeout=timeout)
                attempts.append(result)
                if result["status"] == "failed":
                    dead_letters.append({"delivery": result, "job": job})
        else:
            attempts = [_dry_run_attempt(job) for job in jobs]

    if dead_letters:
        failures.append(f"{len(dead_letters)} enrichment refresh job(s) failed delivery.")

    write_jsonl(jobs_jsonl_path, jobs)
    write_csv(jobs_csv_path, jobs)
    write_jsonl(attempts_path, attempts)
    write_jsonl(dead_letter_path, dead_letters)

    sent = sum(1 for item in attempts if item.get("status") == "sent")
    dry_run_count = sum(1 for item in attempts if item.get("status") == "dry_run")
    failed = sum(1 for item in attempts if item.get("status") == "failed")
    categories = sorted({str(job.get("category")) for job in jobs if job.get("category")})
    report = {
        "report_type": "homepilot_enrichment_refresh",
        "created_at": utc_now(),
        "status": "pass" if not failures else "fail",
        "mode": "live" if live else "dry_run",
        "source_enrichment_plan": str(enrichment_plan_path),
        "credentials": {
            "endpoint_env": ENDPOINT_ENV,
            "endpoint_configured": bool(endpoint_url),
            "endpoint_host": _host(endpoint_url),
            "api_key_env": API_KEY_ENV,
            "api_key_configured": bool(api_key),
            "api_key_written": False,
            "auth_header_written": False,
        },
        "summary": {
            "jobs": len(jobs),
            "categories": categories,
            "sent": sent,
            "dry_run": dry_run_count,
            "failed": failed,
            "dead_letters": len(dead_letters),
            "max_attempts": max_attempts,
            "live_api_calls_made": live and bool(attempts),
        },
        "checks": {
            "source_plan": "pass" if plan.get("status") == "pass" else "fail",
            "idempotency": "pass" if not any("idempotency" in failure for failure in failures) else "fail",
            "credentials": "pass" if (not live or bool(endpoint_url)) else "fail",
            "delivery": "pass" if not failed else "fail",
            "tenant_scope": "pass" if all(job.get("guardrails", {}).get("tenant_scoped") for job in jobs) else "fail",
        },
        "paths": {
            "refresh_report": str(report_path),
            "runbook": str(runbook_path),
            "refresh_jobs_jsonl": str(jobs_jsonl_path),
            "refresh_jobs_csv": str(jobs_csv_path),
            "delivery_attempts": str(attempts_path),
            "dead_letter": str(dead_letter_path),
        },
        "failures": failures,
        "warnings": warnings,
    }
    write_json(report_path, report)
    write_text(runbook_path, render_runbook(report))
    secret_findings = _scan_files([report_path, runbook_path, jobs_jsonl_path, jobs_csv_path, attempts_path, dead_letter_path])
    if secret_findings:
        report["status"] = "fail"
        report["failures"] = [*report["failures"], f"Secret-like values found in enrichment refresh artifacts: {secret_findings}"]
        write_json(report_path, report)
        write_text(runbook_path, render_runbook(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or dry-run HomePilot enrichment refresh jobs")
    parser.add_argument("--enrichment-plan", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    report = build_enrichment_refresh_pack(
        enrichment_plan_path=args.enrichment_plan,
        out_dir=args.out_dir,
        live=args.live,
        max_jobs=args.max_jobs,
        max_attempts=args.max_attempts,
        timeout=args.timeout,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "mode": report["mode"],
        "summary": report["summary"],
        "refresh_report": report["paths"]["refresh_report"],
        "runbook": report["paths"]["runbook"],
        "failures": report["failures"],
        "warnings": report["warnings"],
    }, indent=2, ensure_ascii=False))
    if report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
