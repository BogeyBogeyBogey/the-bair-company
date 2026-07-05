#!/usr/bin/env python3
"""
HomePilot campaign compliance audit.

This is not legal advice. It is a machine-checkable preflight for the trust
boundary large renovation customers will care about before using outreach data:
source provenance, contact basis, opt-out handling, retention review, and safe
lead-claim language.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_store import load_payload, validate_payload


CONTACT_BASIS_VALUES = {
    "consent",
    "customer_request",
    "existing_customer_soft_opt_in",
    "legitimate_interest_reviewed",
    "public_business_record",
    "not_for_outreach",
}

OUTREACH_STATUSES = {"queued", "sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
RESPONDED_STATUSES = {"responded", "appointment", "customer"}
UNPROVEN_INTENT_PHRASES = (
    "ready to hire",
    "ready_to_hire",
    "ready to buy",
    "ready_to_buy",
    "requested quote",
    "requested_quote",
    "submitted request",
    "submitted_request",
    "wants quote",
    "wants_quote",
    "buying intent",
    "buying_intent",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _property_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("id")): row for row in payload.get("properties", [])}


def _has_source_provenance(target: dict[str, Any], prop: dict[str, Any] | None) -> bool:
    metadata = _metadata(target)
    if _text(metadata.get("source_provenance") or metadata.get("source")):
        return True
    if prop and _text(prop.get("source_external_id")):
        return True
    if prop and isinstance(prop.get("core"), dict) and _text(prop["core"].get("source")):
        return True
    return False


def _intent_claim(metadata: dict[str, Any]) -> str:
    values = [
        metadata.get("lead_claim"),
        metadata.get("intent_claim"),
        metadata.get("claim"),
        metadata.get("segment_claim"),
    ]
    joined = " ".join(_text(value) for value in values if _text(value))
    return joined.lower()


def _has_response_evidence(payload: dict[str, Any], target: dict[str, Any]) -> bool:
    property_id = target.get("property_id")
    module_key = target.get("module_key")
    campaign_id = target.get("campaign_id")
    for interaction in payload.get("interactions", []):
        if interaction.get("property_id") != property_id:
            continue
        if interaction.get("module_key") != module_key:
            continue
        if campaign_id and interaction.get("campaign_id") not in (campaign_id, None):
            continue
        if interaction.get("response_status") in {"interested", "customer"}:
            return True
        if interaction.get("interaction_type") in {"form_submit", "call", "meeting"}:
            return True
    return False


def _do_not_contact_keys(metadata: dict[str, Any]) -> bool:
    return bool(
        metadata.get("do_not_contact")
        or metadata.get("opted_out")
        or metadata.get("suppressed")
        or _lower(metadata.get("contact_preference")) in {"do_not_contact", "opt_out", "suppressed"}
    )


def _dnc_interactions(payload: dict[str, Any]) -> set[tuple[str, str]]:
    blocked: set[tuple[str, str]] = set()
    for interaction in payload.get("interactions", []):
        if interaction.get("response_status") == "do_not_contact":
            blocked.add((str(interaction.get("property_id")), str(interaction.get("module_key"))))
    return blocked


def build_compliance_report(payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload(payload)
    properties = _property_map(payload)
    dnc_pairs = _dnc_interactions(payload)
    failures: list[str] = []
    warnings: list[str] = []
    contactable_count = 0
    contacted_count = 0
    ready_claim_count = 0
    opt_out_count = 0

    for target in payload.get("campaign_targets", []):
        status = str(target.get("status") or "")
        metadata = _metadata(target)
        prop = properties.get(str(target.get("property_id")))
        label = f"{target.get('property_id')}/{target.get('module_key')}/{target.get('campaign_id')}"

        if status in OUTREACH_STATUSES:
            contactable_count += 1
            basis = _text(metadata.get("contact_basis") or metadata.get("legal_basis"))
            if basis not in CONTACT_BASIS_VALUES:
                failures.append(f"{label}: missing or unsupported contact_basis for outreach status {status}.")
            if not _has_source_provenance(target, prop):
                failures.append(f"{label}: missing source provenance for contactable record.")
            if not _text(metadata.get("contact_channel")):
                warnings.append(f"{label}: missing contact_channel metadata.")
            if not _text(metadata.get("opt_out_method")) and status in CONTACTED_STATUSES:
                warnings.append(f"{label}: missing opt_out_method for contacted record.")
            if not _text(metadata.get("retention_review_at") or metadata.get("delete_after")):
                warnings.append(f"{label}: missing retention_review_at/delete_after metadata.")

        if status in CONTACTED_STATUSES:
            contacted_count += 1

        if _do_not_contact_keys(metadata):
            opt_out_count += 1
            if status in {"queued", "sent", "scanned", "clicked"}:
                failures.append(f"{label}: do_not_contact/opted_out record is still in an outreach status.")

        if (str(target.get("property_id")), str(target.get("module_key"))) in dnc_pairs and not _do_not_contact_keys(metadata):
            failures.append(f"{label}: do_not_contact interaction is not propagated to campaign target metadata.")

        claim = _intent_claim(metadata)
        if claim:
            if any(phrase in claim for phrase in UNPROVEN_INTENT_PHRASES):
                ready_claim_count += 1
                if status not in RESPONDED_STATUSES or not _has_response_evidence(payload, target):
                    failures.append(f"{label}: unproven buying/ready-to-hire intent claim without response evidence.")
            if "opportunity" not in claim and "renovation" not in claim and status not in RESPONDED_STATUSES:
                warnings.append(f"{label}: lead_claim should use opportunity language until response evidence exists.")

    campaigns_without_variant = [
        str(row.get("id"))
        for row in payload.get("campaigns", [])
        if not _text(row.get("message_variant"))
    ]
    for campaign_id in campaigns_without_variant:
        warnings.append(f"{campaign_id}: missing message_variant for campaign learning audit.")

    status = "fail" if failures else ("warn" if warnings else "pass")
    return {
        "report_type": "homepilot_compliance_audit",
        "created_at": utc_now(),
        "status": status,
        "sources": [
            {
                "label": "Belgian Data Protection Authority direct marketing",
                "url": "https://www.gegevensbeschermingsautoriteit.be/professioneel/thema-s/direct-marketing",
            },
            {
                "label": "ICO direct marketing guidance",
                "url": "https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/direct-marketing-guidance/",
            },
            {
                "label": "FTC HomeAdvisor lead marketing order",
                "url": "https://www.ftc.gov/news-events/news/press-releases/2023/04/ftc-approves-final-order-against-homeadvisor-inc-deceptively-marketing-its-leads-home-improvement",
            },
        ],
        "metrics": {
            "campaign_target_count": len(payload.get("campaign_targets", [])),
            "contactable_count": contactable_count,
            "contacted_count": contacted_count,
            "opt_out_count": opt_out_count,
            "unproven_intent_claim_count": ready_claim_count,
            "failure_count": len(failures),
            "warning_count": len(warnings),
        },
        "failures": failures,
        "warnings": warnings,
        "required_metadata": {
            "contactable_records": ["contact_basis", "source_provenance or property.source_external_id", "contact_channel"],
            "contacted_records": ["opt_out_method"],
            "recommended": ["retention_review_at or delete_after", "lead_claim using opportunity language"],
        },
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit HomePilot outreach compliance metadata")
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    report = build_compliance_report(load_payload(args.json))
    write_json(args.out, report)
    print(json.dumps({
        "output": str(args.out),
        "status": report["status"],
        "failures": len(report["failures"]),
        "warnings": len(report["warnings"]),
    }, indent=2, ensure_ascii=False))
    if report["status"] == "fail" or (args.fail_on_warn and report["status"] == "warn"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
