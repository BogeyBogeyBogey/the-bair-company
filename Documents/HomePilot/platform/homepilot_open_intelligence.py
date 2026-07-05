#!/usr/bin/env python3
"""
Build the HomePilot Open Intelligence layer for customer packages.

This is the WPP Open Intelligence idea translated to HomePilot: tenant-scoped
renovation intelligence, model evidence, data-collaboration rules, activation
paths, and outcome learning loops. It is a review artifact only. It does not
write to live systems, start outreach, or claim homeowner buying intent.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENGAGED_STATUSES = {"responded", "appointment", "customer"}
CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                field: " | ".join(str(item) for item in value) if isinstance(value, list) else value
                for field, value in row.items()
                if field in fieldnames
            })


def _number(value: Any, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _best_assessment(prop: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    assessments = prop.get("assessments") if isinstance(prop.get("assessments"), dict) else {}
    if not assessments:
        return "", {}
    return sorted(
        assessments.items(),
        key=lambda item: (_number(item[1].get("score")), _number(prop.get("estimatedValue"))),
        reverse=True,
    )[0]


def _tenant(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("tenant") if isinstance(snapshot.get("tenant"), dict) else {}


def _properties(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return snapshot.get("properties") if isinstance(snapshot.get("properties"), list) else []


def _modules(snapshot: dict[str, Any]) -> list[str]:
    tenant_modules = _tenant(snapshot).get("modules")
    if isinstance(tenant_modules, list) and tenant_modules:
        return [str(module) for module in tenant_modules]
    return sorted({
        module
        for prop in _properties(snapshot)
        for module in (prop.get("assessments") or {})
    })


def _network(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}


def _producer_name(snapshot: dict[str, Any]) -> str:
    producer = _network(snapshot).get("producer")
    if isinstance(producer, dict):
        return str(producer.get("name") or producer.get("id") or "")
    return str(producer or "")


def _is_producer_network(snapshot: dict[str, Any]) -> bool:
    return str(_network(snapshot).get("type") or "") == "producer_partner_network"


def _partner_count(snapshot: dict[str, Any]) -> int:
    partners = _network(snapshot).get("partners")
    return len(partners) if isinstance(partners, list) else 0


def _campaign_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    properties = _properties(snapshot)
    contacted = sum(1 for prop in properties if str(prop.get("status") or "") in CONTACTED_STATUSES)
    engaged = sum(1 for prop in properties if str(prop.get("status") or "") in ENGAGED_STATUSES)
    appointments = sum(1 for prop in properties if str(prop.get("status") or "") in {"appointment", "customer"})
    no_response = sum(1 for prop in properties if str(prop.get("status") or "") == "no_response")
    return {
        "visible_properties": len(properties),
        "contacted_count": contacted,
        "engaged_count": engaged,
        "appointment_count": appointments,
        "no_response_count": no_response,
        "response_rate_pct": _pct(engaged, contacted),
        "appointment_rate_pct": _pct(appointments, contacted),
    }


def _best_score(prop: dict[str, Any]) -> float:
    return _number(_best_assessment(prop)[1].get("score"))


def _best_grade(prop: dict[str, Any]) -> str:
    return str(_best_assessment(prop)[1].get("grade") or "")


def _estimated_value(props: list[dict[str, Any]]) -> int:
    return int(round(sum(_number(prop.get("estimatedValue")) for prop in props)))


def _facade_m2(props: list[dict[str, Any]]) -> int:
    return int(round(sum(_number(prop.get("estimatedFacadeM2")) for prop in props)))


def _activation_counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    properties = _properties(snapshot)
    top = [
        prop for prop in properties
        if _best_grade(prop) in {"A", "A+"} or _best_score(prop) >= 80
    ]
    no_response = [prop for prop in properties if str(prop.get("status") or "") == "no_response"]
    engaged = [prop for prop in properties if str(prop.get("status") or "") in ENGAGED_STATUSES]
    contacted = [prop for prop in properties if str(prop.get("status") or "") in CONTACTED_STATUSES]
    public_context = [
        prop for prop in properties
        if isinstance(prop.get("publicContext"), dict)
        and isinstance(prop["publicContext"].get("features"), list)
        and prop["publicContext"]["features"]
    ]
    return {
        "top_opportunity_count": len(top),
        "top_pipeline_value": _estimated_value(top),
        "top_facade_m2": _facade_m2(top),
        "no_response_count": len(no_response),
        "engaged_count": len(engaged),
        "contacted_count": len(contacted),
        "public_context_count": len(public_context),
        "public_context_coverage_pct": _pct(len(public_context), len(properties)),
    }


def _partner_assignment_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    assignment = snapshot.get("partnerAssignment") if isinstance(snapshot.get("partnerAssignment"), dict) else {}
    rows = assignment.get("best_assignment")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _segment_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    segmentation = snapshot.get("campaignSegmentation") if isinstance(snapshot.get("campaignSegmentation"), dict) else {}
    rows = segmentation.get("best_segments")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _message_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    message = snapshot.get("messageStrategy") if isinstance(snapshot.get("messageStrategy"), dict) else {}
    rows = message.get("best_message_tests")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _first_message_theme(messages: list[dict[str, Any]], segment_key: str | None = None) -> str:
    candidates = [
        row for row in messages
        if not segment_key or str(row.get("segment_key") or "") == str(segment_key)
    ] or messages
    if not candidates:
        return "customer-approved opportunity framing"
    first = candidates[0]
    return str(first.get("subject_theme") or first.get("angle") or "customer-approved opportunity framing")


def _top_segment_label(segments: list[dict[str, Any]]) -> str:
    if not segments:
        return "high-score properties"
    ordered = sorted(
        segments,
        key=lambda row: (_number(row.get("final_score")), _number(row.get("property_count"))),
        reverse=True,
    )
    first = ordered[0]
    return str(first.get("segment_label") or first.get("segment_key") or "reviewable segment")


def _marketing_impact_planner(snapshot: dict[str, Any]) -> dict[str, Any]:
    counts = _activation_counts(snapshot)
    campaign = _campaign_metrics(snapshot)
    assignments = _partner_assignment_rows(snapshot)
    segments = _segment_rows(snapshot)
    messages = _message_rows(snapshot)
    partner_batches = len(assignments)
    segment_label = _top_segment_label(segments)
    message_theme = _first_message_theme(messages, segments[0].get("segment_key") if segments else None)
    properties = _properties(snapshot)
    status = "review_ready" if properties and _modules(snapshot) else "review_required"
    activation_lanes = [
        {
            "lane_key": "priority_queue_activation",
            "audience": "A/A+ and high-score renovation opportunities",
            "recommended_channel": "partner-scoped review queue plus customer-approved first-wave channel",
            "record_count": counts["top_opportunity_count"],
            "decision_use": "Focus DAW and renovator attention on the records with the strongest opportunity evidence.",
            "expected_impact": f"{counts['top_facade_m2']} facade m2 and EUR {counts['top_pipeline_value']} pipeline value in the highest-priority queue.",
            "approval_required": "customer go/no-go, contact basis, suppression, partner capacity, and message approval",
            "measurement_event": "campaign_target_contacted and latest explicit response status",
            "guardrail": "Opportunity score is not homeowner intent.",
        },
        {
            "lane_key": "partner_capacity_routing",
            "audience": "assigned partner territories and capacity waves",
            "recommended_channel": "producer cockpit to partner portal or partner cutdown package",
            "record_count": sum(int(_number(row.get("selected_count"))) for row in assignments) if assignments else len(properties),
            "decision_use": "Route work to the right renovator while preserving partner-only visibility.",
            "expected_impact": f"{partner_batches or _partner_count(snapshot)} partner review batches with partner_id scope enforced.",
            "approval_required": "partner roster, territory assignment, capacity confirmation, and partner Auth/RLS proof",
            "measurement_event": "partner_id, campaign_id, status, response timestamp, and appointment outcome",
            "guardrail": "Partner views must never expose another partner's raw records.",
        },
        {
            "lane_key": "segment_message_match",
            "audience": segment_label,
            "recommended_channel": "approved segment-specific message test",
            "record_count": int(_number(segments[0].get("property_count"))) if segments else counts["top_opportunity_count"],
            "decision_use": "Match the safest message angle to the segment before spending budget or partner time.",
            "expected_impact": f"Message theme under review: {message_theme}.",
            "approval_required": "DAW/legal review of claims, opt-out text, language, and response routing",
            "measurement_event": "segment_key, message_variant, channel, contacted_count denominator, response_count",
            "guardrail": "Draft copy remains review evidence until approved.",
        },
        {
            "lane_key": "no_response_recovery",
            "audience": "contacted records with no explicit response",
            "recommended_channel": "approved follow-up or holdout test",
            "record_count": counts["no_response_count"],
            "decision_use": "Separate real silence from uncontacted inventory and avoid misreading response rate.",
            "expected_impact": f"{counts['no_response_count']} no-response records can become a clean retest cohort.",
            "approval_required": "frequency cap, suppression check, lawful contact basis, and customer go/no-go",
            "measurement_event": "previous_status=no_response, follow_up_variant, new_response_status",
            "guardrail": "Use contacted_count as the denominator, not all generated targets.",
        },
        {
            "lane_key": "source_backed_storytelling",
            "audience": "records with approved public context and evidence references",
            "recommended_channel": "boardroom narrative, sales brief, and proof-led creative review",
            "record_count": counts["public_context_count"],
            "decision_use": "Use source-backed context to explain why a territory or segment is worth attention.",
            "expected_impact": f"{counts['public_context_coverage_pct']}% of visible records include public-context demo coverage.",
            "approval_required": "dataset licence, field allowlist, attribution, and public-data production intake",
            "measurement_event": "source_run_id, feature_key, allowed_use, attribution_status",
            "guardrail": "Public context can support prioritization, not private household intent claims.",
        },
    ]
    channel_mix = [
        {
            "channel": "producer_cockpit",
            "role": "Executive steering and budget focus",
            "recommended_for": "DAW aggregate view, partner comparison, first-wave decisions",
            "blocked_until": "buyer review accepts scope and caveats",
            "measurement_event": "decision_log_entry and approved launch lane",
        },
        {
            "channel": "partner_portal_or_cutdown",
            "role": "Renovator action queue",
            "recommended_for": "partner-scoped assigned records only",
            "blocked_until": "partner membership, Auth mapping, and RLS/customer-access proof pass",
            "measurement_event": "partner_queue_opened, status_update, appointment_created",
        },
        {
            "channel": "approved_direct_mail_or_local_drop",
            "role": "First-wave outreach candidate",
            "recommended_for": "high-score records after lawful contact basis and suppression approval",
            "blocked_until": "message approval, contact basis, opt-out method, suppression, and launch gate",
            "measurement_event": "contacted_count, response_status, message_variant",
        },
        {
            "channel": "reply_capture_landing_page",
            "role": "Response capture and measurement",
            "recommended_for": "QR/URL reply path tied to campaign, segment, partner, and message variant",
            "blocked_until": "privacy copy, analytics scope, and customer-owned routing approval",
            "measurement_event": "reply_event, partner_id, segment_key, consent_status",
        },
        {
            "channel": "call_back_after_response",
            "role": "Conversion follow-up",
            "recommended_for": "responded, appointment, or customer-approved callback records",
            "blocked_until": "explicit response evidence or customer-approved callback basis",
            "measurement_event": "appointment_booked, quoted_project, won_project",
        },
    ]
    measurement_loop = [
        {
            "stage": "pre_wave_baseline",
            "cadence": "before launch gate",
            "owner": "HomePilot operator plus DAW campaign owner",
            "denominator": "visible scoped records",
            "required_fields": ["tenant_id", "module_key", "partner_id", "campaign_id", "segment_key", "message_variant"],
            "pass_condition": "scope, source, suppression, and message approvals are archived",
            "output": "first-wave go/no-go evidence",
        },
        {
            "stage": "contacted_measurement",
            "cadence": "daily during first wave",
            "owner": "campaign operations",
            "denominator": "contacted_count",
            "required_fields": ["channel", "status", "contacted_at", "opt_out_method", "source_provenance"],
            "pass_condition": "response rate never mixes generated and contacted denominators",
            "output": "response-rate and no-response backlog",
        },
        {
            "stage": "partner_effectiveness_review",
            "cadence": "weekly",
            "owner": "DAW network manager",
            "denominator": "partner contacted_count",
            "required_fields": ["partner_id", "assigned_count", "response_count", "appointment_count", "capacity_status"],
            "pass_condition": "partner drilldown stays scoped and leakage count remains zero",
            "output": "partner coaching and next-wave routing",
        },
        {
            "stage": "message_learning_review",
            "cadence": "after each approved wave",
            "owner": "DAW marketing/legal plus HomePilot",
            "denominator": "message_variant contacted_count",
            "required_fields": ["segment_key", "message_variant", "response_status", "objection_theme", "approval_status"],
            "pass_condition": "no forbidden homeowner-intent claims and claims remain source-backed",
            "output": "approved message-learning register",
        },
        {
            "stage": "commercial_outcome_sync",
            "cadence": "monthly after campaign start",
            "owner": "DAW plus partner sales owner",
            "denominator": "appointment_count or customer-approved CRM opportunity count",
            "required_fields": ["appointment_count", "quote_count", "won_project_count", "project_value", "loss_reason"],
            "pass_condition": "commercial outcomes come from customer-approved systems",
            "output": "ROI forecast calibration and next budget decision",
        },
    ]
    return {
        "status": status,
        "planner_type": "marketing_impact_planner",
        "privacy_pattern": {
            "name": "intelligence_beyond_identity",
            "description": "Use tenant, property, partner, segment, and outcome intelligence without building a personal ad-identity graph.",
            "allowed": [
                "tenant-scoped property opportunity signals",
                "partner assignment and capacity signals",
                "approved public-context features with provenance",
                "explicit campaign response and outcome signals",
            ],
            "blocked": [
                "personal ad identity activation",
                "raw cross-tenant learning",
                "owner/contact scraping",
                "homeowner-intent claims without response evidence",
            ],
        },
        "impact_summary": {
            "visible_properties": len(properties),
            "contacted_count": campaign["contacted_count"],
            "top_opportunity_count": counts["top_opportunity_count"],
            "top_pipeline_value": counts["top_pipeline_value"],
            "no_response_count": counts["no_response_count"],
            "partner_batches": partner_batches,
            "segment_count": len(segments),
            "message_test_count": len(messages),
            "public_context_coverage_pct": counts["public_context_coverage_pct"],
        },
        "activation_lanes": activation_lanes,
        "channel_mix": channel_mix,
        "measurement_loop": measurement_loop,
        "review_boundaries": [
            "This planner is a buyer-review artifact, not a media buying platform.",
            "It does not write to Supabase, CRM, ad platforms, mail systems, or partner portals.",
            "Live activation requires customer go/no-go, source approvals, launch gate, and live RLS/customer-access proof.",
        ],
    }


def _source_coverage(snapshot: dict[str, Any]) -> dict[str, Any]:
    trust = snapshot.get("trust") if isinstance(snapshot.get("trust"), dict) else {}
    source_ledger = trust.get("sourceLedger") if isinstance(trust.get("sourceLedger"), dict) else {}
    public_context = trust.get("publicContext") if isinstance(trust.get("publicContext"), dict) else {}
    properties = _properties(snapshot)
    with_public_context = sum(
        1
        for prop in properties
        if isinstance(prop.get("publicContext"), dict)
        and isinstance(prop["publicContext"].get("features"), list)
        and prop["publicContext"]["features"]
    )
    evidence_refs = 0
    for prop in properties:
        for assessment in (prop.get("assessments") or {}).values():
            evidence = assessment.get("evidence") if isinstance(assessment, dict) else []
            evidence_refs += len(evidence) if isinstance(evidence, list) else 0
    return {
        "source_ledger_status": source_ledger.get("status", "not_attached"),
        "source_runs": len(source_ledger.get("source_runs", [])) if isinstance(source_ledger.get("source_runs"), list) else 0,
        "evidence_references": evidence_refs,
        "public_context_records": with_public_context,
        "public_context_coverage_pct": _pct(with_public_context, len(properties)),
        "public_context_summary": public_context,
    }


def _model_name(snapshot: dict[str, Any]) -> str:
    modules = _modules(snapshot)
    tenant = _tenant(snapshot)
    tenant_name = str(tenant.get("name") or tenant.get("id") or "HomePilot")
    if _is_producer_network(snapshot) and "facadepilot" in modules:
        producer = _producer_name(snapshot) or tenant_name
        return f"{producer} Crepi Opportunity Model"
    if len(modules) == 1:
        return f"{tenant_name} {modules[0]} Opportunity Model"
    return f"{tenant_name} Renovation Opportunity Model"


def _model_card(snapshot: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(snapshot)
    modules = _modules(snapshot)
    campaign = _campaign_metrics(snapshot)
    source = _source_coverage(snapshot)
    properties = _properties(snapshot)
    scores = [
        _number(_best_assessment(prop)[1].get("score"))
        for prop in properties
        if _best_assessment(prop)[1]
    ]
    values = [_number(prop.get("estimatedValue")) for prop in properties]
    facade_m2 = [_number(prop.get("estimatedFacadeM2")) for prop in properties]
    return {
        "name": _model_name(snapshot),
        "model_family": "HomePilot Open Intelligence",
        "model_type": "Large Renovation Opportunity Model",
        "status": "buyer_review_ready",
        "tenant": {
            "id": tenant.get("id"),
            "name": tenant.get("name"),
            "modules": modules,
            "producer_network": _is_producer_network(snapshot),
            "producer": _producer_name(snapshot),
            "partner_count": _partner_count(snapshot),
        },
        "business_questions": [
            "Which renovation opportunities deserve action first?",
            "Which partner should receive which work queue?",
            "Which campaign segments and follow-up motions are most defensible?",
            "Which outcome signals should improve future prioritization?",
        ],
        "allowed_decisions": [
            "prioritize opportunity review queues",
            "prepare partner-scoped campaign batches",
            "choose campaign segments and message tests",
            "prepare Excel, CRM, boardroom, and partner handoff artifacts",
        ],
        "prohibited_decisions": [
            "claim homeowner buying intent without response or customer evidence",
            "start live outreach without launch gate approval",
            "grant partner access without tenant/module/partner RLS proof",
            "reuse raw cross-tenant addresses, responses, notes, or campaign learnings",
        ],
        "signals_used": [
            "module opportunity score and grade",
            "estimated opportunity value",
            "visible facade m2 where available",
            "assessment confidence and evidence coverage",
            "campaign status and explicit response history",
            "partner capacity and partner response history",
            "approved public-context features with provenance",
        ],
        "signals_excluded_by_default": [
            "cadastral owner identity",
            "scraped personal contact data",
            "non-public EPC records",
            "raw cross-tenant benchmark rows",
            "free-form notes outside tenant/partner scope",
        ],
        "input_summary": {
            "visible_properties": len(properties),
            "modules": modules,
            "campaigns": len(snapshot.get("campaigns", [])) if isinstance(snapshot.get("campaigns"), list) else 0,
            "average_best_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "estimated_pipeline_value": int(round(sum(values))),
            "estimated_facade_m2": int(round(sum(facade_m2))),
            "evidence_references": source["evidence_references"],
            "public_context_coverage_pct": source["public_context_coverage_pct"],
        },
        "outcome_summary": campaign,
        "review_caveats": [
            "Synthetic demo records must not be presented as production DAW evidence.",
            "Scores are opportunity signals, not homeowner intent.",
            "Production use requires live schema verification, RLS probes, customer access proof, and customer go/no-go.",
            "Public-data imports require dataset-level licence, allowed-use, field allowlist, attribution, and source-run provenance.",
        ],
    }


def _model_lab(snapshot: dict[str, Any]) -> dict[str, Any]:
    graph = {}
    visual = snapshot.get("visualIntelligence") if isinstance(snapshot.get("visualIntelligence"), dict) else {}
    graph_model = visual.get("graph") if isinstance(visual.get("graph"), dict) else {}
    if graph_model:
        graph_research = graph_model.get("layout_research") if isinstance(graph_model.get("layout_research"), dict) else {}
        graph_quality = graph_model.get("layout_quality") if isinstance(graph_model.get("layout_quality"), dict) else {}
        graph = {
            "family": "second_brain_graph_layout",
            "status": "ready" if graph_quality else "baseline_only",
            "best_tag": graph_research.get("best_tag", "baseline"),
            "score": graph_quality.get("final_score"),
            "fit_score": graph_quality.get("fit_score"),
            "evidence_type": "graph readability evidence only",
        }

    lead = snapshot.get("leadPrioritization") if isinstance(snapshot.get("leadPrioritization"), dict) else {}
    lead_quality = lead.get("priority_quality") if isinstance(lead.get("priority_quality"), dict) else {}
    lead_research = lead.get("priority_research") if isinstance(lead.get("priority_research"), dict) else {}
    lead_lab = {
        "family": "lead_prioritization",
        "status": "ready" if lead_quality else "not_run",
        "best_tag": lead_research.get("best_tag"),
        "model": (lead.get("priority_config") or {}).get("model_name") if isinstance(lead.get("priority_config"), dict) else None,
        "baseline_score": lead_research.get("baseline_score"),
        "best_score": lead_quality.get("final_score") or lead_research.get("best_score"),
        "queue_rows": len(lead.get("best_queue", [])) if isinstance(lead.get("best_queue"), list) else 0,
        "evidence_type": "synthetic/demo outcome proxy only",
    }

    assignment = snapshot.get("partnerAssignment") if isinstance(snapshot.get("partnerAssignment"), dict) else {}
    assignment_quality = assignment.get("assignment_quality") if isinstance(assignment.get("assignment_quality"), dict) else {}
    assignment_research = assignment.get("assignment_research") if isinstance(assignment.get("assignment_research"), dict) else {}
    assignment_lab = {
        "family": "partner_assignment",
        "status": "ready" if assignment_quality else "not_run",
        "best_tag": assignment_research.get("best_tag"),
        "strategy": (assignment.get("assignment_config") or {}).get("strategy_name") if isinstance(assignment.get("assignment_config"), dict) else None,
        "baseline_score": assignment_research.get("baseline_score"),
        "best_score": assignment_quality.get("final_score") or assignment_research.get("best_score"),
        "partner_batches": len(assignment.get("best_assignment", [])) if isinstance(assignment.get("best_assignment"), list) else 0,
        "scope_leakage_count": assignment_quality.get("scope_leakage_count"),
        "evidence_type": "partner-scope wave assignment evidence only",
    }

    segmentation = snapshot.get("campaignSegmentation") if isinstance(snapshot.get("campaignSegmentation"), dict) else {}
    segment_quality = segmentation.get("segment_quality") if isinstance(segmentation.get("segment_quality"), dict) else {}
    segment_research = segmentation.get("segment_research") if isinstance(segmentation.get("segment_research"), dict) else {}
    segmentation_lab = {
        "family": "campaign_segmentation",
        "status": "ready" if segment_quality else "not_run",
        "best_tag": segment_research.get("best_tag"),
        "strategy": (segmentation.get("segment_config") or {}).get("strategy_name") if isinstance(segmentation.get("segment_config"), dict) else None,
        "baseline_score": segment_research.get("baseline_score"),
        "best_score": segment_quality.get("final_score") or segment_research.get("best_score"),
        "segment_count": len(segmentation.get("best_segments", [])) if isinstance(segmentation.get("best_segments"), list) else 0,
        "coverage_pct": segment_quality.get("coverage_pct"),
        "response_denominator": segment_quality.get("response_denominator") or segment_research.get("response_denominator"),
        "evidence_type": "campaign segmentation evidence with contacted denominator",
    }

    message = snapshot.get("messageStrategy") if isinstance(snapshot.get("messageStrategy"), dict) else {}
    message_quality = message.get("message_quality") if isinstance(message.get("message_quality"), dict) else {}
    message_research = message.get("message_research") if isinstance(message.get("message_research"), dict) else {}
    message_lab = {
        "family": "message_strategy",
        "status": "ready" if message_quality else "not_run",
        "best_tag": message_research.get("best_tag"),
        "strategy": (message.get("message_config") or {}).get("strategy_name") if isinstance(message.get("message_config"), dict) else None,
        "baseline_score": message_research.get("baseline_score"),
        "best_score": message_quality.get("final_score") or message_research.get("best_score"),
        "message_test_count": len(message.get("best_message_tests", [])) if isinstance(message.get("best_message_tests"), list) else 0,
        "compliance_pass_rate_pct": message_quality.get("compliance_pass_rate_pct"),
        "forbidden_claim_count": message_quality.get("forbidden_claim_count"),
        "response_denominator": message_quality.get("response_denominator") or message_research.get("response_denominator"),
        "evidence_type": "message-strategy draft evidence requiring customer approval",
    }

    next_families = []
    if not assignment_quality:
        next_families.append({
            "family": "partner_assignment",
            "purpose": "Test which partner receives which opportunity queue under capacity and region constraints.",
            "success_metrics": ["partner_balance_score", "appointment_rate_pct", "pipeline_value", "scope_leakage=0"],
        })
    if not segment_quality:
        next_families.append({
            "family": "campaign_segmentation",
            "purpose": "Test territory, property-type, score, no-response, and public-context segments before first-wave outreach.",
            "success_metrics": ["response_rate_pct", "no_response_recovery_pct", "denominator clarity"],
        })
    if not message_quality:
        next_families.append({
            "family": "message_strategy",
            "purpose": "Test safe message angles per segment without claiming homeowner intent.",
            "success_metrics": ["response_rate_pct", "objection_rate", "compliance_pass"],
        })
    return {
        "status": "ready",
        "experiment_families": [row for row in (graph, lead_lab, assignment_lab, segmentation_lab, message_lab) if row],
        "next_experiment_families": next_families,
        "guardrails": {
            "non_mutating": True,
            "winning_models_require_review": True,
            "live_outreach_requires_launch_gate": True,
            "raw_cross_tenant_learning_forbidden": True,
        },
    }


def _data_collaboration_room(snapshot: dict[str, Any]) -> dict[str, Any]:
    tenant = _tenant(snapshot)
    modules = _modules(snapshot)
    producer = _producer_name(snapshot)
    partner_scope = "producer network aggregate plus partner drilldown" if _is_producer_network(snapshot) else "tenant module scope"
    sources = [
        {
            "source": "homepilot_dashboard_snapshot",
            "owner": tenant.get("name") or tenant.get("id") or "tenant",
            "grain": "tenant/module/partner-scoped dashboard rows",
            "allowed_use": "customer dashboard, boardroom report, model card, model lab, exports",
            "blocked_use": "cross-tenant raw learning or homeowner intent claims",
            "scope": partner_scope,
            "status": "attached",
        },
        {
            "source": "homepilot_assessments",
            "owner": "HomePilot + tenant-approved pilot modules",
            "grain": "one property/module assessment",
            "allowed_use": "opportunity score, grade, confidence, evidence, safe metric drivers",
            "blocked_use": "unknown metric exposure or unentitled module handoff",
            "scope": f"enabled modules: {', '.join(modules) or 'none'}",
            "status": "attached",
        },
        {
            "source": "homepilot_campaign_targets_interactions",
            "owner": tenant.get("name") or tenant.get("id") or "tenant",
            "grain": "campaign target and interaction events",
            "allowed_use": "response-rate, appointment, no-response, objection and follow-up learning",
            "blocked_use": "intent claim unless responded, appointment, or customer evidence exists",
            "scope": partner_scope,
            "status": "attached",
        },
        {
            "source": "producer_partner_network",
            "owner": producer or tenant.get("name") or "tenant",
            "grain": "partner assignment, capacity, territory, aggregate partner performance",
            "allowed_use": "producer view and partner-scoped action queues",
            "blocked_use": "partner-to-partner raw record exposure",
            "scope": f"{_partner_count(snapshot)} partner scopes",
            "status": "attached" if _partner_count(snapshot) else "not_applicable",
        },
        {
            "source": "public_context_and_source_ledger",
            "owner": "approved public-data source owner plus tenant review",
            "grain": "source run, geography, feature, property enrichment",
            "allowed_use": "licensed public context, provenance, attribution, coverage review",
            "blocked_use": "owner/contact scraping, non-public EPC, unsupported licence claims",
            "scope": "source licence and field allowlist required",
            "status": "demo_attached" if _source_coverage(snapshot)["public_context_records"] else "approval_required",
        },
    ]
    return {
        "status": "ready_for_buyer_review",
        "collaboration_principle": "Share intelligence and proofs; do not merge raw cross-tenant or partner-private data.",
        "room_scope": {
            "tenant_id": tenant.get("id"),
            "tenant_name": tenant.get("name"),
            "modules": modules,
            "producer_network": _is_producer_network(snapshot),
            "partner_count": _partner_count(snapshot),
        },
        "sources": sources,
        "access_boundaries": [
            "tenant_id is mandatory on customer-visible rows",
            "module_key must match enabled tenant modules",
            "partner_id scopes producer-network partner views",
            "benchmark learning is aggregate-only with minimum cohort thresholds",
            "unknown metrics are hidden from dashboard, export, and benchmark surfaces by default",
        ],
        "approval_gates": [
            "source licence and allowed-use approval",
            "field allowlist and attribution approval",
            "suppression/contact-basis approval before outreach",
            "live schema/RLS/customer-access proof before portal access",
            "explicit customer go/no-go before first wave",
        ],
    }


def _activation_and_outcomes(snapshot: dict[str, Any]) -> dict[str, Any]:
    lead = snapshot.get("leadPrioritization") if isinstance(snapshot.get("leadPrioritization"), dict) else {}
    best_queue = lead.get("best_queue") if isinstance(lead.get("best_queue"), list) else []
    assignment = snapshot.get("partnerAssignment") if isinstance(snapshot.get("partnerAssignment"), dict) else {}
    best_assignment = assignment.get("best_assignment") if isinstance(assignment.get("best_assignment"), list) else []
    segmentation = snapshot.get("campaignSegmentation") if isinstance(snapshot.get("campaignSegmentation"), dict) else {}
    best_segments = segmentation.get("best_segments") if isinstance(segmentation.get("best_segments"), list) else []
    message = snapshot.get("messageStrategy") if isinstance(snapshot.get("messageStrategy"), dict) else {}
    best_message_tests = message.get("best_message_tests") if isinstance(message.get("best_message_tests"), list) else []
    campaign = _campaign_metrics(snapshot)
    return {
        "activation": {
            "status": "review_ready" if best_queue or best_assignment or best_segments or best_message_tests else "baseline_queue_ready",
            "available_surfaces": [
                "customer dashboard priority queue",
                "partner assignment wave plan",
                "campaign segmentation plan",
                "message strategy draft plan",
                "boardroom report",
                "partner cutdown packages",
                "Excel/CSV export",
                "CRM/webhook integration pack",
                "first-campaign launch gate",
            ],
            "recommended_first_actions": [
                "review model card and data collaboration room with DAW",
                "confirm partner roster, territory assignment, capacity, suppression, and message approval",
                "review autoresearched partner wave plan before any live outreach",
                "review segmentation evidence and keep contacted denominators explicit",
                "review message-strategy drafts with DAW/legal before any live outreach",
                "run partner-scoped queue review before any live outreach",
                "require live proof and explicit go/no-go before first wave",
            ],
            "autoresearched_queue_rows": len(best_queue),
            "autoresearched_partner_batches": len(best_assignment),
            "autoresearched_segments": len(best_segments),
            "autoresearched_message_tests": len(best_message_tests),
            "partner_assignment_status": "review_ready" if best_assignment else "not_run",
            "campaign_segmentation_status": "review_ready" if best_segments else "not_run",
            "message_strategy_status": "review_ready" if best_message_tests else "not_run",
        },
        "outcomes": {
            "status": "demo_proxy_ready",
            "current_snapshot_metrics": campaign,
            "learning_loop_metrics": [
                "contacted_count",
                "response_count",
                "response_rate_pct with contacted denominator",
                "appointment_count",
                "appointment_rate_pct with contacted denominator",
                "no_response_backlog",
                "partner pipeline value",
                "partner response rate",
                "cost per appointment once campaign costs are provided",
                "revenue or won-project outcome once customer systems provide it",
            ],
            "caveat": "Demo response statuses are synthetic until replaced by customer-approved live outcomes.",
        },
    }


def _evidence_passed(production_evidence: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = production_evidence.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.lower() in {"pass", "go", "verified", "approved", "production_verified"}:
            return True
        if isinstance(value, dict):
            if value.get("production_verified") is True or value.get("verified") is True:
                return True
            if str(value.get("status") or "").lower() in {"pass", "go", "verified", "approved", "production_verified"}:
                return True
            if str(value.get("decision") or "").lower() in {"go", "approved"}:
                return True
    return False


def _production_gate_row(
    gate_key: str,
    label: str,
    stage: str,
    buyer_review_ok: bool,
    production_ok: bool,
    owner: str,
    evidence: list[str],
    pass_condition: str,
    blocked_until: str,
    guardrail: str,
    *,
    production_required: bool = True,
) -> dict[str, Any]:
    return {
        "gate_key": gate_key,
        "label": label,
        "stage": stage,
        "buyer_review_status": "pass" if buyer_review_ok else "blocked",
        "production_status": "pass" if production_ok else ("blocked_until_live_proof" if production_required else "not_required"),
        "owner": owner,
        "evidence": evidence,
        "pass_condition": pass_condition,
        "blocked_until": "" if production_ok else blocked_until,
        "guardrail": guardrail,
        "production_required": production_required,
    }


def _production_gate(
    snapshot: dict[str, Any],
    room: dict[str, Any],
    planner: dict[str, Any],
    activation_outcomes: dict[str, Any],
    production_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = production_evidence or {}
    tenant = _tenant(snapshot)
    modules = _modules(snapshot)
    properties = _properties(snapshot)
    source = _source_coverage(snapshot)
    measurement_loop = planner.get("measurement_loop") if isinstance(planner.get("measurement_loop"), list) else []
    activation_lanes = planner.get("activation_lanes") if isinstance(planner.get("activation_lanes"), list) else []
    room_sources = room.get("sources") if isinstance(room.get("sources"), list) else []
    contacted_denominator_ok = any(str(row.get("denominator") or "") == "contacted_count" for row in measurement_loop)
    commercial_sync_defined = any(str(row.get("stage") or "") == "commercial_outcome_sync" for row in measurement_loop)
    live_schema_verified = _evidence_passed(evidence, "live_schema_verification", "schema_verification", "schema_verified")
    rls_verified = _evidence_passed(evidence, "rls_customer_access", "customer_access_verification", "rls_verified")
    partner_rls_verified = _evidence_passed(evidence, "partner_access_verification", "partner_rls_verified", "partner_access")
    customer_go = _evidence_passed(evidence, "customer_go_no_go", "signed_customer_approval", "first_wave_go_no_go")
    launch_gate = _evidence_passed(evidence, "launch_gate", "first_wave_launch_gate", "live_launch_gate")
    source_approval = _evidence_passed(evidence, "public_data_approvals", "source_licence_approvals", "field_allowlist_approved")
    outcome_sync = _evidence_passed(evidence, "outcome_sync", "crm_outcome_sync", "commercial_outcome_sync")
    monitoring = _evidence_passed(evidence, "monitoring", "audit_events", "observability")

    scope_ok = bool(tenant.get("id") and modules and properties)
    partner_scope_ok = not _is_producer_network(snapshot) or _partner_count(snapshot) > 0
    data_room_ok = (
        room.get("status") == "ready_for_buyer_review"
        and len(room_sources) >= 4
        and len(room.get("access_boundaries") or []) >= 4
    )
    planner_ok = planner.get("status") == "review_ready" and len(activation_lanes) >= 5
    measurement_ok = contacted_denominator_ok and commercial_sync_defined
    public_data_review_ok = any(row.get("source") == "public_context_and_source_ledger" for row in room_sources)
    activation_ready = activation_outcomes["activation"]["status"] in {"review_ready", "baseline_queue_ready"}

    rows = [
        _production_gate_row(
            "tenant_module_scope_contract",
            "Tenant and module scope contract",
            "buyer_review",
            scope_ok,
            live_schema_verified and rls_verified,
            "IT/security owner + analytics owner",
            ["open_intelligence.json", "DATA_PLATFORM_BLUEPRINT.md", "live_schema_verification.json"],
            "Tenant id, enabled modules, and visible scoped properties are present; live schema and RLS proof pass.",
            "live schema verification and customer RLS probe",
            "Every customer-visible row must stay tenant- and module-scoped.",
        ),
        _production_gate_row(
            "partner_scope_contract",
            "Producer and partner access contract",
            "live_launch",
            partner_scope_ok,
            (not _is_producer_network(snapshot)) or (rls_verified and partner_rls_verified),
            "DAW network manager + IT/security owner",
            ["partner_cutdown_manifest.json", "CUSTOMER_ACCESS_PLAN.md", "customer_access_verification.json"],
            "Producer can review aggregate and partner drilldown; partner identities only see assigned records in live RLS.",
            "partner Auth mapping plus partner-scoped RLS/customer-access proof",
            "A renovator must never see another partner's raw records.",
        ),
        _production_gate_row(
            "data_collaboration_contract",
            "Data collaboration room contract",
            "buyer_review",
            data_room_ok,
            data_room_ok and live_schema_verified and source_approval,
            "Legal/privacy owner + data owner",
            ["OPEN_INTELLIGENCE.md", "PUBLIC_DATA_PRODUCTION_INTAKE.md", "SOURCE_LEDGER.md"],
            "Allowed and blocked uses are documented; approved sources have licence, field allowlist, attribution, and provenance.",
            "dataset approval, field allowlist, attribution, and source-run provenance",
            "Share intelligence and proofs, not raw cross-tenant or partner-private data.",
        ),
        _production_gate_row(
            "activation_control_contract",
            "Activation and outreach authorization contract",
            "live_launch",
            planner_ok and activation_ready,
            customer_go and launch_gate,
            "DAW campaign owner + customer success",
            ["MARKETING_IMPACT_PLANNER.csv", "FIRST_WAVE_LAUNCH_GATE.md", "MESSAGE_APPROVAL_TEMPLATE.csv"],
            "Activation lanes are reviewable and live outreach is authorized only by customer go/no-go plus launch gate.",
            "customer go/no-go, contact basis, suppression, partner capacity, and message approval",
            "Open Intelligence may recommend actions, but it must not start outreach by itself.",
        ),
        _production_gate_row(
            "measurement_contract",
            "Marketing impact measurement contract",
            "buyer_review",
            measurement_ok,
            measurement_ok and outcome_sync,
            "Analyst + CRM owner",
            ["MEASUREMENT_LOOP.csv", "OUTCOME_MEASUREMENT_CONTRACT.md", "OUTCOME_IMPORT_VALIDATION.md"],
            "Contacted denominators, partner review, message learning, and commercial outcomes are defined and live outcome sync is proven.",
            "customer-approved outcome source and live outcome-sync proof",
            "Response rates must use contacted_count as denominator unless explicitly labelled otherwise.",
        ),
        _production_gate_row(
            "public_data_contract",
            "Public-data production contract",
            "buyer_review",
            public_data_review_ok,
            source_approval and (source["public_context_records"] == 0 or live_schema_verified),
            "Legal/privacy owner + data owner",
            ["PUBLIC_DATA_SOURCE_REGISTER.md", "PUBLIC_DATA_APPROVAL_CHECKLIST.csv", "PUBLIC_DATA_RECONCILIATION.md"],
            "Every public source has approved licence, allowed use, attribution, retrieval date, transform owner, and field allowlist.",
            "dataset-level approval and live source-run provenance",
            "Public context can support prioritization; it cannot become private homeowner-intent proof.",
        ),
        _production_gate_row(
            "outcome_learning_contract",
            "Closed-loop outcome learning contract",
            "production",
            commercial_sync_defined,
            outcome_sync,
            "DAW/partner CRM owner + analyst",
            ["OUTCOME_EVENT_SCHEMA.csv", "OUTCOME_SYNC_TEMPLATE.csv", "OUTCOME_RECONCILIATION_CHECKLIST.csv"],
            "Appointments, quotes, won/lost projects, value, and loss reasons can be reconciled from customer-approved systems.",
            "live customer CRM/sheet outcome sync and reconciliation proof",
            "Commercial outcome learning must remain tenant-private unless explicitly aggregated and approved.",
        ),
        _production_gate_row(
            "observability_audit_contract",
            "Production observability and audit contract",
            "production",
            True,
            monitoring,
            "Operator + support owner",
            ["audit_events.json", "MONITORING_STATUS.md", "INCIDENT_RESPONSE_PLAYBOOK.md"],
            "Access, package generation, exports, activation decisions, and outcome syncs produce audit events and monitoring evidence.",
            "live monitoring, audit-event retention, support SLA, and incident response proof",
            "Production is operated through evidence, not memory or meeting notes.",
        ),
    ]
    buyer_blockers = [row for row in rows if row["buyer_review_status"] != "pass"]
    production_blockers = [
        row for row in rows
        if row["production_required"] and row["production_status"] != "pass"
    ]
    status = (
        "production_ready"
        if not buyer_blockers and not production_blockers
        else "buyer_review_ready_live_proof_required"
        if not buyer_blockers
        else "review_required"
    )
    return {
        "status": status,
        "production_ready": status == "production_ready",
        "live_launch_ready": status == "production_ready",
        "buyer_review_ready": not buyer_blockers,
        "gate_count": len(rows),
        "buyer_review_pass_count": len(rows) - len(buyer_blockers),
        "production_blocker_count": len(production_blockers),
        "required_live_proof_count": len(production_blockers),
        "production_blockers": [row["gate_key"] for row in production_blockers],
        "required_live_proofs": [
            {
                "gate_key": row["gate_key"],
                "blocked_until": row["blocked_until"],
                "owner": row["owner"],
            }
            for row in production_blockers
        ],
        "gates": rows,
        "guardrails": {
            "non_mutating": True,
            "no_live_writes": True,
            "no_outreach_authorization": True,
            "no_raw_contact_data": True,
            "tenant_module_partner_scope_required": True,
            "production_requires_live_schema_rls_customer_access_and_outcome_proof": True,
        },
    }


def _boardroom_brief(
    snapshot: dict[str, Any],
    model: dict[str, Any],
    lab: dict[str, Any],
    room: dict[str, Any],
    planner: dict[str, Any],
    activation_outcomes: dict[str, Any],
    issues: list[str],
) -> dict[str, Any]:
    impact = planner["impact_summary"]
    metrics = activation_outcomes["outcomes"]["current_snapshot_metrics"]
    partner_count = model["tenant"]["partner_count"]
    top_facade_m2 = next(
        (lane["expected_impact"] for lane in planner["activation_lanes"] if lane["lane_key"] == "priority_queue_activation"),
        "highest-priority queue evidence attached",
    )
    decision_questions = [
        {
            "decision_key": "where_to_focus_first_wave",
            "boardroom_question": "Which opportunities should DAW and the renovator network review first?",
            "what_daw_learns": f"{impact['top_opportunity_count']} high-priority records, with {top_facade_m2}",
            "evidence": "model_card.input_summary; MARKETING_IMPACT_PLANNER.csv; lead_prioritization evidence",
            "recommended_action": "Approve a scoped first-wave review queue, then keep outreach blocked until launch proof is archived.",
            "owner": "DAW marketing lead + HomePilot operator",
            "blocked_until": "customer go/no-go, contact basis, suppression, partner capacity, message approval, and live proof",
            "customer_visible_metric": "top_opportunity_count, top_pipeline_value, top_facade_m2",
            "guardrail": "Opportunity score is not homeowner intent.",
        },
        {
            "decision_key": "which_partner_gets_which_work",
            "boardroom_question": "How should DAW split opportunities across partner renovators?",
            "what_daw_learns": f"{partner_count} partner scopes and {impact['partner_batches']} autoresearched partner batches are reviewable.",
            "evidence": "data_collaboration_room; partner_assignment evidence; partner cutdown leakage audit",
            "recommended_action": "Review partner wave balance, capacity, and territory fit before partner portal access.",
            "owner": "DAW network manager",
            "blocked_until": "partner roster, Supabase Auth mapping, partner membership review, RLS proof, and customer access proof",
            "customer_visible_metric": "partner_batches, assigned_count, partner response rate, leakage_count",
            "guardrail": "A partner may only see assigned records.",
        },
        {
            "decision_key": "which_message_and_segment_to_test",
            "boardroom_question": "Which campaign segment and message angle should DAW test first?",
            "what_daw_learns": f"{impact['segment_count']} segments and {impact['message_test_count']} message tests are available for review.",
            "evidence": "campaign_segmentation evidence; message_strategy evidence; MEASUREMENT_LOOP.csv",
            "recommended_action": "Approve one segment-message pair and keep denominators tied to contacted records.",
            "owner": "DAW marketing/legal + HomePilot customer success",
            "blocked_until": "legal claim review, opt-out text, language approval, response routing, and launch gate",
            "customer_visible_metric": "segment_count, message_test_count, contacted_count denominator, response_rate_pct",
            "guardrail": "Draft copy is review evidence until explicitly approved.",
        },
        {
            "decision_key": "how_to_measure_marketing_impact",
            "boardroom_question": "How will DAW know if the campaign is working?",
            "what_daw_learns": f"Current synthetic contacted response rate is {metrics['response_rate_pct']}%, with {metrics['no_response_count']} no-response records.",
            "evidence": "MEASUREMENT_LOOP.csv; campaign metrics; customer-approved CRM outcome sync",
            "recommended_action": "Agree the first-wave measurement loop before spending partner time or budget.",
            "owner": "DAW campaign owner + analyst",
            "blocked_until": "response capture, CRM outcome fields, customer-owned routing, and denominator approval",
            "customer_visible_metric": "contacted_count, response_count, appointment_count, no_response_count",
            "guardrail": "Response rates must never mix generated and contacted denominators.",
        },
        {
            "decision_key": "which_data_can_be_used_safely",
            "boardroom_question": "Which data can DAW use safely in prioritization and storytelling?",
            "what_daw_learns": f"{impact['public_context_coverage_pct']}% synthetic public-context coverage is attached for demo review.",
            "evidence": "data_collaboration_room; PUBLIC_DATA_SOURCE_REGISTER.md; PUBLIC_DATA_RECONCILIATION.md",
            "recommended_action": "Approve source licences, field allowlists, attribution, and blocked-data rules before production import.",
            "owner": "DAW legal/privacy + HomePilot operator",
            "blocked_until": "dataset approval, allowed-use review, attribution, source-run provenance, and live proof",
            "customer_visible_metric": "public_context_coverage_pct, source_run_count, attribution_status",
            "guardrail": "Public context supports prioritization, not private household intent claims.",
        },
    ]
    proof_stack = [
        {
            "proof_key": "model_card",
            "artifact": "OPEN_INTELLIGENCE.md",
            "use": "Explains the model family, allowed decisions, prohibited decisions, signals used, and caveats.",
            "status": model["status"],
        },
        {
            "proof_key": "decision_matrix",
            "artifact": "OPEN_INTELLIGENCE_DECISION_MATRIX.csv",
            "use": "Excel-ready boardroom decision table for DAW, partner, message, measurement, and data-governance decisions.",
            "status": "ready",
        },
        {
            "proof_key": "impact_planner",
            "artifact": "MARKETING_IMPACT_PLANNER.csv",
            "use": "Turns opportunity, partner, segment, message, and source evidence into activation lanes without launching outreach.",
            "status": planner["status"],
        },
        {
            "proof_key": "measurement_loop",
            "artifact": "MEASUREMENT_LOOP.csv",
            "use": "Keeps contacted denominators, partner review, message learning, and commercial outcome sync explicit.",
            "status": "ready",
        },
        {
            "proof_key": "open_intelligence_production_gate",
            "artifact": "OPEN_INTELLIGENCE_PRODUCTION_GATE.md",
            "use": "Turns the Open Intelligence idea into explicit buyer-review, live-launch, production, owner, proof, and blocker gates.",
            "status": "buyer_review_ready_live_proof_required",
        },
        {
            "proof_key": "model_lab",
            "artifact": "INTELLIGENCE_LAB.md",
            "use": "Shows autoresearch evidence for lead priority, partner waves, segmentation, and message strategy.",
            "status": lab["status"],
        },
        {
            "proof_key": "live_proof",
            "artifact": "LIVE_PROOF_EXECUTION_PLAN.md",
            "use": "Shows what must be proven before production activation, partner access, or outreach.",
            "status": "blocked_until_live_inputs",
        },
    ]
    return {
        "status": "boardroom_ready" if not issues else "review_required",
        "brief_type": "open_intelligence_boardroom_brief",
        "executive_takeaway": (
            "HomePilot can give DAW a producer-level intelligence cockpit for crepi opportunities, "
            "partner routing, campaign learning, and safe activation planning while keeping live outreach "
            "blocked until customer approval and production proof are complete."
        ),
        "summary": {
            "tenant": model["tenant"]["name"],
            "model": model["name"],
            "visible_properties": impact["visible_properties"],
            "top_opportunity_count": impact["top_opportunity_count"],
            "partner_count": partner_count,
            "partner_batches": impact["partner_batches"],
            "segment_count": impact["segment_count"],
            "message_test_count": impact["message_test_count"],
            "contacted_count": metrics["contacted_count"],
            "response_rate_pct": metrics["response_rate_pct"],
            "launch_position": "buyer_review_ready_live_launch_blocked",
        },
        "decision_questions": decision_questions,
        "proof_stack": proof_stack,
        "meeting_sequence": [
            "Confirm the model scope and tenant/module/partner access boundaries.",
            "Review the five decision questions and choose which ones belong in the first DAW pilot.",
            "Review the impact planner and measurement loop before any channel or partner activation.",
            "Assign live-proof, source-approval, message-approval, and customer go/no-go owners.",
            "Keep production, partner access, public-data import, and outreach blocked until live proof passes.",
        ],
        "guardrails": {
            "brief_is_not_metric_source": True,
            "no_raw_addresses": True,
            "no_secret_values": True,
            "no_live_writes": True,
            "no_outreach_authorization": True,
            "production_requires_live_proof": True,
        },
    }


def build_open_intelligence(snapshot: dict[str, Any], production_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    issues = []
    if not _properties(snapshot):
        issues.append("No visible tenant-scoped properties available.")
    if not _modules(snapshot):
        issues.append("No enabled modules available.")
    if _is_producer_network(snapshot) and not _partner_count(snapshot):
        issues.append("Producer-network snapshot has no partner rows.")
    activation_outcomes = _activation_and_outcomes(snapshot)
    model_card = _model_card(snapshot)
    model_lab = _model_lab(snapshot)
    data_room = _data_collaboration_room(snapshot)
    planner = _marketing_impact_planner(snapshot)
    production_gate = _production_gate(snapshot, data_room, planner, activation_outcomes, production_evidence)
    boardroom_brief = _boardroom_brief(
        snapshot,
        model_card,
        model_lab,
        data_room,
        planner,
        activation_outcomes,
        issues,
    )
    return {
        "report_type": "homepilot_open_intelligence",
        "created_at": utc_now(),
        "status": "pass" if not issues else "review",
        "positioning": {
            "category": "property intelligence for renovation opportunities",
            "inspiration": "Open Intelligence pattern translated to renovation, not adtech identity activation.",
            "promise": "Connect property signals, partner capacity, public context, campaign learning, and audited activation paths.",
        },
        "tenant": {
            "id": _tenant(snapshot).get("id"),
            "name": _tenant(snapshot).get("name"),
            "modules": _modules(snapshot),
        },
        "model_card": model_card,
        "model_lab": model_lab,
        "data_collaboration_room": data_room,
        "marketing_impact_planner": planner,
        "production_gate": production_gate,
        "boardroom_brief": boardroom_brief,
        "activation": activation_outcomes["activation"],
        "outcomes": activation_outcomes["outcomes"],
        "guardrails": {
            "tenant_scoped": True,
            "module_scoped": True,
            "partner_scoped_for_producer_networks": True,
            "no_homeowner_intent_without_response_or_customer_evidence": True,
            "no_live_writes": True,
            "no_supabase_mutation": True,
            "no_outreach_without_launch_gate": True,
            "production_gate_required": True,
            "synthetic_demo_must_be_labelled": True,
            "public_data_requires_licence_and_allowed_use": True,
        },
        "issues": issues,
    }


def _markdown_value(value: Any) -> str:
    if value is None:
        return "not available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    model = report["model_card"]
    lab = report["model_lab"]
    room = report["data_collaboration_room"]
    planner = report["marketing_impact_planner"]
    impact = planner["impact_summary"]
    lines = [
        "# HomePilot Open Intelligence",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Tenant: {report['tenant'].get('name') or report['tenant'].get('id')}",
        f"Model: {model['name']}",
        "",
        "## Positioning",
        "",
        f"- Category: {report['positioning']['category']}",
        f"- Promise: {report['positioning']['promise']}",
        f"- Boundary: {report['positioning']['inspiration']}",
        "",
        "## Model Card",
        "",
        f"- Type: {model['model_type']}",
        f"- Producer network: {_markdown_value(model['tenant']['producer_network'])}",
        f"- Partner count: {model['tenant']['partner_count']}",
        f"- Visible properties: {model['input_summary']['visible_properties']}",
        f"- Average best score: {model['input_summary']['average_best_score']}",
        f"- Estimated pipeline value: EUR {model['input_summary']['estimated_pipeline_value']:,}".replace(",", " "),
        f"- Public-context coverage: {model['input_summary']['public_context_coverage_pct']}%",
        "",
        "Allowed decisions:",
    ]
    for item in model["allowed_decisions"]:
        lines.append(f"- {item}")
    lines += ["", "Prohibited decisions:"]
    for item in model["prohibited_decisions"]:
        lines.append(f"- {item}")
    lines += ["", "## Model Lab", ""]
    for family in lab["experiment_families"]:
        score = family.get("best_score", family.get("score"))
        lines.append(f"- `{family['family']}`: {family['status']}, score {score}, evidence {family['evidence_type']}")
    lines += ["", "Next experiment families:"]
    for family in lab["next_experiment_families"]:
        lines.append(f"- `{family['family']}`: {family['purpose']}")
    lines += ["", "## Data Collaboration Room", ""]
    lines.append(f"Principle: {room['collaboration_principle']}")
    lines.append("")
    for source in room["sources"]:
        lines.append(f"- `{source['source']}`: {source['allowed_use']} / status {source['status']}")
    lines += ["", "Access boundaries:"]
    for boundary in room["access_boundaries"]:
        lines.append(f"- {boundary}")
    lines += ["", "## Marketing Impact Planner", ""]
    lines.append(f"- Status: {planner['status']}")
    lines.append(f"- Privacy pattern: {planner['privacy_pattern']['name']}")
    lines.append(f"- Top opportunities: {impact['top_opportunity_count']}")
    lines.append(f"- No-response backlog: {impact['no_response_count']}")
    lines.append(f"- Partner batches: {impact['partner_batches']}")
    lines.append(f"- Segment count: {impact['segment_count']}")
    lines.append(f"- Message tests: {impact['message_test_count']}")
    lines.append("")
    lines.append("Activation lanes:")
    for lane in planner["activation_lanes"]:
        lines.append(
            f"- `{lane['lane_key']}`: {lane['record_count']} records via {lane['recommended_channel']} "
            f"/ approval {lane['approval_required']}"
        )
    lines.append("")
    lines.append("Channel mix:")
    for channel in planner["channel_mix"]:
        lines.append(f"- `{channel['channel']}`: {channel['role']} / blocked until {channel['blocked_until']}")
    lines.append("")
    lines.append("Measurement loop:")
    for stage in planner["measurement_loop"]:
        lines.append(f"- `{stage['stage']}`: denominator {stage['denominator']} / output {stage['output']}")
    production_gate = report.get("production_gate") or {}
    lines += ["", "## Production Gate", ""]
    lines.append(f"- Status: {production_gate.get('status')}")
    lines.append(f"- Buyer-review ready: {_markdown_value(production_gate.get('buyer_review_ready'))}")
    lines.append(f"- Production ready: {_markdown_value(production_gate.get('production_ready'))}")
    lines.append(f"- Production blockers: {production_gate.get('production_blocker_count')}")
    for gate in production_gate.get("gates") or []:
        lines.append(
            f"- `{gate['gate_key']}`: buyer {gate['buyer_review_status']} / "
            f"production {gate['production_status']} / owner {gate['owner']}"
        )
    lines += ["", "## Activation And Outcomes", ""]
    lines.append(f"- Activation status: {report['activation']['status']}")
    lines.append(f"- Autoresearched queue rows: {report['activation']['autoresearched_queue_rows']}")
    lines.append(f"- Autoresearched partner batches: {report['activation'].get('autoresearched_partner_batches', 0)}")
    lines.append(f"- Autoresearched segments: {report['activation'].get('autoresearched_segments', 0)}")
    lines.append(f"- Autoresearched message tests: {report['activation'].get('autoresearched_message_tests', 0)}")
    lines.append(f"- Outcome status: {report['outcomes']['status']}")
    metrics = report["outcomes"]["current_snapshot_metrics"]
    lines.append(f"- Response rate: {metrics['response_rate_pct']}%")
    lines.append(f"- Appointment rate: {metrics['appointment_rate_pct']}%")
    lines += ["", "## Guardrails", ""]
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    if report["issues"]:
        lines += ["", "## Issues", ""]
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def render_production_gate_markdown(report: dict[str, Any]) -> str:
    gate = report["production_gate"]
    lines = [
        "# HomePilot Open Intelligence Production Gate",
        "",
        f"Created: {report['created_at']}",
        f"Status: {gate['status']}",
        f"Buyer-review ready: {_markdown_value(gate['buyer_review_ready'])}",
        f"Production ready: {_markdown_value(gate['production_ready'])}",
        f"Production blockers: {gate['production_blocker_count']}",
        "",
        "## Executive Meaning",
        "",
        (
            "Open Intelligence is packaged as a production-controlled intelligence layer: it can support "
            "boardroom review, partner routing, segment planning, message review, and outcome measurement, "
            "but live access, outreach, public-data import, and outcome learning remain blocked until the "
            "listed live proofs pass."
        ),
        "",
        "## Gates",
        "",
        "| Gate | Stage | Buyer review | Production | Owner | Blocked until | Guardrail |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in gate["gates"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["label"]),
                    str(row["stage"]),
                    str(row["buyer_review_status"]),
                    str(row["production_status"]),
                    str(row["owner"]),
                    str(row["blocked_until"] or "none"),
                    str(row["guardrail"]),
                ]
            )
            + " |"
        )
    lines += ["", "## Required Live Proofs", ""]
    for proof in gate["required_live_proofs"]:
        lines.append(f"- `{proof['gate_key']}`: {proof['blocked_until']} / owner {proof['owner']}")
    lines += ["", "## Guardrails", ""]
    for key, value in gate["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    lines.append("")
    return "\n".join(lines)


def render_production_runbook(report: dict[str, Any]) -> str:
    gate = report["production_gate"]
    lines = [
        "# HomePilot Open Intelligence Production Runbook",
        "",
        f"Created: {report['created_at']}",
        f"Gate status: {gate['status']}",
        "",
        "## Operating Sequence",
        "",
        "1. Review the Open Intelligence model card, data collaboration room, impact planner, and measurement loop.",
        "2. Confirm tenant, module, producer, partner, campaign, source, and metric scopes with DAW.",
        "3. Apply the database schema only through the SQL apply plan and post-apply verification.",
        "4. Run live schema verification, RLS/customer-access probes, and partner-access probes with approved credentials.",
        "5. Collect customer go/no-go, message approval, contact basis, suppression proof, partner capacity, and launch-gate approval.",
        "6. Start live activation only after the first-wave launch gate is authorized.",
        "7. Sync outcomes only from customer-approved CRM/sheet systems and reconcile appointment, quote, won/lost, value, and loss-reason fields.",
        "8. Archive production proof, monitoring, audit events, and incident-response ownership before scale decisions.",
        "",
        "## Gate Owners And Evidence",
        "",
        "| Gate | Owner | Evidence | Pass condition |",
        "| --- | --- | --- | --- |",
    ]
    for row in gate["gates"]:
        evidence = ", ".join(str(item) for item in row["evidence"])
        lines.append(
            f"| {row['gate_key']} | {row['owner']} | {evidence} | {row['pass_condition']} |"
        )
    lines += ["", "## Non-Negotiables", ""]
    for row in gate["gates"]:
        lines.append(f"- {row['gate_key']}: {row['guardrail']}")
    lines.append("")
    return "\n".join(lines)


def render_boardroom_brief(report: dict[str, Any]) -> str:
    brief = report["boardroom_brief"]
    summary = brief["summary"]
    lines = [
        "# HomePilot Open Intelligence Boardroom Brief",
        "",
        f"Created: {report['created_at']}",
        f"Status: {brief['status']}",
        f"Tenant: {summary.get('tenant')}",
        f"Model: {summary.get('model')}",
        "",
        "## Executive Takeaway",
        "",
        brief["executive_takeaway"],
        "",
        "## Decision Snapshot",
        "",
        f"- Visible properties: {summary['visible_properties']}",
        f"- Top opportunities: {summary['top_opportunity_count']}",
        f"- Partner scopes: {summary['partner_count']}",
        f"- Partner batches: {summary['partner_batches']}",
        f"- Segments: {summary['segment_count']}",
        f"- Message tests: {summary['message_test_count']}",
        f"- Contacted count: {summary['contacted_count']}",
        f"- Response rate: {summary['response_rate_pct']}%",
        f"- Launch position: {summary['launch_position']}",
        "",
        "## Boardroom Decision Matrix",
        "",
        "| Decision | What DAW learns | Recommended action | Blocked until | Guardrail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for decision in brief["decision_questions"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(decision["boardroom_question"]),
                    str(decision["what_daw_learns"]),
                    str(decision["recommended_action"]),
                    str(decision["blocked_until"]),
                    str(decision["guardrail"]),
                ]
            )
            + " |"
        )
    lines += ["", "## Proof Stack", ""]
    for proof in brief["proof_stack"]:
        lines.append(f"- `{proof['artifact']}`: {proof['use']} / status {proof['status']}")
    lines += ["", "## Meeting Sequence", ""]
    for index, step in enumerate(brief["meeting_sequence"], start=1):
        lines.append(f"{index}. {step}")
    lines += ["", "## Guardrails", ""]
    for key, value in brief["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    lines.append("")
    return "\n".join(lines)


def _secret_scan(paths: list[Path]) -> list[str]:
    markers = ("service-role", "secret-token", "authorization: bearer", "supabase_service_role", "@example.")
    findings = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in markers:
            if marker in body:
                findings.append(f"{path.name}: contains {marker}")
    return findings


def build_open_intelligence_pack(
    out_dir: Path,
    snapshot: dict[str, Any],
    production_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_open_intelligence(snapshot, production_evidence=production_evidence)
    json_path = out_dir / "open_intelligence.json"
    markdown_path = out_dir / "OPEN_INTELLIGENCE.md"
    boardroom_brief_path = out_dir / "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md"
    decision_matrix_path = out_dir / "OPEN_INTELLIGENCE_DECISION_MATRIX.csv"
    impact_csv_path = out_dir / "MARKETING_IMPACT_PLANNER.csv"
    measurement_csv_path = out_dir / "MEASUREMENT_LOOP.csv"
    production_gate_path = out_dir / "OPEN_INTELLIGENCE_PRODUCTION_GATE.md"
    production_gates_csv_path = out_dir / "OPEN_INTELLIGENCE_PRODUCTION_GATES.csv"
    production_runbook_path = out_dir / "OPEN_INTELLIGENCE_PRODUCTION_RUNBOOK.md"
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    boardroom_brief_path.write_text(render_boardroom_brief(report), encoding="utf-8")
    production_gate_path.write_text(render_production_gate_markdown(report), encoding="utf-8")
    production_runbook_path.write_text(render_production_runbook(report), encoding="utf-8")
    write_csv(decision_matrix_path, report["boardroom_brief"]["decision_questions"], [
        "decision_key",
        "boardroom_question",
        "what_daw_learns",
        "evidence",
        "recommended_action",
        "owner",
        "blocked_until",
        "customer_visible_metric",
        "guardrail",
    ])
    planner = report["marketing_impact_planner"]
    write_csv(impact_csv_path, planner["activation_lanes"], [
        "lane_key",
        "audience",
        "recommended_channel",
        "record_count",
        "decision_use",
        "expected_impact",
        "approval_required",
        "measurement_event",
        "guardrail",
    ])
    write_csv(measurement_csv_path, planner["measurement_loop"], [
        "stage",
        "cadence",
        "owner",
        "denominator",
        "required_fields",
        "pass_condition",
        "output",
    ])
    write_csv(production_gates_csv_path, report["production_gate"]["gates"], [
        "gate_key",
        "label",
        "stage",
        "buyer_review_status",
        "production_status",
        "owner",
        "evidence",
        "pass_condition",
        "blocked_until",
        "guardrail",
        "production_required",
    ])
    generated_paths = [
        json_path,
        markdown_path,
        boardroom_brief_path,
        decision_matrix_path,
        impact_csv_path,
        measurement_csv_path,
        production_gate_path,
        production_gates_csv_path,
        production_runbook_path,
    ]
    findings = _secret_scan(generated_paths)
    if findings:
        report["status"] = "fail"
        report["secret_scan"] = {"status": "fail", "findings": findings}
        write_json(json_path, report)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        boardroom_brief_path.write_text(render_boardroom_brief(report), encoding="utf-8")
        production_gate_path.write_text(render_production_gate_markdown(report), encoding="utf-8")
        production_runbook_path.write_text(render_production_runbook(report), encoding="utf-8")
    else:
        report["secret_scan"] = {"status": "pass", "findings": []}
        write_json(json_path, report)
    return {
        "status": report["status"],
        "paths": {
            "open_intelligence": str(json_path),
            "markdown": str(markdown_path),
            "boardroom_brief": str(boardroom_brief_path),
            "decision_matrix": str(decision_matrix_path),
            "marketing_impact_planner": str(impact_csv_path),
            "measurement_loop": str(measurement_csv_path),
            "production_gate": str(production_gate_path),
            "production_gates": str(production_gates_csv_path),
            "production_runbook": str(production_runbook_path),
        },
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot Open Intelligence model card and data room")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--production-evidence", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    production_evidence = json.loads(args.production_evidence.read_text(encoding="utf-8")) if args.production_evidence else None
    pack = build_open_intelligence_pack(args.out_dir, snapshot=snapshot, production_evidence=production_evidence)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "model": pack["report"]["model_card"]["name"],
        "model_lab": pack["report"]["model_lab"]["status"],
        "data_collaboration_room": pack["report"]["data_collaboration_room"]["status"],
        "marketing_impact_planner": pack["report"]["marketing_impact_planner"]["status"],
        "production_gate": pack["report"]["production_gate"]["status"],
        "production_ready": pack["report"]["production_gate"]["production_ready"],
        "issues": pack["report"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
