#!/usr/bin/env python3
"""
Build the HomePilot Intelligence Lab evidence stack.

The lab orchestrates the non-mutating autoresearch families in the order needed
for enterprise review: lead prioritization, partner assignment, campaign
segmentation, and message strategy. It updates the provided snapshot in memory
and writes review artifacts only. It does not write live data, mutate Supabase,
change outreach state, or grant partner access.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_campaign_segmentation_autoresearch import build_campaign_segmentation_autoresearch_pack
from homepilot_lead_autoresearch import build_lead_autoresearch_pack
from homepilot_message_strategy_autoresearch import build_message_strategy_autoresearch_pack
from homepilot_partner_assignment_autoresearch import build_partner_assignment_autoresearch_pack


RAW_ADDRESS_MARKERS = (
    "daw gevelstraat",
    "daw demolaan",
    "daw crepiweg",
    "daw isolatiepad",
    "daw pleisterlaan",
    "daw renovatiehof",
    "daw steenweg",
    "daw energieplein",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _network(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}


def _is_producer_network(snapshot: dict[str, Any]) -> bool:
    return str(_network(snapshot).get("type") or "") == "producer_partner_network"


def _partner_count(snapshot: dict[str, Any]) -> int:
    partners = _network(snapshot).get("partners")
    return len(partners) if isinstance(partners, list) else 0


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _family_summary(pack: dict[str, Any], score_key: str = "best_score") -> dict[str, Any]:
    summary = pack.get("summary") if isinstance(pack.get("summary"), dict) else {}
    return {
        "status": pack.get("status"),
        "best_tag": summary.get("best_tag"),
        "best_strategy": summary.get("best_strategy") or summary.get("best_model"),
        "best_score": summary.get(score_key),
        "baseline_score": summary.get("baseline_score"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Intelligence Lab",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Release: {report['release_label']}",
        "",
        "## Families",
        "",
    ]
    for name, family in report["families"].items():
        lines.append(
            f"- `{name}`: {family['status']}, best {family.get('best_tag')}, score {family.get('best_score')}"
        )
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def _secret_scan(paths: list[Path]) -> list[str]:
    markers = (
        "service-role",
        "secret-token",
        "authorization: bearer",
        "supabase_service_role",
        "@example.",
        "guaranteed",
        *RAW_ADDRESS_MARKERS,
    )
    findings = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in markers:
            if marker in body:
                findings.append(f"{path.name}: contains {marker}")
    return findings


def build_intelligence_lab_pack(
    out_dir: Path,
    snapshot: dict[str, Any],
    release_label: str = "local",
    run_count: int = 12,
    lead_limit: int = 50,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": str(out_dir / "INTELLIGENCE_LAB.md"),
        "pack": str(out_dir / "intelligence_lab.json"),
    }
    families: dict[str, Any] = {}

    lead_pack = build_lead_autoresearch_pack(
        out_dir / "lead_prioritization",
        snapshot=snapshot,
        release_label=f"{release_label}-lead",
        run_count=run_count,
        limit=lead_limit,
    )
    snapshot["leadPrioritization"] = _read_json(lead_pack["paths"]["best_lead_priority"])
    families["lead_prioritization"] = {
        **_family_summary(lead_pack),
        "paths": lead_pack["paths"],
    }

    if _is_producer_network(snapshot) and _partner_count(snapshot):
        assignment_pack = build_partner_assignment_autoresearch_pack(
            out_dir / "partner_assignment",
            snapshot=snapshot,
            release_label=f"{release_label}-partner-assignment",
            run_count=run_count,
            limit=lead_limit,
        )
        snapshot["partnerAssignment"] = _read_json(assignment_pack["paths"]["best_partner_assignment"])
        families["partner_assignment"] = {
            **_family_summary(assignment_pack),
            "scope_leakage_count": assignment_pack["summary"]["scope_leakage_count"],
            "paths": assignment_pack["paths"],
        }

    segmentation_pack = build_campaign_segmentation_autoresearch_pack(
        out_dir / "campaign_segmentation",
        snapshot=snapshot,
        release_label=f"{release_label}-campaign-segmentation",
        run_count=run_count,
    )
    snapshot["campaignSegmentation"] = _read_json(segmentation_pack["paths"]["best_campaign_segments"])
    families["campaign_segmentation"] = {
        **_family_summary(segmentation_pack),
        "response_denominator": "contacted_count",
        "paths": segmentation_pack["paths"],
    }

    message_pack = build_message_strategy_autoresearch_pack(
        out_dir / "message_strategy",
        snapshot=snapshot,
        release_label=f"{release_label}-message-strategy",
        run_count=run_count,
    )
    snapshot["messageStrategy"] = _read_json(message_pack["paths"]["best_message_strategy"])
    families["message_strategy"] = {
        **_family_summary(message_pack),
        "forbidden_claim_count": message_pack["summary"]["forbidden_claim_count"],
        "compliance_pass_rate_pct": message_pack["summary"]["compliance_pass_rate_pct"],
        "paths": message_pack["paths"],
    }

    report = {
        "pack_type": "homepilot_intelligence_lab",
        "created_at": utc_now(),
        "status": "pass" if all(family.get("status") == "pass" for family in families.values()) else "fail",
        "release_label": release_label,
        "families": families,
        "snapshot_keys_attached": [
            key
            for key in ("leadPrioritization", "partnerAssignment", "campaignSegmentation", "messageStrategy")
            if key in snapshot
        ],
        "guardrails": {
            "tenant_scoped_snapshot_only": True,
            "module_scoped": True,
            "partner_scoped_for_producer_networks": True,
            "non_mutating_pack": True,
            "writes_live_data": False,
            "writes_supabase": False,
            "changes_outreach_state": False,
            "drafts_require_customer_approval": True,
            "no_homeowner_intent_claims": True,
            "raw_addresses_written": False,
            "raw_contact_values_written": False,
        },
        "paths": paths,
    }
    write_json(Path(paths["pack"]), report)
    Path(paths["report"]).write_text(render_markdown(report), encoding="utf-8")
    scan_paths = [Path(paths["pack"]), Path(paths["report"])]
    for family in families.values():
        family_paths = family.get("paths") if isinstance(family.get("paths"), dict) else {}
        scan_paths.extend(Path(value) for value in family_paths.values())
    findings = _secret_scan(scan_paths)
    report["secret_scan"] = {"status": "pass" if not findings else "fail", "findings": findings}
    if findings:
        report["status"] = "fail"
    write_json(Path(paths["pack"]), report)
    return {
        "status": report["status"],
        "report": report,
        "paths": paths,
        "snapshot": snapshot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot Intelligence Lab evidence")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--run", type=int, default=12)
    parser.add_argument("--lead-limit", type=int, default=50)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    pack = build_intelligence_lab_pack(
        args.out_dir,
        snapshot=snapshot,
        release_label=args.release_label,
        run_count=args.run,
        lead_limit=args.lead_limit,
    )
    print(json.dumps({
        "status": pack["status"],
        "families": pack["report"]["families"],
        "paths": pack["paths"],
        "secret_scan": pack["report"].get("secret_scan"),
    }, indent=2, ensure_ascii=False))
    if pack["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
