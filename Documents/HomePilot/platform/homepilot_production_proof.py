#!/usr/bin/env python3
"""
Build a tamper-evident HomePilot production proof manifest.

Release audit decides go/no-go. This module makes the evidence reviewable for
enterprise buyers and operators: it records checksums, freshness, missing live
proof, and a redacted secret scan for the handoff artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_release_audit import build_release_audit


SECRET_PATTERNS = {
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "postgres_password_url": re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]{8,}@", re.IGNORECASE),
    "assigned_secret_value": re.compile(r"(?:service[_-]?role|anon[_-]?key|password|token|secret)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_days(created_at: str | None, now: datetime) -> int | None:
    parsed = parse_timestamp(created_at)
    if not parsed:
        return None
    return max(0, (now - parsed).days)


def _artifact_record(
    label: str,
    path: Path | None,
    *,
    required_for_buyer: bool,
    required_for_production: bool,
    max_age_days: int,
    now: datetime,
) -> dict[str, Any]:
    if path is None:
        return {
            "label": label,
            "path": None,
            "status": "missing",
            "required_for_buyer": required_for_buyer,
            "required_for_production": required_for_production,
        }
    if not path.exists():
        return {
            "label": label,
            "path": str(path),
            "status": "missing",
            "required_for_buyer": required_for_buyer,
            "required_for_production": required_for_production,
        }
    created_at = None
    report_type = None
    json_status = "not_json"
    parse_error = None
    if path.suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            json_status = "pass"
            created_at = payload.get("created_at") if isinstance(payload, dict) else None
            report_type = payload.get("report_type") if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError) as exc:
            json_status = "fail"
            parse_error = str(exc)
    age_days = _age_days(created_at, now)
    if age_days is None:
        freshness = "unknown"
    elif age_days <= max_age_days:
        freshness = "pass"
    else:
        freshness = "stale"
    return {
        "label": label,
        "path": str(path),
        "status": "present" if json_status != "fail" else "invalid",
        "required_for_buyer": required_for_buyer,
        "required_for_production": required_for_production,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "json_status": json_status,
        "json_parse_error": parse_error,
        "report_type": report_type,
        "created_at": created_at,
        "age_days": age_days,
        "freshness": freshness,
    }


def scan_artifacts_for_secrets(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    findings = []
    files_scanned = []
    for artifact in artifacts:
        path_value = artifact.get("path")
        if not path_value or artifact.get("status") == "missing":
            continue
        path = Path(path_value)
        if not path.exists() or not path.is_file():
            continue
        files_scanned.append(str(path))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append({
                        "file": str(path),
                        "line": line_number,
                        "pattern": label,
                    })
    return {
        "status": "pass" if not findings else "fail",
        "files_scanned": files_scanned,
        "issue_count": len(findings),
        "issues": findings,
    }


def _artifact_summary(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    missing_buyer = [
        artifact["label"]
        for artifact in artifacts
        if artifact.get("required_for_buyer") and artifact.get("status") == "missing"
    ]
    missing_production = [
        artifact["label"]
        for artifact in artifacts
        if artifact.get("required_for_production") and artifact.get("status") == "missing"
    ]
    invalid = [
        artifact["label"]
        for artifact in artifacts
        if artifact.get("status") == "invalid"
    ]
    return {
        "status": "pass" if not missing_buyer and not invalid else "fail",
        "missing_buyer_artifacts": missing_buyer,
        "missing_production_artifacts": missing_production,
        "invalid_artifacts": invalid,
        "artifact_count": len([artifact for artifact in artifacts if artifact.get("status") != "missing"]),
    }


def _freshness_summary(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    stale = [
        artifact["label"]
        for artifact in artifacts
        if artifact.get("freshness") == "stale"
        and (artifact.get("required_for_buyer") or artifact.get("required_for_production"))
    ]
    unknown_required = [
        artifact["label"]
        for artifact in artifacts
        if artifact.get("freshness") == "unknown"
        and artifact.get("status") != "missing"
        and (artifact.get("required_for_buyer") or artifact.get("required_for_production"))
    ]
    return {
        "status": "pass" if not stale else "fail",
        "stale_required_artifacts": stale,
        "unknown_required_artifacts": unknown_required,
    }


def _build_artifacts(
    paths: dict[str, Path | None],
    max_age_days: int,
    now: datetime,
) -> list[dict[str, Any]]:
    specs = [
        ("readiness_report", True, True),
        ("due_diligence_report", True, True),
        ("live_readiness_report", False, True),
        ("schema_verification_report", False, True),
        ("launch_report", False, True),
        ("customer_access_report", False, True),
        ("release_audit_report", False, False),
        ("preflight_report", False, False),
        ("ops_status_report", False, False),
        ("artifact_index", False, False),
    ]
    return [
        _artifact_record(
            label,
            paths.get(label),
            required_for_buyer=required_for_buyer,
            required_for_production=required_for_production,
            max_age_days=max_age_days,
            now=now,
        )
        for label, required_for_buyer, required_for_production in specs
    ]


def _decisions(
    release_audit: dict[str, Any],
    artifact_summary: dict[str, Any],
    freshness: dict[str, Any],
    redaction: dict[str, Any],
) -> dict[str, str]:
    buyer_ok = (
        release_audit.get("decisions", {}).get("buyer_review") == "go"
        and artifact_summary["status"] == "pass"
        and freshness["status"] == "pass"
        and redaction["status"] == "pass"
    )
    production_ok = (
        buyer_ok
        and release_audit.get("decisions", {}).get("production") == "go"
        and not artifact_summary["missing_production_artifacts"]
    )
    return {
        "buyer_review": "go" if buyer_ok else "no_go",
        "production": "go" if production_ok else "no_go",
    }


def _status(decisions: dict[str, str]) -> str:
    if decisions["production"] == "go":
        return "production_ready"
    if decisions["buyer_review"] == "go":
        return "buyer_review_ready"
    return "action_required"


def build_production_proof_manifest(
    *,
    readiness_report_path: Path,
    due_diligence_report_path: Path,
    live_readiness_report_path: Path | None = None,
    schema_verification_report_path: Path | None = None,
    launch_report_path: Path | None = None,
    customer_access_report_path: Path | None = None,
    release_audit_report_path: Path | None = None,
    preflight_report_path: Path | None = None,
    ops_status_report_path: Path | None = None,
    artifact_index_path: Path | None = None,
    release_label: str = "local",
    max_evidence_age_days: int = 30,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    paths = {
        "readiness_report": readiness_report_path,
        "due_diligence_report": due_diligence_report_path,
        "live_readiness_report": live_readiness_report_path,
        "schema_verification_report": schema_verification_report_path,
        "launch_report": launch_report_path,
        "customer_access_report": customer_access_report_path,
        "release_audit_report": release_audit_report_path,
        "preflight_report": preflight_report_path,
        "ops_status_report": ops_status_report_path,
        "artifact_index": artifact_index_path,
    }
    readiness = load_json(readiness_report_path)
    due_diligence = load_json(due_diligence_report_path)
    live_readiness = load_json(live_readiness_report_path)
    schema_verification = load_json(schema_verification_report_path)
    launch = load_json(launch_report_path)
    customer_access = load_json(customer_access_report_path)
    release_audit = load_json(release_audit_report_path) or build_release_audit(
        readiness=readiness,
        due_diligence=due_diligence,
        live_readiness=live_readiness,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema_verification,
    )

    artifacts = _build_artifacts(paths, max_evidence_age_days, now)
    artifact_summary = _artifact_summary(artifacts)
    freshness = _freshness_summary(artifacts)
    redaction = scan_artifacts_for_secrets(artifacts)
    decisions = _decisions(release_audit, artifact_summary, freshness, redaction)
    required_for_production = release_audit.get("required_for_production", [])

    return {
        "report_type": "homepilot_production_proof_manifest",
        "created_at": now.isoformat(),
        "release_label": release_label,
        "status": _status(decisions),
        "decisions": decisions,
        "artifact_integrity": artifact_summary,
        "freshness": {
            **freshness,
            "max_evidence_age_days": max_evidence_age_days,
        },
        "redaction": redaction,
        "release_audit": {
            "status": release_audit.get("status"),
            "decisions": release_audit.get("decisions", {}),
            "production_blockers": release_audit.get("blockers", {}).get("production", []),
            "required_for_production": required_for_production,
        },
        "artifacts": artifacts,
        "production_gate": {
            "verified": decisions["production"] == "go",
            "missing_live_artifacts": artifact_summary["missing_production_artifacts"],
            "blockers": release_audit.get("blockers", {}).get("production", []),
        },
        "guardrails": {
            "secret_values_written": redaction["status"] != "pass",
            "hashes_recorded": all("sha256" in artifact for artifact in artifacts if artifact.get("status") != "missing"),
            "live_proof_required": decisions["production"] != "go",
        },
    }


def render_production_proof_markdown(manifest: dict[str, Any]) -> str:
    production_gate = manifest["production_gate"]
    lines = [
        "# HomePilot Production Proof Manifest",
        "",
        f"Release: {manifest['release_label']}",
        f"Created: {manifest['created_at']}",
        f"Status: {manifest['status']}",
        "",
        "## Decisions",
        "",
        f"- Buyer review: {manifest['decisions']['buyer_review']}",
        f"- Production: {manifest['decisions']['production']}",
        "",
        "## Integrity",
        "",
        f"- Artifact integrity: {manifest['artifact_integrity']['status']}",
        f"- Freshness: {manifest['freshness']['status']}",
        f"- Secret scan: {manifest['redaction']['status']}",
        f"- Hashes recorded: {str(manifest['guardrails']['hashes_recorded']).lower()}",
        "",
        "## Production Blockers",
        "",
    ]
    blockers = production_gate.get("blockers", [])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- None.")
    lines += [
        "",
        "## Missing Live Artifacts",
        "",
    ]
    missing = production_gate.get("missing_live_artifacts", [])
    if missing:
        lines.extend(f"- {label}" for label in missing)
    else:
        lines.append("- None.")
    lines += [
        "",
        "## Evidence Hashes",
        "",
    ]
    for artifact in manifest["artifacts"]:
        if artifact.get("status") == "missing":
            lines.append(f"- {artifact['label']}: missing")
            continue
        lines.append(f"- {artifact['label']}: `{artifact['sha256']}` ({artifact['bytes']} bytes)")
    lines += [
        "",
        "## Required For Production",
        "",
    ]
    for item in manifest["release_audit"]["required_for_production"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def build_production_proof_pack(out_dir: Path, **kwargs: Any) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_production_proof_manifest(**kwargs)
    manifest_path = out_dir / "production_proof.json"
    markdown_path = out_dir / "PRODUCTION_PROOF.md"
    write_json(manifest_path, manifest)
    write_text(markdown_path, render_production_proof_markdown(manifest))
    manifest["paths"] = {
        "production_proof": str(manifest_path),
        "production_proof_markdown": str(markdown_path),
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot production proof manifest")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--readiness-report", required=True, type=Path)
    parser.add_argument("--due-diligence-report", required=True, type=Path)
    parser.add_argument("--live-readiness-report", type=Path)
    parser.add_argument("--schema-verification-report", type=Path)
    parser.add_argument("--launch-report", type=Path)
    parser.add_argument("--customer-access-report", type=Path)
    parser.add_argument("--release-audit-report", type=Path)
    parser.add_argument("--preflight-report", type=Path)
    parser.add_argument("--ops-status-report", type=Path)
    parser.add_argument("--artifact-index", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--max-evidence-age-days", type=int, default=30)
    args = parser.parse_args()

    manifest = build_production_proof_pack(
        args.out_dir,
        readiness_report_path=args.readiness_report,
        due_diligence_report_path=args.due_diligence_report,
        live_readiness_report_path=args.live_readiness_report,
        schema_verification_report_path=args.schema_verification_report,
        launch_report_path=args.launch_report,
        customer_access_report_path=args.customer_access_report,
        release_audit_report_path=args.release_audit_report,
        preflight_report_path=args.preflight_report,
        ops_status_report_path=args.ops_status_report,
        artifact_index_path=args.artifact_index,
        release_label=args.release_label,
        max_evidence_age_days=args.max_evidence_age_days,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": manifest["status"],
        "buyer_review": manifest["decisions"]["buyer_review"],
        "production": manifest["decisions"]["production"],
        "production_proof": manifest["paths"]["production_proof"],
        "production_proof_markdown": manifest["paths"]["production_proof_markdown"],
    }, indent=2, ensure_ascii=False))
    if manifest["decisions"]["buyer_review"] != "go":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
