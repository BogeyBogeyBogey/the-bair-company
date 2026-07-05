#!/usr/bin/env python3
"""
Build a customer-facing HomePilot boardroom report.

The dashboard is an interactive workspace. This report is the executive reading
path: the same tenant/module-scoped snapshot, translated into a short report a
buyer can understand before using the dashboard or exports.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
ENGAGED_STATUSES = {"responded", "appointment", "customer"}
CONVERSION_STATUSES = {"appointment", "customer"}
TOP_GRADES = {"A+", "A"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _number(value: Any, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _money(value: Any) -> str:
    amount = _number(value)
    if abs(amount) >= 1_000_000:
        return f"EUR {amount / 1_000_000:.1f}M"
    if abs(amount) >= 1_000:
        return f"EUR {amount / 1_000:.0f}k"
    return f"EUR {amount:.0f}"


def _integer(value: Any) -> str:
    return f"{int(round(_number(value))):,}".replace(",", " ")


def _pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _percent(value: Any) -> str:
    return f"{_number(value):.1f}%"


def _property_assessments(prop: dict[str, Any]) -> list[dict[str, Any]]:
    assessments = prop.get("assessments") if isinstance(prop.get("assessments"), dict) else {}
    rows = []
    for module_key, assessment in assessments.items():
        if isinstance(assessment, dict):
            rows.append({"module_key": module_key, **assessment})
    return rows


def _best_assessment(prop: dict[str, Any]) -> dict[str, Any]:
    assessments = _property_assessments(prop)
    if not assessments:
        return {}
    return sorted(assessments, key=lambda row: _number(row.get("score")), reverse=True)[0]


def _estimated_value(prop: dict[str, Any]) -> float:
    if prop.get("estimatedValue") not in (None, ""):
        return _number(prop.get("estimatedValue"))
    core = prop.get("core") if isinstance(prop.get("core"), dict) else {}
    return _number(core.get("estimated_value") or core.get("pipeline_value"))


def _estimated_facade_m2(prop: dict[str, Any]) -> float:
    if prop.get("estimatedFacadeM2") not in (None, ""):
        return _number(prop.get("estimatedFacadeM2"))
    best = _best_assessment(prop)
    metrics = best.get("metrics") if isinstance(best.get("metrics"), dict) else {}
    return _number(metrics.get("visible_facade_area_m2"))


def _status_counts(properties: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prop in properties:
        status = str(prop.get("status") or "generated")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _module_rows(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for prop in properties:
        for assessment in _property_assessments(prop):
            module_key = str(assessment.get("module_key") or "unknown")
            row = buckets.setdefault(module_key, {
                "module_key": module_key,
                "properties": 0,
                "score_total": 0.0,
                "top_opportunities": 0,
                "pipeline_value": 0.0,
                "contacted": 0,
                "responses": 0,
                "appointments": 0,
            })
            row["properties"] += 1
            row["score_total"] += _number(assessment.get("score"))
            if str(assessment.get("grade") or "") in TOP_GRADES:
                row["top_opportunities"] += 1
            row["pipeline_value"] += _estimated_value(prop)
            status = str(prop.get("status") or "")
            row["contacted"] += 1 if status in CONTACTED_STATUSES else 0
            row["responses"] += 1 if status in ENGAGED_STATUSES else 0
            row["appointments"] += 1 if status in CONVERSION_STATUSES else 0
    rows = []
    for row in buckets.values():
        count = max(1, int(row["properties"]))
        contacted = int(row["contacted"])
        rows.append({
            **row,
            "average_score": round(row["score_total"] / count, 1),
            "top_share_pct": _pct(row["top_opportunities"], count),
            "response_rate_pct": _pct(row["responses"], contacted),
            "target_response_rate_pct": _pct(row["responses"], count),
            "appointment_rate_pct": _pct(row["appointments"], contacted),
        })
    return sorted(rows, key=lambda row: (row["pipeline_value"], row["average_score"]), reverse=True)


def _partner_rows(snapshot: dict[str, Any], properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    network = snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}
    partners = network.get("partners") if isinstance(network.get("partners"), list) else []
    by_partner: dict[str, list[dict[str, Any]]] = {}
    for prop in properties:
        partner = prop.get("partner") if isinstance(prop.get("partner"), dict) else {}
        partner_id = str(partner.get("id") or "")
        if partner_id:
            by_partner.setdefault(partner_id, []).append(prop)

    rows: list[dict[str, Any]] = []
    for partner in partners:
        if not isinstance(partner, dict):
            continue
        partner_id = str(partner.get("id") or "")
        partner_properties = by_partner.get(partner_id, [])
        total = int(partner.get("properties") or len(partner_properties))
        contacted = sum(1 for prop in partner_properties if str(prop.get("status") or "") in CONTACTED_STATUSES)
        responses = int(partner.get("responded") or sum(1 for prop in partner_properties if str(prop.get("status") or "") in ENGAGED_STATUSES))
        appointments = int(partner.get("appointments") or sum(1 for prop in partner_properties if str(prop.get("status") or "") in CONVERSION_STATUSES))
        no_response = int(partner.get("no_response") or sum(1 for prop in partner_properties if str(prop.get("status") or "") == "no_response"))
        pipeline_value = _number(partner.get("pipeline_value") or sum(_estimated_value(prop) for prop in partner_properties))
        facade_m2 = _number(partner.get("facade_m2") or sum(_estimated_facade_m2(prop) for prop in partner_properties))
        top = int(partner.get("top_opportunities") or sum(1 for prop in partner_properties if str(_best_assessment(prop).get("grade") or "") in TOP_GRADES))
        top_share = _pct(top, total)
        contacted_response = _pct(responses, contacted or total)
        action = "Scale partner playbook"
        if top_share >= 65 and contacted_response >= 30:
            action = "Use as proof partner"
        elif no_response >= max(10, total * 0.08):
            action = "Retarget no-response backlog"
        elif appointments >= max(5, total * 0.08):
            action = "Convert booked demand fast"
        rows.append({
            "partner_id": partner_id,
            "partner": str(partner.get("name") or partner_id or "Partner"),
            "region": str(partner.get("region") or partner.get("territory") or "Unknown"),
            "properties": total,
            "top_opportunities": top,
            "top_share_pct": top_share,
            "responses": responses,
            "appointments": appointments,
            "no_response": no_response,
            "pipeline_value": int(round(pipeline_value)),
            "facade_m2": int(round(facade_m2)),
            "response_rate_pct": contacted_response,
            "target_response_rate_pct": _number(partner.get("target_response_rate_pct"), _pct(responses, total)),
            "contacted_response_rate_pct": contacted_response,
            "appointment_rate_pct": _pct(appointments, contacted),
            "recommended_action": action,
        })
    return sorted(rows, key=lambda row: (row["pipeline_value"], row["top_share_pct"]), reverse=True)


def _summary(snapshot: dict[str, Any], properties: list[dict[str, Any]], partner_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = _status_counts(properties)
    contacted = sum(status_counts.get(status, 0) for status in CONTACTED_STATUSES)
    responses = sum(status_counts.get(status, 0) for status in ENGAGED_STATUSES)
    appointments = sum(status_counts.get(status, 0) for status in CONVERSION_STATUSES)
    total_pipeline = sum(_estimated_value(prop) for prop in properties)
    total_facade = sum(_estimated_facade_m2(prop) for prop in properties)
    if partner_rows:
        total_pipeline = sum(row["pipeline_value"] for row in partner_rows) or total_pipeline
        total_facade = sum(row["facade_m2"] for row in partner_rows) or total_facade
    top_count = sum(1 for prop in properties if str(_best_assessment(prop).get("grade") or "") in TOP_GRADES)
    return {
        "properties": len(properties),
        "partners": len(partner_rows),
        "pipeline_value": int(round(total_pipeline)),
        "facade_m2": int(round(total_facade)),
        "top_opportunities": top_count,
        "contacted": contacted,
        "responses": responses,
        "appointments": appointments,
        "no_response": status_counts.get("no_response", 0),
        "response_rate_pct": _pct(responses, contacted),
        "appointment_rate_pct": _pct(appointments, contacted),
        "status_counts": status_counts,
    }


def _safe_score(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _intelligence_lab_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    lead = snapshot.get("leadPrioritization") if isinstance(snapshot.get("leadPrioritization"), dict) else {}
    assignment = snapshot.get("partnerAssignment") if isinstance(snapshot.get("partnerAssignment"), dict) else {}
    segmentation = snapshot.get("campaignSegmentation") if isinstance(snapshot.get("campaignSegmentation"), dict) else {}
    message = snapshot.get("messageStrategy") if isinstance(snapshot.get("messageStrategy"), dict) else {}
    family_sources = [
        (
            "lead_prioritization",
            lead.get("priority_quality") if isinstance(lead.get("priority_quality"), dict) else {},
            lead.get("priority_research") if isinstance(lead.get("priority_research"), dict) else {},
            len(lead.get("best_queue", [])) if isinstance(lead.get("best_queue"), list) else 0,
            "review rows",
        ),
        (
            "partner_assignment",
            assignment.get("assignment_quality") if isinstance(assignment.get("assignment_quality"), dict) else {},
            assignment.get("assignment_research") if isinstance(assignment.get("assignment_research"), dict) else {},
            len(assignment.get("best_assignment", [])) if isinstance(assignment.get("best_assignment"), list) else 0,
            "partner waves",
        ),
        (
            "campaign_segmentation",
            segmentation.get("segment_quality") if isinstance(segmentation.get("segment_quality"), dict) else {},
            segmentation.get("segment_research") if isinstance(segmentation.get("segment_research"), dict) else {},
            len(segmentation.get("best_segments", [])) if isinstance(segmentation.get("best_segments"), list) else 0,
            "segments",
        ),
        (
            "message_strategy",
            message.get("message_quality") if isinstance(message.get("message_quality"), dict) else {},
            message.get("message_research") if isinstance(message.get("message_research"), dict) else {},
            len(message.get("best_message_tests", [])) if isinstance(message.get("best_message_tests"), list) else 0,
            "message tests",
        ),
    ]
    families = []
    for name, quality, research, count, count_label in family_sources:
        if not quality:
            continue
        families.append({
            "family": name,
            "status": "ready",
            "best_tag": research.get("best_tag"),
            "baseline_score": _safe_score(research.get("baseline_score")),
            "best_score": _safe_score(quality.get("final_score") or research.get("best_score")),
            "count": count,
            "count_label": count_label,
            "response_denominator": quality.get("response_denominator") or research.get("response_denominator"),
            "scope_leakage_count": quality.get("scope_leakage_count"),
            "forbidden_claim_count": quality.get("forbidden_claim_count"),
            "compliance_pass_rate_pct": quality.get("compliance_pass_rate_pct"),
            "synthetic_demo_metric": bool(quality.get("synthetic_demo_metric") or research.get("synthetic_demo_evidence")),
            "outcome_proxy_only": bool(quality.get("outcome_proxy_only") or research.get("outcome_proxy_only")),
        })
    guardrails = [
        "Autoresearch evidence is review support, not a live outreach decision.",
        "Response rates stay denominator-explicit and use contacted records where shown.",
        "Partner assignment evidence must stay assigned-records-only for partner handoffs.",
        "Message drafts require DAW/customer approval before launch.",
    ]
    return {
        "status": "ready" if families else "not_run",
        "families": families,
        "family_count": len(families),
        "guardrails": guardrails,
        "synthetic_demo_evidence": any(row["synthetic_demo_metric"] for row in families),
        "outcome_proxy_only": any(row["outcome_proxy_only"] for row in families),
        "scope_leakage_count": next((row["scope_leakage_count"] for row in families if row["family"] == "partner_assignment"), None),
        "forbidden_claim_count": next((row["forbidden_claim_count"] for row in families if row["family"] == "message_strategy"), None),
        "response_denominator": next((row["response_denominator"] for row in families if row["family"] == "campaign_segmentation"), None),
    }


def build_boardroom_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    properties = snapshot.get("properties") if isinstance(snapshot.get("properties"), list) else []
    partner_rows = _partner_rows(snapshot, properties)
    module_rows = _module_rows(properties)
    summary = _summary(snapshot, properties, partner_rows)
    intelligence_lab = _intelligence_lab_summary(snapshot)
    tenant = snapshot.get("tenant") if isinstance(snapshot.get("tenant"), dict) else {}
    network = snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}
    mode = "producer_network" if partner_rows else "tenant_workspace"
    producer = network.get("producer") if isinstance(network.get("producer"), dict) else {}
    title = f"{producer.get('name') or tenant.get('name') or 'HomePilot'} Boardroom Report"
    if mode == "producer_network":
        headline = (
            f"{producer.get('name') or 'Producer'} can steer {summary['partners']} partners across "
            f"{_integer(summary['properties'])} visible opportunities."
        )
    else:
        headline = f"{tenant.get('name') or 'This tenant'} has {_integer(summary['properties'])} visible renovation opportunities."
    recommendations = list(snapshot.get("recommendations") or [])[:4]
    if mode == "producer_network":
        recommendations = [
            "Use the producer view for aggregate performance and partner drilldown; keep partner exports filtered to assigned records.",
            "Review appointments, clicked records, no-response backlog, and queued capacity with partners every week.",
            "Use A/A+ concentration to choose proof partners before scaling spend across the whole network.",
            "Add official address matching, parcel geometry, and statistical-sector context before production import.",
        ]
    elif not recommendations:
        recommendations = [
            "Prioritize high-score properties with recent engagement before increasing campaign volume.",
            "Use no-response records for retargeting tests before changing territory.",
            "Keep exports tenant/module-scoped and attach access-audit evidence to each customer package.",
        ]
    report = {
        "report_type": "homepilot_boardroom_report",
        "created_at": utc_now(),
        "status": "pass",
        "mode": mode,
        "title": title,
        "headline": headline,
        "tenant": tenant,
        "summary": summary,
        "status_rows": [
            {"status": status, "count": count, "share_pct": _pct(count, summary["properties"])}
            for status, count in sorted(summary["status_counts"].items(), key=lambda item: item[1], reverse=True)
        ],
        "module_rows": module_rows,
        "partner_rows": partner_rows,
        "recommendations": recommendations,
        "caveats": [
            "Scores and estimated values are opportunity signals, not claims of homeowner buying intent.",
            "Customer-facing rows must remain tenant-scoped, module-scoped, and partner-scoped where applicable.",
            "Public-data enrichment needs source provenance, licence, retrieval date, and allowed-use review before production import.",
        ],
    }
    if intelligence_lab["status"] == "ready":
        report["recommendations"] = [
            "Review the Intelligence Lab evidence before finalizing partner waves, campaign segments, and message tests.",
            *report["recommendations"],
        ][:5]
        report["caveats"].append(
            "Autoresearch scores are synthetic/demo outcome proxies unless tied to customer-approved production outcomes."
        )
    report["intelligence_lab"] = intelligence_lab
    return report


def _bar(value: float, max_value: float) -> str:
    width = max(2.0, min(100.0, _pct(value, max_value))) if max_value else 2.0
    return f"{width:.1f}%"


def _html_table(rows: list[dict[str, Any]], mode: str) -> str:
    if mode == "producer_network" and rows:
        max_pipeline = max(_number(row.get("pipeline_value")) for row in rows) or 1
        body = []
        for row in rows:
            body.append(
                "<tr>"
                f"<td><strong>{html.escape(str(row['partner']))}</strong><span>{html.escape(str(row['region']))}</span></td>"
                f"<td>{row['properties']}</td>"
                f"<td>{row['top_opportunities']}<span>{_percent(row['top_share_pct'])}</span></td>"
                f"<td>{_percent(row['contacted_response_rate_pct'])}</td>"
                f"<td>{row['appointments']}</td>"
                f"<td><div class='bar'><i style='width:{_bar(_number(row['pipeline_value']), max_pipeline)}'></i></div>{html.escape(_money(row['pipeline_value']))}</td>"
                f"<td>{html.escape(str(row['recommended_action']))}</td>"
                "</tr>"
            )
        return (
            "<table><thead><tr><th>Partner</th><th>Records</th><th>A/A+</th><th>Response</th>"
            "<th>Appt.</th><th>Pipeline</th><th>Action</th></tr></thead><tbody>"
            + "".join(body)
            + "</tbody></table>"
        )
    max_pipeline = max((_number(row.get("pipeline_value")) for row in rows), default=1) or 1
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td><strong>{html.escape(str(row['module_key']))}</strong></td>"
            f"<td>{row['properties']}</td>"
            f"<td>{row['average_score']}</td>"
            f"<td>{row['top_opportunities']}<span>{_percent(row['top_share_pct'])}</span></td>"
            f"<td>{_percent(row['response_rate_pct'])}</td>"
            f"<td><div class='bar'><i style='width:{_bar(_number(row['pipeline_value']), max_pipeline)}'></i></div>{html.escape(_money(row['pipeline_value']))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Module</th><th>Records</th><th>Avg score</th><th>A/A+</th>"
        "<th>Response</th><th>Pipeline</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _html_intelligence_lab(lab: dict[str, Any]) -> str:
    if lab.get("status") != "ready":
        return ""
    family_cards = []
    for row in lab.get("families", []):
        details = [
            f"{row.get('count', 0)} {row.get('count_label') or 'items'}",
            f"best {row.get('best_tag') or 'reviewed'}",
        ]
        if row.get("response_denominator"):
            details.append(f"denominator: {row['response_denominator']}")
        if row.get("scope_leakage_count") is not None:
            details.append(f"scope leakage: {row['scope_leakage_count']}")
        if row.get("forbidden_claim_count") is not None:
            details.append(f"forbidden claims: {row['forbidden_claim_count']}")
        family_cards.append(
            "<div class='lab-card'>"
            f"<small>{html.escape(str(row['family']).replace('_', ' ').title())}</small>"
            f"<strong>{html.escape(str(row.get('best_score') if row.get('best_score') is not None else 'n/a'))}</strong>"
            f"<span>{html.escape(' | '.join(details))}</span>"
            "</div>"
        )
    guardrails = "".join(f"<li>{html.escape(str(item))}</li>" for item in lab.get("guardrails", []))
    return (
        "<section class='panel' data-contract-section='intelligence-lab-evidence'>"
        "<div class='eyebrow'>Open Intelligence</div>"
        "<h2>Intelligence Lab Evidence</h2>"
        "<p><strong>These research loops explain how the first campaign should be reviewed.</strong> "
        "They support partner waves, campaign segments, and message tests while keeping launch approval separate.</p>"
        f"<div class='lab-grid'>{''.join(family_cards)}</div>"
        f"<div class='callout'><ul>{guardrails}</ul></div>"
        "</section>"
    )


def render_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    mode = report["mode"]
    rows = report["partner_rows"] if mode == "producer_network" else report["module_rows"]
    lab_html = _html_intelligence_lab(report.get("intelligence_lab") or {})
    cards = [
        ("Visible records", _integer(summary["properties"]), f"{summary['partners']} partners" if summary["partners"] else "tenant/module scoped"),
        ("Visible pipeline", _money(summary["pipeline_value"]), f"{_integer(summary['facade_m2'])} facade m2" if summary["facade_m2"] else "tenant-private estimate"),
        ("A/A+ opportunities", _integer(summary["top_opportunities"]), f"{_percent(_pct(summary['top_opportunities'], summary['properties']))} of visible set"),
        ("Contacted response", _percent(summary["response_rate_pct"]), f"{_integer(summary['responses'])} responses from {_integer(summary['contacted'])} contacted"),
        ("Appointments", _integer(summary["appointments"]), f"{_percent(summary['appointment_rate_pct'])} contacted-to-appointment"),
        ("No-response backlog", _integer(summary["no_response"]), "retargeting queue"),
    ]
    status_max = max((row["count"] for row in report["status_rows"]), default=1)
    status_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['status']).replace('_', ' ').title())}</td>"
        f"<td><div class='bar soft'><i style='width:{_bar(row['count'], status_max)}'></i></div></td>"
        f"<td>{row['count']}<span>{_percent(row['share_pct'])}</span></td>"
        "</tr>"
        for row in report["status_rows"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(report['title'])}</title>
  <style>
    :root {{ --surface:#f7f8fb; --panel:#fff; --ink:#1f2430; --muted:#626b7d; --line:#dfe3eb; --blue:#5477c4; --soft:#eaf1fe; --olive:#71b436; --orange:#cc6f47; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--surface); color:var(--ink); font-family:Arial, Helvetica, sans-serif; }}
    main {{ max-width:1120px; margin:0 auto; padding:38px 20px 68px; }}
    header {{ padding-bottom:22px; margin-bottom:26px; border-bottom:1px solid var(--line); }}
    .eyebrow {{ color:var(--blue); font-size:13px; letter-spacing:.08em; text-transform:uppercase; font-weight:700; }}
    h1 {{ margin:8px 0 10px; font-size:clamp(34px,5vw,58px); line-height:1.03; }}
    h2 {{ margin:0 0 12px; font-size:clamp(24px,3vw,34px); line-height:1.12; }}
    p, li {{ color:#303746; line-height:1.6; font-size:17px; }}
    section {{ margin:30px 0; }}
    .summary, .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:22px; box-shadow:0 18px 48px rgba(31,36,48,.06); }}
    .cards {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-top:18px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:15px; background:#fbfcff; }}
    .metric small {{ display:block; color:var(--muted); font-size:13px; margin-bottom:8px; }}
    .metric strong {{ display:block; font-size:28px; }}
    .metric span, td span {{ display:block; color:var(--muted); font-size:12px; margin-top:3px; }}
    table {{ width:100%; border-collapse:collapse; overflow:hidden; border-radius:8px; background:var(--panel); }}
    th, td {{ padding:12px 10px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; font-size:14px; }}
    th {{ background:#fbfcff; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
    tr:last-child td {{ border-bottom:0; }}
    .bar {{ width:100%; min-width:130px; height:10px; background:#edf1f7; border-radius:999px; overflow:hidden; margin-bottom:6px; }}
    .bar i {{ display:block; height:100%; background:var(--blue); border-radius:999px; }}
    .bar.soft i {{ background:var(--olive); }}
    .lab-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:18px 0; }}
    .lab-card {{ border:1px solid var(--line); border-top:4px solid var(--blue); border-radius:8px; background:#fbfcff; padding:15px; }}
    .lab-card small {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; font-weight:700; margin-bottom:8px; }}
    .lab-card strong {{ display:block; font-size:28px; margin-bottom:5px; }}
    .lab-card span {{ color:var(--muted); font-size:13px; line-height:1.45; }}
    .callout {{ border-left:5px solid var(--orange); background:#ffedde; border-radius:8px; padding:16px 18px; }}
    @media (max-width:820px) {{ .cards, .lab-grid {{ grid-template-columns:1fr; }} table {{ display:block; overflow-x:auto; white-space:nowrap; }} }}
  </style>
</head>
<body>
<main data-report-audience="product stakeholders">
  <header data-contract-section="title">
    <div class="eyebrow">HomePilot boardroom report</div>
    <h1>{html.escape(report['title'])}</h1>
    <p>{html.escape(report['headline'])}</p>
  </header>
  <section class="summary" data-contract-section="executive-summary">
    <h2>Executive Summary</h2>
    <ul>
      <li><strong>The report translates the dashboard into an executive reading path.</strong> It uses the same tenant/module-scoped snapshot as the dashboard and exports.</li>
      <li><strong>The strongest current signal is {_integer(summary['top_opportunities'])} A/A+ opportunities.</strong> That is {_percent(_pct(summary['top_opportunities'], summary['properties']))} of the visible set.</li>
      <li><strong>Campaign follow-up is measurable.</strong> Response rate is {_percent(summary['response_rate_pct'])} using contacted records as denominator.</li>
    </ul>
    <div class="cards">{''.join(f'<div class="metric"><small>{html.escape(label)}</small><strong>{html.escape(value)}</strong><span>{html.escape(detail)}</span></div>' for label, value, detail in cards)}</div>
  </section>
  {lab_html}
  <section data-contract-section="key-findings">
    <h2>{'Partner steering matrix' if mode == 'producer_network' else 'Module performance matrix'}</h2>
    <p><strong>This is the boardroom control surface.</strong> It shows where the buyer should focus attention before opening row-level exports.</p>
    {_html_table(rows, mode)}
  </section>
  <section>
    <h2>Campaign work queues</h2>
    <p><strong>Statuses are operational queues, not purchase intent.</strong> Use them to decide what to convert, call, retarget, or hold for capacity.</p>
    <table><thead><tr><th>Status</th><th>Volume</th><th>Count</th></tr></thead><tbody>{status_rows}</tbody></table>
  </section>
  <section data-contract-section="recommended-next-steps">
    <h2>Recommended Next Steps</h2>
    <ol>{''.join(f'<li>{html.escape(str(item))}</li>' for item in report['recommendations'])}</ol>
  </section>
  <section data-contract-section="caveats-and-assumptions">
    <h2>Caveats and Assumptions</h2>
    <div class="callout"><ul>{''.join(f'<li>{html.escape(str(item))}</li>' for item in report['caveats'])}</ul></div>
  </section>
</main>
</body>
</html>
"""


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lab = report.get("intelligence_lab") if isinstance(report.get("intelligence_lab"), dict) else {}
    lines = [
        f"# {report['title']}",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Mode: {report['mode']}",
        "",
        "## Executive Summary",
        "",
        f"- {report['headline']}",
        f"- Visible records: {_integer(summary['properties'])}",
        f"- Visible pipeline: {_money(summary['pipeline_value'])}",
        f"- A/A+ opportunities: {_integer(summary['top_opportunities'])}",
        f"- Contacted response rate: {_percent(summary['response_rate_pct'])}",
        "",
    ]
    if lab.get("status") == "ready":
        lines += [
            "## Intelligence Lab Evidence",
            "",
            "These research loops support partner waves, campaign segments, and message tests while keeping launch approval separate.",
            "",
        ]
        for row in lab.get("families", []):
            details = [
                f"score {row.get('best_score') if row.get('best_score') is not None else 'n/a'}",
                f"{row.get('count', 0)} {row.get('count_label') or 'items'}",
            ]
            if row.get("response_denominator"):
                details.append(f"denominator {row['response_denominator']}")
            if row.get("scope_leakage_count") is not None:
                details.append(f"scope leakage {row['scope_leakage_count']}")
            if row.get("forbidden_claim_count") is not None:
                details.append(f"forbidden claims {row['forbidden_claim_count']}")
            lines.append(f"- {str(row['family']).replace('_', ' ')}: " + "; ".join(details))
        lines += ["", "Guardrails:", ""]
        for item in lab.get("guardrails", []):
            lines.append(f"- {item}")
        lines.append("")
    lines += [
        "## Recommended Next Steps",
        "",
    ]
    for item in report["recommendations"]:
        lines.append(f"- {item}")
    lines += ["", "## Caveats", ""]
    for item in report["caveats"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _write_partner_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_boardroom_report_pack(
    snapshot: dict[str, Any],
    output_dir: Path,
    dashboard_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_boardroom_report(snapshot)
    report_path = output_dir / "boardroom_report.json"
    markdown_path = output_dir / "BOARDROOM_REPORT.md"
    html_path = (dashboard_dir / "boardroom-report.html") if dashboard_dir else (output_dir / "boardroom-report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    paths = {
        "boardroom_report": str(report_path),
        "markdown": str(markdown_path),
        "html": str(html_path),
    }
    if report["partner_rows"]:
        partner_path = output_dir / "partner_summary.csv"
        _write_partner_csv(partner_path, report["partner_rows"])
        paths["partner_summary"] = str(partner_path)
    return {
        "status": report["status"],
        "mode": report["mode"],
        "paths": paths,
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot boardroom report from a dashboard snapshot")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--dashboard-dir", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    pack = build_boardroom_report_pack(snapshot, args.out_dir, dashboard_dir=args.dashboard_dir)
    print(json.dumps({
        "status": pack["status"],
        "mode": pack["mode"],
        "paths": pack["paths"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
