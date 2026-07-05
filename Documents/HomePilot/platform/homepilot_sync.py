#!/usr/bin/env python3
"""
HomePilot pilot sync runner.

This wraps the platform adapter and store into one repeatable command:

FacadePilot CSV -> HomePilot JSON -> validation -> optional Supabase import.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES, convert_facade_csv
from homepilot_pilot_csv import convert_pilot_csv
from homepilot_store import HomePilotStore, summarize_payload, validate_payload


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent
DEFAULT_EXPORT_DIR = HOME_ROOT / "exports"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_output_path(pilot: str, source_path: Path) -> Path:
    stem = source_path.stem.replace(" ", "_")
    return DEFAULT_EXPORT_DIR / pilot / f"{stem}_{timestamp()}_homepilot.json"


def write_payload(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def sync_payload(
    pilot: str,
    payload: dict[str, Any],
    csv_path: Path,
    output_path: Path | None,
    import_to_supabase: bool,
    dry_run: bool,
) -> dict[str, Any]:
    validate_payload(payload)
    final_output = output_path or default_output_path(pilot, csv_path)
    write_payload(payload, final_output)

    result: dict[str, Any] = {
        "pilot": pilot,
        "source": str(csv_path),
        "output": str(final_output),
        "summary": summarize_payload(payload),
        "imported": None,
        "dry_run": dry_run,
    }

    if import_to_supabase:
        store = HomePilotStore(dry_run=dry_run)
        store.seed_modules()
        result["imported"] = store.import_payload(payload)

    return result


def sync_facadepilot(
    csv_path: Path,
    tenant_id: str,
    campaign_id: str | None,
    source_run_id: str | None,
    output_path: Path | None,
    import_to_supabase: bool,
    dry_run: bool,
) -> dict[str, Any]:
    payload = convert_facade_csv(
        csv_path,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        source_run_id=source_run_id,
    )
    return sync_payload(
        pilot="facadepilot",
        payload=payload,
        csv_path=csv_path,
        output_path=output_path,
        import_to_supabase=import_to_supabase,
        dry_run=dry_run,
    )


def sync_generic_pilot_csv(
    csv_path: Path,
    module_key: str,
    tenant_id: str,
    campaign_id: str | None,
    campaign_name: str | None,
    source_run_id: str | None,
    output_path: Path | None,
    import_to_supabase: bool,
    dry_run: bool,
) -> dict[str, Any]:
    payload = convert_pilot_csv(
        csv_path=csv_path,
        module_key=module_key,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        source_run_id=source_run_id,
    )
    return sync_payload(
        pilot=module_key,
        payload=payload,
        csv_path=csv_path,
        output_path=output_path,
        import_to_supabase=import_to_supabase,
        dry_run=dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Pilot output into HomePilot")
    sub = parser.add_subparsers(dest="pilot", required=True)

    facade = sub.add_parser("facadepilot", help="Sync FacadePilot scored CSV")
    facade.add_argument("--csv", required=True, type=Path)
    facade.add_argument("--tenant-id", required=True)
    facade.add_argument("--campaign-id", default="")
    facade.add_argument("--source-run-id", default="")
    facade.add_argument("--out", type=Path, default=None)
    facade.add_argument("--import", dest="import_to_supabase", action="store_true")
    facade.add_argument("--dry-run", action="store_true", help="Dry-run Supabase writes")

    generic = sub.add_parser("pilot-csv", help="Sync any module CSV with canonical metric columns")
    generic.add_argument("--csv", required=True, type=Path)
    generic.add_argument("--module", required=True, choices=sorted(PILOT_MODULES))
    generic.add_argument("--tenant-id", required=True)
    generic.add_argument("--campaign-id", default="")
    generic.add_argument("--campaign-name", default="")
    generic.add_argument("--source-run-id", default="")
    generic.add_argument("--out", type=Path, default=None)
    generic.add_argument("--import", dest="import_to_supabase", action="store_true")
    generic.add_argument("--dry-run", action="store_true", help="Dry-run Supabase writes")

    args = parser.parse_args()

    if args.pilot == "facadepilot":
        if not args.csv.exists():
            raise SystemExit(f"CSV not found: {args.csv}")
        result = sync_facadepilot(
            csv_path=args.csv,
            tenant_id=args.tenant_id,
            campaign_id=args.campaign_id or None,
            source_run_id=args.source_run_id or None,
            output_path=args.out,
            import_to_supabase=args.import_to_supabase,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.pilot == "pilot-csv":
        if not args.csv.exists():
            raise SystemExit(f"CSV not found: {args.csv}")
        result = sync_generic_pilot_csv(
            csv_path=args.csv,
            module_key=args.module,
            tenant_id=args.tenant_id,
            campaign_id=args.campaign_id or None,
            campaign_name=args.campaign_name or None,
            source_run_id=args.source_run_id or None,
            output_path=args.out,
            import_to_supabase=args.import_to_supabase,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
