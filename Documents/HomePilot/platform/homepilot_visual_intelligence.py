#!/usr/bin/env python3
"""
Build scalable visual intelligence models for HomePilot dashboards.

Customer-facing dashboards need to feel impressive without becoming slow or
unreadable when a territory grows from a few demo homes to hundreds of
properties. This module creates a compact map cluster model, a graph render
budget, and evidence artifacts for buyer review.
"""

from __future__ import annotations

import argparse
import csv
import json
from math import floor
from pathlib import Path
from typing import Any

from homepilot_autoresearch import build_graph_layout_recommendation


DEFAULT_CLUSTER_THRESHOLD = 80
DEFAULT_GRID_SIZE = 7
DEFAULT_NODE_BUDGET = 160
DEFAULT_EDGE_BUDGET = 260


def _number(value: Any, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _best_assessment(property_row: dict[str, Any]) -> dict[str, Any]:
    assessments = property_row.get("assessments") if isinstance(property_row.get("assessments"), dict) else {}
    best_key = ""
    best = {"score": 0, "grade": "", "label": ""}
    for key, value in assessments.items():
        if _number(value.get("score")) > _number(best.get("score")):
            best_key = str(key)
            best = value
    return {"module_key": best_key, **best}


def _level(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 65:
        return "mid"
    return "low"


def _bounds(mapped: list[dict[str, Any]]) -> dict[str, float] | None:
    if not mapped:
        return None
    lats = [_number(row.get("lat")) for row in mapped]
    lons = [_number(row.get("lon")) for row in mapped]
    return {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }


def _cell_index(value: float, minimum: float, maximum: float, grid_size: int) -> int:
    span = max(0.000001, maximum - minimum)
    return max(0, min(grid_size - 1, int(floor(((value - minimum) / span) * grid_size))))


def build_map_clusters(
    properties: list[dict[str, Any]],
    grid_size: int = DEFAULT_GRID_SIZE,
    cluster_threshold: int = DEFAULT_CLUSTER_THRESHOLD,
) -> dict[str, Any]:
    mapped = [
        row for row in properties
        if row.get("lat") not in (None, "") and row.get("lon") not in (None, "")
    ]
    bounds = _bounds(mapped)
    if not bounds:
        return {
            "strategy": "empty_map",
            "cluster_threshold": cluster_threshold,
            "grid_size": grid_size,
            "property_count": len(properties),
            "mapped_property_count": 0,
            "mapped_coverage_pct": 0,
            "bounds": None,
            "clusters": [],
            "top_clusters": [],
        }

    cluster_map: dict[str, dict[str, Any]] = {}
    for property_row in mapped:
        lat = _number(property_row.get("lat"))
        lon = _number(property_row.get("lon"))
        x_index = _cell_index(lon, bounds["min_lon"], bounds["max_lon"], grid_size)
        y_index = _cell_index(lat, bounds["min_lat"], bounds["max_lat"], grid_size)
        cluster_id = f"cell:{x_index}:{y_index}"
        best = _best_assessment(property_row)
        score = _number(best.get("score"))
        cluster = cluster_map.setdefault(cluster_id, {
            "id": cluster_id,
            "grid_x": x_index,
            "grid_y": y_index,
            "property_count": 0,
            "lat_sum": 0.0,
            "lon_sum": 0.0,
            "max_score": 0.0,
            "score_sum": 0.0,
            "estimated_value_sum": 0.0,
            "module_counts": {},
            "status_counts": {},
            "property_ids": [],
            "top_properties": [],
        })
        cluster["property_count"] += 1
        cluster["lat_sum"] += lat
        cluster["lon_sum"] += lon
        cluster["max_score"] = max(_number(cluster["max_score"]), score)
        cluster["score_sum"] += score
        cluster["estimated_value_sum"] += _number(property_row.get("estimatedValue"))
        module_key = str(best.get("module_key") or "unknown")
        status = str(property_row.get("status") or "generated")
        cluster["module_counts"][module_key] = cluster["module_counts"].get(module_key, 0) + 1
        cluster["status_counts"][status] = cluster["status_counts"].get(status, 0) + 1
        cluster["property_ids"].append(str(property_row.get("id")))
        cluster["top_properties"].append({
            "id": str(property_row.get("id")),
            "address": str(property_row.get("address") or ""),
            "score": int(round(score)),
            "module_key": module_key,
            "status": status,
        })

    clusters = []
    for cluster in cluster_map.values():
        count = max(1, int(cluster["property_count"]))
        top_properties = sorted(cluster["top_properties"], key=lambda row: row["score"], reverse=True)[:8]
        top_module = max(cluster["module_counts"], key=cluster["module_counts"].get) if cluster["module_counts"] else ""
        clusters.append({
            "id": cluster["id"],
            "grid_x": cluster["grid_x"],
            "grid_y": cluster["grid_y"],
            "property_count": count,
            "lat": round(cluster["lat_sum"] / count, 6),
            "lon": round(cluster["lon_sum"] / count, 6),
            "avg_score": round(cluster["score_sum"] / count, 1),
            "max_score": int(round(cluster["max_score"])),
            "level": _level(_number(cluster["max_score"])),
            "estimated_value_sum": int(round(cluster["estimated_value_sum"])),
            "top_module": top_module,
            "module_counts": dict(sorted(cluster["module_counts"].items())),
            "status_counts": dict(sorted(cluster["status_counts"].items())),
            "property_ids": cluster["property_ids"][:25],
            "top_properties": top_properties,
        })

    clusters.sort(key=lambda row: (row["property_count"], row["max_score"], row["estimated_value_sum"]), reverse=True)
    return {
        "strategy": "clustered_map" if len(mapped) > cluster_threshold else "property_points",
        "cluster_threshold": cluster_threshold,
        "grid_size": grid_size,
        "property_count": len(properties),
        "mapped_property_count": len(mapped),
        "mapped_coverage_pct": round((len(mapped) / max(1, len(properties))) * 100, 1),
        "bounds": bounds,
        "clusters": clusters,
        "top_clusters": clusters[:8],
    }


def build_graph_budget(
    brain: dict[str, Any],
    node_budget: int = DEFAULT_NODE_BUDGET,
    edge_budget: int = DEFAULT_EDGE_BUDGET,
) -> dict[str, Any]:
    nodes = brain.get("nodes") if isinstance(brain.get("nodes"), list) else []
    edges = brain.get("edges") if isinstance(brain.get("edges"), list) else []
    degree: dict[str, int] = {}
    for edge in edges:
        degree[str(edge.get("source"))] = degree.get(str(edge.get("source")), 0) + 1
        degree[str(edge.get("target"))] = degree.get(str(edge.get("target")), 0) + 1

    type_priority = {
        "tenant": 0,
        "module": 1,
        "campaign": 2,
        "signal": 3,
        "property": 4,
        "reaction": 5,
        "objection": 6,
        "action": 7,
    }
    ranked_nodes = sorted(
        nodes,
        key=lambda node: (
            type_priority.get(str(node.get("type")), 9),
            -degree.get(str(node.get("id")), 0),
            -_number(node.get("score")),
            -_number(node.get("weight")),
            str(node.get("label") or ""),
        ),
    )
    render_nodes = ranked_nodes[:node_budget]
    render_ids = {str(node.get("id")) for node in render_nodes}
    ranked_edges = sorted(
        [
            edge for edge in edges
            if str(edge.get("source")) in render_ids and str(edge.get("target")) in render_ids
        ],
        key=lambda edge: (
            -_number(edge.get("weight")),
            -_number(edge.get("score")),
            str(edge.get("type") or ""),
            str(edge.get("source") or ""),
        ),
    )
    render_edges = ranked_edges[:edge_budget]
    node_by_id = {str(node.get("id")): node for node in nodes}
    hubs = []
    for node_id, count in sorted(degree.items(), key=lambda item: item[1], reverse=True)[:12]:
        node = node_by_id.get(node_id, {})
        hubs.append({
            "id": node_id,
            "label": str(node.get("label") or node_id),
            "type": str(node.get("type") or "unknown"),
            "degree": count,
            "weight": int(_number(node.get("weight"), 1)),
        })

    return {
        "strategy": "budgeted_graph" if len(nodes) > node_budget or len(edges) > edge_budget else "full_graph",
        "node_budget": node_budget,
        "edge_budget": edge_budget,
        "source_nodes": len(nodes),
        "source_edges": len(edges),
        "render_nodes": len(render_nodes),
        "render_edges": len(render_edges),
        "hidden_nodes": max(0, len(nodes) - len(render_nodes)),
        "hidden_edges": max(0, len(edges) - len(render_edges)),
        "render_node_ids": [str(node.get("id")) for node in render_nodes],
        "render_edge_keys": [
            f"{edge.get('source')}->{edge.get('target')}:{edge.get('type')}"
            for edge in render_edges
        ],
        "hubs": hubs,
    }


def build_visual_intelligence(snapshot: dict[str, Any]) -> dict[str, Any]:
    properties = snapshot.get("properties") if isinstance(snapshot.get("properties"), list) else []
    brain = snapshot.get("brain") if isinstance(snapshot.get("brain"), dict) else {}
    map_model = build_map_clusters(properties)
    graph_model = build_graph_budget(brain)
    graph_model.update(build_graph_layout_recommendation(
        brain,
        node_budget=graph_model["node_budget"],
        edge_budget=graph_model["edge_budget"],
        run_count=0,
    ))
    warnings = []
    if map_model["mapped_coverage_pct"] < 95 and properties:
        warnings.append("Map coverage below 95%; geocode missing properties before territory-scale campaigns.")
    if graph_model["strategy"] == "budgeted_graph":
        warnings.append("Second-brain graph is budgeted for readable rendering; use hubs/top clusters for boardroom review.")
    return {
        "model_type": "homepilot_visual_intelligence",
        "status": "pass",
        "map": map_model,
        "graph": graph_model,
        "boardroom": {
            "recommended_map_view": map_model["strategy"],
            "recommended_graph_view": graph_model["strategy"],
            "top_cluster_ids": [cluster["id"] for cluster in map_model["top_clusters"][:5]],
            "top_hub_ids": [hub["id"] for hub in graph_model["hubs"][:5]],
        },
        "performance_contract": {
            "cluster_threshold": DEFAULT_CLUSTER_THRESHOLD,
            "grid_size": DEFAULT_GRID_SIZE,
            "graph_node_budget": DEFAULT_NODE_BUDGET,
            "graph_edge_budget": DEFAULT_EDGE_BUDGET,
        },
        "warnings": warnings,
    }


def build_visual_scale_fixture(property_count: int = 180) -> dict[str, Any]:
    statuses = ["generated", "sent", "no_response", "responded", "appointment"]
    modules = ["windowpilot", "facadepilot", "roofpilot", "gardenpilot"]
    properties = []
    nodes = [
        {"id": "tenant:visual_scale", "label": "Visual Scale Customer", "type": "tenant", "weight": property_count},
    ]
    edges = []
    for module_key in modules:
        nodes.append({"id": f"module:{module_key}", "label": module_key, "type": "module", "module_key": module_key})
        edges.append({"source": "tenant:visual_scale", "target": f"module:{module_key}", "type": "enabled_module", "label": "enabled"})
    for index in range(property_count):
        module_key = modules[index % len(modules)]
        status = statuses[index % len(statuses)]
        score = 60 + (index % 38)
        property_id = f"visual_prop_{index:03d}"
        lat = 50.78 + ((index % 30) * 0.006)
        lon = 4.58 + ((index // 30) * 0.028) + ((index % 5) * 0.002)
        properties.append({
            "id": property_id,
            "address": f"Visual Scalelaan {index + 1}",
            "city": ["Leuven", "Herent", "Bierbeek", "Tienen"][index % 4],
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "status": status,
            "nextAction": "Review clustered territory",
            "estimatedValue": 25000 + (score * 500),
            "tags": [f"segment-{index % 9}", "scale-test"],
            "assessments": {
                module_key: {
                    "score": score,
                    "grade": "A" if score >= 80 else "B",
                    "label": f"{module_key} signal {index % 12}",
                    "confidence": 0.72,
                    "metrics": {},
                    "evidence": [{"type": "note", "value": "Synthetic visual scale fixture"}],
                }
            },
            "interactions": [],
            "objections": [],
        })
        property_node = f"property:{property_id}"
        signal_node = f"signal:{module_key}:{index % 12}"
        status_node = f"status:{status}"
        nodes.append({"id": property_node, "label": f"Visual Scalelaan {index + 1}", "type": "property", "property_id": property_id, "module_key": module_key, "score": score, "weight": max(1, round(score / 20))})
        nodes.append({"id": signal_node, "label": f"{module_key} signal {index % 12}", "type": "signal", "module_key": module_key, "weight": 1})
        nodes.append({"id": status_node, "label": status.replace("_", " ").title(), "type": "reaction", "status": status, "weight": 1})
        edges.append({"source": f"module:{module_key}", "target": property_node, "type": "scores_property", "label": "scores", "module_key": module_key, "property_id": property_id, "score": score})
        edges.append({"source": signal_node, "target": property_node, "type": "assessment_signal", "label": "evidence", "module_key": module_key, "property_id": property_id, "score": score})
        edges.append({"source": property_node, "target": status_node, "type": "campaign_status", "label": "status", "property_id": property_id})
    unique_nodes = {str(node["id"]): node for node in nodes}
    return {
        "tenant": {"id": "visual-scale", "name": "Visual Scale Customer", "modules": modules},
        "campaigns": [],
        "properties": properties,
        "recommendations": ["Use clustered territory view for boardroom review."],
        "summary": {"tenants": 1, "properties": len(properties), "modules": {module: property_count // len(modules) for module in modules}},
        "brain": {
            "nodes": list(unique_nodes.values()),
            "edges": edges,
            "stats": {"nodes": len(unique_nodes), "edges": len(edges), "properties": len(properties), "modules": len(modules)},
        },
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def write_cluster_csv(path: Path, clusters: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "id",
            "property_count",
            "lat",
            "lon",
            "avg_score",
            "max_score",
            "level",
            "estimated_value_sum",
            "top_module",
        ])
        writer.writeheader()
        for cluster in clusters:
            writer.writerow({key: cluster.get(key) for key in writer.fieldnames})


def render_runbook(visual: dict[str, Any]) -> str:
    graph = visual["graph"]
    map_model = visual["map"]
    lines = [
        "# HomePilot Visual Intelligence Runbook",
        "",
        f"Status: {visual['status']}",
        f"Map strategy: {map_model['strategy']}",
        f"Graph strategy: {graph['strategy']}",
        "",
        "## Scale Contract",
        "",
        f"- Properties: {map_model['property_count']}",
        f"- Mapped coverage: {map_model['mapped_coverage_pct']}%",
        f"- Map clusters: {len(map_model['clusters'])}",
        f"- Graph source/render nodes: {graph['source_nodes']} / {graph['render_nodes']}",
        f"- Graph source/render edges: {graph['source_edges']} / {graph['render_edges']}",
        "",
        "## Graph Readability Evidence",
        "",
        f"- Layout score: {graph.get('layout_quality', {}).get('final_score', 'n/a')}",
        f"- Node overlaps: {graph.get('layout_quality', {}).get('overlap_count', 'n/a')}",
        f"- Label overlaps: {graph.get('layout_quality', {}).get('label_overlap_count', 'n/a')}",
        f"- Fit score: {graph.get('layout_quality', {}).get('fit_score', 'n/a')}",
        "",
        "## Boardroom Use",
        "",
        "- Use property points for small territories and clustered map view above the cluster threshold.",
        "- Use graph hubs and top clusters for executive explanation before opening individual properties.",
        "- Keep missing geocodes out of territory heatmaps until addresses are verified.",
        "",
    ]
    if visual["warnings"]:
        lines += ["## Warnings", ""]
        lines.extend(f"- {warning}" for warning in visual["warnings"])
        lines.append("")
    return "\n".join(lines)


def _secret_scan(paths: list[Path]) -> list[str]:
    findings = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in ("service-role", "secret-token", "authorization: bearer", "supabase_service_role"):
            if marker in body:
                findings.append(f"{path}: contains {marker}")
    return findings


def build_visual_intelligence_pack(
    out_dir: Path,
    snapshot: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot or build_visual_scale_fixture()
    visual = build_visual_intelligence(snapshot)
    visual["release_label"] = release_label
    visual_path = out_dir / "visual_intelligence.json"
    runbook_path = out_dir / "VISUAL_INTELLIGENCE.md"
    cluster_csv_path = out_dir / "map_clusters.csv"
    write_json(visual_path, visual)
    write_text(runbook_path, render_runbook(visual))
    write_cluster_csv(cluster_csv_path, visual["map"]["clusters"])
    findings = _secret_scan([visual_path, runbook_path, cluster_csv_path])
    if findings:
        visual["status"] = "fail"
        visual["secret_scan"] = {"status": "fail", "findings": findings}
        write_json(visual_path, visual)
        write_text(runbook_path, render_runbook(visual))
    else:
        visual["secret_scan"] = {"status": "pass", "findings": []}
        write_json(visual_path, visual)
    return {
        "status": visual["status"],
        "paths": {
            "visual_intelligence": str(visual_path),
            "runbook": str(runbook_path),
            "map_clusters": str(cluster_csv_path),
        },
        "visual": visual,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot visual intelligence evidence")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
    pack = build_visual_intelligence_pack(args.out_dir, snapshot=snapshot, release_label=args.release_label)
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "visual_intelligence": pack["paths"]["visual_intelligence"],
        "runbook": pack["paths"]["runbook"],
        "map_clusters": pack["paths"]["map_clusters"],
        "summary": {
            "map_strategy": pack["visual"]["map"]["strategy"],
            "clusters": len(pack["visual"]["map"]["clusters"]),
            "graph_strategy": pack["visual"]["graph"]["strategy"],
            "render_nodes": pack["visual"]["graph"]["render_nodes"],
        },
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
