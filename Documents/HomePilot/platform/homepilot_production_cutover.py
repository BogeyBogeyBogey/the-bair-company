#!/usr/bin/env python3
"""
HomePilot production cutover orchestrator.

This is the operator-safe sequence for moving from buyer-review evidence to a
production proof bundle. It does not apply SQL migrations automatically. It
verifies the redacted live credential checklist, local deployment manifest, live
schema when requested, module catalog seed, live RLS fixture, planned customer
access, and then runs the final release audit.

Dry-run mode exercises the same evidence chain without writing to Supabase or
claiming production verification.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_customer_access_verification import build_customer_access_verification_from_file
from homepilot_deployment import build_deployment_pack
from homepilot_healthcheck import build_healthcheck_report
from homepilot_launch import run_live_rls_launch
from homepilot_live_readiness import build_live_readiness_report
from homepilot_live_schema_verification import build_schema_verification_report
from homepilot_release_audit import build_release_audit
from homepilot_store import HOME_ROOT, HomePilotStore, load_dotenv_file


for env_path in (HOME_ROOT / ".env", HOME_ROOT / "platform" / ".env"):
    load_dotenv_file(env_path)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _env_value(env: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def _fixture_value(env: dict[str, str], current: str, default: str, env_key: str) -> str:
    if current and current != default:
        return current
    return _env_value(env, env_key) or current or default


def _step(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail, **extra}


def _hard_failed(steps: list[dict[str, Any]]) -> bool:
    return any(step["status"] == "fail" for step in steps)


def _default_account_access_plan(readiness_report_path: Path | None, explicit_path: Path | None) -> Path | None:
    if explicit_path:
        return explicit_path
    readiness = load_json(readiness_report_path)
    if not readiness:
        return None
    access_dir = readiness.get("paths", {}).get("account_access_smoke")
    if access_dir:
        candidate = Path(access_dir) / "account_access_plan.json"
        if candidate.exists():
            return candidate
    return None


def _seed_modules(out_dir: Path, url: str, service_key: str, dry_run: bool) -> dict[str, Any]:
    store = HomePilotStore(url=url, service_key=service_key, dry_run=dry_run)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        count = store.seed_modules()
    seed_report = {
        "report_type": "homepilot_module_seed",
        "created_at": utc_now(),
        "status": "dry_run" if dry_run else "pass",
        "dry_run": dry_run,
        "configured": store.configured,
        "modules": count,
        "stdout": log.getvalue().strip().splitlines(),
    }
    path = out_dir / "module_seed.json"
    write_json(path, seed_report)
    seed_report["path"] = str(path)
    return seed_report


def render_cutover_runbook(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Production Cutover",
        "",
        f"Created: {report['created_at']}",
        f"Mode: {report['mode']}",
        f"Status: {report['status']}",
        f"Production verified: {str(report['production_verified']).lower()}",
        "",
        "## Step Status",
        "",
    ]
    for step in report["steps"]:
        lines.append(f"- {step['name']}: {step['status']} - {step['detail']}")
    lines += [
        "",
        "## Production Rules",
        "",
        "- Schema SQL must be applied and then verified by live schema metadata.",
        "- Live readiness must be ready before any live seed/import/probe step runs.",
        "- The module catalog must be seeded after schema verification.",
        "- Live RLS fixture and customer access verification must both pass with real customer JWTs.",
        "- Fixture cleanup SQL is reviewed only after evidence is archived.",
        "- This report does not contain credentials or customer row-level data.",
        "",
        "## Evidence",
        "",
    ]
    for key, value in report["paths"].items():
        if value:
            lines.append(f"- {key}: {value}")
    if report["blockers"]:
        lines += ["", "## Blockers", ""]
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    lines.append("")
    return "\n".join(lines)


def build_production_cutover(
    out_dir: Path,
    readiness_report_path: Path | None = None,
    due_diligence_report_path: Path | None = None,
    account_access_plan_path: Path | None = None,
    release_label: str = "production-candidate",
    live: bool = False,
    env: dict[str, str] | None = None,
    url: str = "",
    service_key: str = "",
    anon_key: str = "",
    db_url: str = "",
    psql_bin: str = "psql",
    window_email: str = "window.rls@example.com",
    window_password: str = "replace-window-password",
    facade_email: str = "facade.rls@example.com",
    facade_password: str = "replace-facade-password",
    facade_partner_email: str = "facade.partner.rls@example.com",
    facade_partner_password: str = "replace-facade-partner-password",
) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    url = url or _env_value(env, "HOMEPILOT_SUPABASE_URL", "SUPABASE_URL")
    service_key = service_key or _env_value(env, "HOMEPILOT_SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY")
    anon_key = anon_key or _env_value(env, "HOMEPILOT_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY")
    db_url = db_url or _env_value(env, "HOMEPILOT_SUPABASE_DB_URL", "SUPABASE_DB_URL", "DATABASE_URL")
    window_email = _fixture_value(env, window_email, "window.rls@example.com", "HOMEPILOT_RLS_WINDOW_EMAIL")
    window_password = _fixture_value(env, window_password, "replace-window-password", "HOMEPILOT_RLS_WINDOW_PASSWORD")
    facade_email = _fixture_value(env, facade_email, "facade.rls@example.com", "HOMEPILOT_RLS_FACADE_EMAIL")
    facade_password = _fixture_value(env, facade_password, "replace-facade-password", "HOMEPILOT_RLS_FACADE_PASSWORD")
    facade_partner_email = _fixture_value(env, facade_partner_email, "facade.partner.rls@example.com", "HOMEPILOT_RLS_FACADE_PARTNER_EMAIL")
    facade_partner_password = _fixture_value(env, facade_partner_password, "replace-facade-partner-password", "HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD")
    dry_run = not live

    out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    blockers: list[str] = []

    account_access_plan_path = _default_account_access_plan(readiness_report_path, account_access_plan_path)
    readiness = load_json(readiness_report_path)
    due_diligence = load_json(due_diligence_report_path)

    input_failures = []
    if not readiness:
        input_failures.append("Missing readiness report.")
    elif readiness.get("status") != "pass":
        input_failures.append(f"Readiness report status is {readiness.get('status')!r}, expected 'pass'.")
    if not due_diligence:
        input_failures.append("Missing due-diligence report.")
    elif due_diligence.get("status") not in {"local_ready", "production_ready"}:
        input_failures.append(f"Due-diligence report status is {due_diligence.get('status')!r}.")
    if not account_access_plan_path:
        input_failures.append("Missing account access plan.")
    elif not account_access_plan_path.exists():
        input_failures.append(f"Account access plan does not exist: {account_access_plan_path}")
    steps.append(_step(
        "input_evidence",
        "pass" if not input_failures else "fail",
        "Required readiness, due-diligence, and account access inputs are present." if not input_failures else "Required cutover inputs are missing or not ready.",
        failures=input_failures,
    ))

    live_readiness_account_path = (
        account_access_plan_path
        if account_access_plan_path and account_access_plan_path.exists()
        else None
    )
    live_readiness = build_live_readiness_report(
        out_dir / "live_readiness",
        account_access_plan_path=live_readiness_account_path,
        readiness_report_path=readiness_report_path,
        due_diligence_report_path=due_diligence_report_path,
        release_label=release_label,
        env=env,
    )
    live_readiness_pass = (
        live_readiness["ready_to_run_live_cutover"]
        if live
        else live_readiness["status"] in {"ready", "action_required"}
    )
    steps.append(_step(
        "live_readiness",
        "pass" if live_readiness_pass else "fail",
        (
            f"Live readiness status is {live_readiness['status']}."
            if live_readiness_pass
            else f"Live readiness missing {len(live_readiness['missing_live_inputs'])} required live inputs."
        ),
        path=live_readiness["paths"]["live_readiness"],
        markdown=live_readiness["paths"]["markdown"],
        env_template=live_readiness["paths"]["env_template"],
        ready_to_run_live_cutover=live_readiness["ready_to_run_live_cutover"],
        missing_live_inputs=len(live_readiness["missing_live_inputs"]),
    ))

    health_dir = out_dir / "health"
    health_dir.mkdir(parents=True, exist_ok=True)
    health = build_healthcheck_report(env=env, live=live, require_live=live)
    health_path = health_dir / "healthcheck.json"
    write_json(health_path, health)
    steps.append(_step(
        "healthcheck",
        "pass" if health["status"] in {"pass", "warn"} and not live else ("pass" if health["status"] == "pass" else "fail"),
        f"Healthcheck status is {health['status']}.",
        path=str(health_path),
    ))

    deployment = build_deployment_pack(out_dir / "deployment", release_label=release_label)
    steps.append(_step(
        "deployment_manifest",
        "pass" if deployment["status"] == "pass" else "fail",
        f"Deployment manifest status is {deployment['status']}.",
        path=deployment["paths"]["deployment_manifest"],
    ))

    schema = build_schema_verification_report(
        out_dir / "schema_verification",
        live=live,
        db_url=db_url,
        env=env,
        psql_bin=psql_bin,
    )
    schema_expected_status = "pass" if live else "dry_run"
    steps.append(_step(
        "schema_verification",
        "pass" if schema["status"] == schema_expected_status else "fail",
        f"Schema verification status is {schema['status']}.",
        path=schema["paths"]["schema_verification"],
        production_verified=schema["production_verified"],
    ))

    seed_report: dict[str, Any] | None = None
    launch: dict[str, Any] | None = None
    customer_access: dict[str, Any] | None = None
    release_audit: dict[str, Any] | None = None

    if not _hard_failed(steps):
        try:
            seed_report = _seed_modules(out_dir / "module_seed", url, service_key, dry_run=dry_run)
            steps.append(_step(
                "seed_modules",
                "pass" if seed_report["status"] in {"pass", "dry_run"} else "fail",
                f"Module seed status is {seed_report['status']}.",
                path=seed_report["path"],
                modules=seed_report["modules"],
            ))
        except Exception as exc:
            steps.append(_step("seed_modules", "fail", f"Module seed failed: {str(exc)[:500]}"))

    if not _hard_failed(steps):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                launch = run_live_rls_launch(
                    out_dir=out_dir / "launch",
                    url=url,
                    service_key=service_key,
                    anon_key=anon_key,
                    dry_run=dry_run,
                    window_email=window_email,
                    window_password=window_password,
                    facade_email=facade_email,
                    facade_password=facade_password,
                    facade_partner_email=facade_partner_email,
                    facade_partner_password=facade_partner_password,
                )
            expected_launch_status = "pass" if live else "dry_run"
            steps.append(_step(
                "rls_launch",
                "pass" if launch["status"] == expected_launch_status else "fail",
                f"RLS launch status is {launch['status']}.",
                path=launch["paths"]["launch_report"],
                production_verified=launch["production_verified"],
            ))
        except Exception as exc:
            steps.append(_step("rls_launch", "fail", f"RLS launch failed: {str(exc)[:500]}"))

    if not account_access_plan_path:
        steps.append(_step("customer_access_verification", "fail", "Account access plan is required for cutover."))
    elif not _hard_failed(steps):
        try:
            customer_access = build_customer_access_verification_from_file(
                out_dir=out_dir / "customer_access",
                account_access_plan_path=account_access_plan_path,
                url=url,
                anon_key=anon_key,
                dry_run=dry_run,
                env=env,
            )
            expected_access_status = "pass" if live else "dry_run"
            steps.append(_step(
                "customer_access_verification",
                "pass" if customer_access["status"] == expected_access_status else "fail",
                f"Customer access verification status is {customer_access['status']}.",
                path=customer_access["paths"]["customer_access_verification"],
                production_verified=customer_access["production_verified"],
            ))
        except Exception as exc:
            steps.append(_step("customer_access_verification", "fail", f"Customer access verification failed: {str(exc)[:500]}"))

    release_audit = build_release_audit(
        readiness=readiness,
        due_diligence=due_diligence,
        live_readiness=live_readiness,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema,
    )
    release_audit_path = out_dir / "release_audit.json"
    write_json(release_audit_path, release_audit)
    expected_production = "go" if live else "no_go"
    steps.append(_step(
        "release_audit",
        "pass" if release_audit["decisions"]["production"] == expected_production else "fail",
        f"Release audit production decision is {release_audit['decisions']['production']}.",
        path=str(release_audit_path),
    ))

    blockers.extend(release_audit.get("blockers", {}).get("production", []))
    if _hard_failed(steps):
        blockers.extend(step["detail"] for step in steps if step["status"] == "fail")
    # Preserve order but avoid repeated phrasing.
    deduped_blockers: list[str] = []
    for blocker in blockers:
        if blocker not in deduped_blockers:
            deduped_blockers.append(blocker)

    production_verified = bool(
        live
        and schema.get("production_verified") is True
        and launch
        and launch.get("production_verified") is True
        and customer_access
        and customer_access.get("production_verified") is True
        and release_audit["decisions"]["production"] == "go"
    )
    if production_verified:
        status = "production_verified"
    elif _hard_failed(steps):
        status = "blocked"
    elif dry_run:
        status = "dry_run_ready"
    else:
        status = "action_required"

    report = {
        "report_type": "homepilot_production_cutover",
        "created_at": utc_now(),
        "release_label": release_label,
        "mode": "live" if live else "dry_run",
        "status": status,
        "production_verified": production_verified,
        "decisions": {
            "production": release_audit["decisions"]["production"],
            "buyer_review": release_audit["decisions"]["buyer_review"],
        },
        "steps": steps,
        "blockers": deduped_blockers,
        "inputs": {
            "readiness_report": str(readiness_report_path) if readiness_report_path else None,
            "due_diligence_report": str(due_diligence_report_path) if due_diligence_report_path else None,
            "account_access_plan": str(account_access_plan_path) if account_access_plan_path else None,
            "live": live,
        },
        "paths": {
            "cutover_report": str(out_dir / "cutover_report.json"),
            "runbook": str(out_dir / "CUTOVER_RUNBOOK.md"),
            "healthcheck": str(health_path),
            "live_readiness": live_readiness["paths"]["live_readiness"],
            "live_readiness_markdown": live_readiness["paths"]["markdown"],
            "live_readiness_env_template": live_readiness["paths"]["env_template"],
            "deployment_manifest": deployment["paths"]["deployment_manifest"],
            "deployment_runbook": deployment["paths"]["deployment_runbook"],
            "schema_verification": schema["paths"]["schema_verification"],
            "schema_runbook": schema["paths"]["runbook"],
            "module_seed": seed_report.get("path") if seed_report else None,
            "launch_report": launch["paths"]["launch_report"] if launch else None,
            "rls_probe_report": launch["paths"]["rls_probe_report"] if launch else None,
            "cleanup_plan": launch["paths"]["cleanup_plan"] if launch else None,
            "cleanup_sql": launch["paths"]["cleanup_sql"] if launch else None,
            "customer_access_verification": customer_access["paths"]["customer_access_verification"] if customer_access else None,
            "customer_access_markdown": customer_access["paths"]["markdown"] if customer_access else None,
            "release_audit": str(release_audit_path),
        },
    }
    write_json(out_dir / "cutover_report.json", report)
    write_text(out_dir / "CUTOVER_RUNBOOK.md", render_cutover_runbook(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the HomePilot production cutover evidence chain")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--due-diligence-report", type=Path)
    parser.add_argument("--account-access-plan", type=Path)
    parser.add_argument("--release-label", default="production-candidate")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--url", default=os.environ.get("HOMEPILOT_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "")
    parser.add_argument("--service-key", default=os.environ.get("HOMEPILOT_SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") or "")
    parser.add_argument("--anon-key", default=os.environ.get("HOMEPILOT_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY") or "")
    parser.add_argument("--db-url", default=os.environ.get("HOMEPILOT_SUPABASE_DB_URL") or os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or "")
    parser.add_argument("--psql-bin", default="psql")
    parser.add_argument("--window-email", default=os.environ.get("HOMEPILOT_RLS_WINDOW_EMAIL", "window.rls@example.com"))
    parser.add_argument("--window-password", default=os.environ.get("HOMEPILOT_RLS_WINDOW_PASSWORD", "replace-window-password"))
    parser.add_argument("--facade-email", default=os.environ.get("HOMEPILOT_RLS_FACADE_EMAIL", "facade.rls@example.com"))
    parser.add_argument("--facade-password", default=os.environ.get("HOMEPILOT_RLS_FACADE_PASSWORD", "replace-facade-password"))
    parser.add_argument("--facade-partner-email", default=os.environ.get("HOMEPILOT_RLS_FACADE_PARTNER_EMAIL", "facade.partner.rls@example.com"))
    parser.add_argument("--facade-partner-password", default=os.environ.get("HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD", "replace-facade-partner-password"))
    args = parser.parse_args()

    report = build_production_cutover(
        out_dir=args.out_dir,
        readiness_report_path=args.readiness_report,
        due_diligence_report_path=args.due_diligence_report,
        account_access_plan_path=args.account_access_plan,
        release_label=args.release_label,
        live=args.live,
        url=args.url,
        service_key=args.service_key,
        anon_key=args.anon_key,
        db_url=args.db_url,
        psql_bin=args.psql_bin,
        window_email=args.window_email,
        window_password=args.window_password,
        facade_email=args.facade_email,
        facade_password=args.facade_password,
        facade_partner_email=args.facade_partner_email,
        facade_partner_password=args.facade_partner_password,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "production_verified": report["production_verified"],
        "production": report["decisions"]["production"],
        "cutover_report": report["paths"]["cutover_report"],
        "runbook": report["paths"]["runbook"],
        "blockers": report["blockers"],
    }, indent=2, ensure_ascii=False))
    if args.live and not report["production_verified"]:
        raise SystemExit(1)
    if report["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
