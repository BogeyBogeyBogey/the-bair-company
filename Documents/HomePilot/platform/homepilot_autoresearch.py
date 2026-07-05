#!/usr/bin/env python3
"""
Run a safe HomePilot autoresearch loop for second-brain graph layouts.

This is deliberately narrower than a self-modifying agent. It benchmarks a
small deterministic set of layout configurations against synthetic HomePilot
graph fixtures and writes review artifacts. It never touches live data,
Supabase, outreach state, or customer records.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_LAYOUT_CONFIG: dict[str, Any] = {
    "world_width": 1680,
    "world_height": 920,
    "world_pad": 72,
    "viewbox_width": 980,
    "viewbox_height": 560,
    "tick_count": 150,
    "cooling_span": 170,
    "lane_force": 0.018,
    "center_gravity": 0.0025,
    "edge_base_distance": 170,
    "edge_span_factor": 0.18,
    "edge_span_cap": 90,
    "edge_force": 0.012,
    "repulsion_padding": 42,
    "repulsion_force": 0.48,
    "fit_x_margin": 42,
    "fit_y_margin": 58,
    "min_scale": 0.34,
    "max_scale": 1.15,
    "property_label_budget": 10,
    "initial_stagger": 14,
    "initial_x_jitter": 18,
    "lanes": {
        "tenant": {"x": 100, "weight": 1.25},
        "module": {"x": 260, "weight": 1.1},
        "partner": {"x": 445, "weight": 1.0},
        "campaign": {"x": 615, "weight": 0.9},
        "signal": {"x": 790, "weight": 0.75},
        "property": {"x": 1010, "weight": 0.55},
        "reaction": {"x": 1260, "weight": 0.85},
        "objection": {"x": 1330, "weight": 0.85},
        "action": {"x": 1510, "weight": 1.0},
    },
}

DEFAULT_NODE_BUDGET = 160
DEFAULT_EDGE_BUDGET = 260


def _number(value: Any, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return number


def _int(value: Any, fallback: int) -> int:
    return max(1, int(round(_number(value, fallback))))


def _merged_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_LAYOUT_CONFIG)
    if not overrides:
        return config
    for key, value in overrides.items():
        if key == "lanes" and isinstance(value, dict):
            for lane_key, lane_value in value.items():
                if isinstance(lane_value, dict):
                    config["lanes"].setdefault(lane_key, {}).update(lane_value)
        elif key in config:
            config[key] = value
    return config


def _node_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "")


def _edge_key(row: dict[str, Any]) -> str:
    return f"{row.get('source')}->{row.get('target')}:{row.get('type', '')}"


def _radius(node: dict[str, Any]) -> float:
    node_type = str(node.get("type") or "")
    if node_type == "property":
        return max(18, min(30, _number(node.get("score"), 70) / 3.5))
    if node_type == "tenant":
        return 34
    if node_type == "module":
        return 25
    if node_type == "partner":
        return 27
    return 21


def _ranked_graph(
    brain: dict[str, Any],
    node_budget: int = DEFAULT_NODE_BUDGET,
    edge_budget: int = DEFAULT_EDGE_BUDGET,
) -> dict[str, list[dict[str, Any]]]:
    nodes = brain.get("nodes") if isinstance(brain.get("nodes"), list) else []
    edges = brain.get("edges") if isinstance(brain.get("edges"), list) else []
    degree: dict[str, int] = {}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        degree[source] = degree.get(source, 0) + 1
        degree[target] = degree.get(target, 0) + 1

    type_priority = {
        "tenant": 0,
        "module": 1,
        "partner": 2,
        "campaign": 3,
        "signal": 4,
        "property": 5,
        "reaction": 6,
        "objection": 7,
        "action": 8,
    }
    ranked_nodes = sorted(
        nodes,
        key=lambda node: (
            type_priority.get(str(node.get("type") or ""), 99),
            -degree.get(_node_id(node), 0),
            -_number(node.get("score")),
            -_number(node.get("weight")),
            str(node.get("label") or ""),
        ),
    )[:node_budget]
    render_ids = {_node_id(node) for node in ranked_nodes}
    ranked_edges = sorted(
        [
            edge for edge in edges
            if str(edge.get("source") or "") in render_ids
            and str(edge.get("target") or "") in render_ids
        ],
        key=lambda edge: (
            -_number(edge.get("weight")),
            -_number(edge.get("score")),
            str(edge.get("type") or ""),
            str(edge.get("source") or ""),
        ),
    )[:edge_budget]
    return {"nodes": ranked_nodes, "edges": ranked_edges}


def _lane_for(node_type: str, config: dict[str, Any]) -> dict[str, float]:
    lane = config.get("lanes", {}).get(node_type)
    if isinstance(lane, dict):
        return {
            "x": _number(lane.get("x"), _number(config["world_width"]) / 2),
            "weight": _number(lane.get("weight"), 0.6),
        }
    return {"x": _number(config["world_width"]) / 2, "weight": 0.6}


def _initial_position(
    node: dict[str, Any],
    type_index: int,
    type_total: int,
    index: int,
    config: dict[str, Any],
) -> dict[str, float]:
    lane = _lane_for(str(node.get("type") or ""), config)
    world_height = _number(config["world_height"])
    world_width = _number(config["world_width"])
    pad = _number(config["world_pad"])
    usable_height = world_height - pad * 2
    slot = (type_index + 0.5) / max(1, type_total)
    stagger = ((index % 5) - 2) * _number(config["initial_stagger"])
    jitter = ((index % 3) - 1) * _number(config["initial_x_jitter"])
    return {
        "x": max(pad, min(world_width - pad, lane["x"] + jitter)),
        "y": max(pad, min(world_height - pad, pad + slot * usable_height + stagger)),
        "r": _radius(node),
    }


def _clamp(point: dict[str, float], config: dict[str, Any]) -> None:
    pad = _number(config["world_pad"])
    point["x"] = max(pad, min(_number(config["world_width"]) - pad, point["x"]))
    point["y"] = max(pad, min(_number(config["world_height"]) - pad, point["y"]))


def compute_graph_layout(
    graph: dict[str, list[dict[str, Any]]],
    layout_config: dict[str, Any] | None = None,
) -> dict[str, dict[str, float]]:
    config = _merged_config(layout_config)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_type: dict[str, list[str]] = {}
    for node in nodes:
        by_type.setdefault(str(node.get("type") or ""), []).append(_node_id(node))
    layout: dict[str, dict[str, float]] = {}
    for index, node in enumerate(nodes):
        node_type = str(node.get("type") or "")
        ids = by_type.get(node_type, [_node_id(node)])
        node_id = _node_id(node)
        layout[node_id] = _initial_position(node, max(0, ids.index(node_id)), len(ids), index, config)

    node_ids = {_node_id(node) for node in nodes}
    linked_edges = [
        edge for edge in edges
        if str(edge.get("source") or "") in node_ids and str(edge.get("target") or "") in node_ids
    ]
    tick_count = _int(config.get("tick_count"), 150)
    cooling_span = max(1, _number(config.get("cooling_span"), tick_count + 20))
    for tick in range(tick_count):
        cooling = max(0.0, 1 - tick / cooling_span)
        for node in nodes:
            node_id = _node_id(node)
            point = layout.get(node_id)
            if not point:
                continue
            lane = _lane_for(str(node.get("type") or ""), config)
            point["x"] += (lane["x"] - point["x"]) * _number(config["lane_force"]) * lane["weight"] * cooling
            point["y"] += (_number(config["world_height"]) / 2 - point["y"]) * _number(config["center_gravity"]) * cooling

        for edge in linked_edges:
            source = layout.get(str(edge.get("source") or ""))
            target = layout.get(str(edge.get("target") or ""))
            if not source or not target:
                continue
            dx = target["x"] - source["x"]
            dy = target["y"] - source["y"]
            distance = max(1.0, math.hypot(dx, dy))
            desired = _number(config["edge_base_distance"]) + min(
                _number(config["edge_span_cap"]),
                abs(dx) * _number(config["edge_span_factor"]),
            )
            force = (distance - desired) * _number(config["edge_force"]) * cooling
            nx = dx / distance
            ny = dy / distance
            source["x"] += nx * force
            source["y"] += ny * force
            target["x"] -= nx * force
            target["y"] -= ny * force

        for i, node_a in enumerate(nodes):
            a = layout.get(_node_id(node_a))
            if not a:
                continue
            for node_b in nodes[i + 1:]:
                b = layout.get(_node_id(node_b))
                if not b:
                    continue
                dx = b["x"] - a["x"]
                dy = b["y"] - a["y"]
                distance = max(0.1, math.hypot(dx, dy))
                min_distance = a["r"] + b["r"] + _number(config["repulsion_padding"])
                if distance >= min_distance:
                    continue
                push = ((min_distance - distance) / distance) * _number(config["repulsion_force"]) * cooling
                a["x"] -= dx * push
                a["y"] -= dy * push
                b["x"] += dx * push
                b["y"] += dy * push

        for point in layout.values():
            _clamp(point, config)
    return layout


def _fit_metrics(layout: dict[str, dict[str, float]], config: dict[str, Any]) -> dict[str, float]:
    if not layout:
        return {"raw_fit_scale": 1.0, "scale": 1.0, "fit_score": 100.0, "width": 0.0, "height": 0.0}
    min_x = min(point["x"] - point["r"] - _number(config["fit_x_margin"]) for point in layout.values())
    max_x = max(point["x"] + point["r"] + _number(config["fit_x_margin"]) for point in layout.values())
    min_y = min(point["y"] - point["r"] - _number(config["fit_y_margin"]) for point in layout.values())
    max_y = max(point["y"] + point["r"] + _number(config["fit_y_margin"]) for point in layout.values())
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)
    raw_fit = min(_number(config["viewbox_width"]) / width, _number(config["viewbox_height"]) / height)
    min_scale = _number(config["min_scale"])
    max_scale = _number(config["max_scale"])
    scale = max(min_scale, min(max_scale, raw_fit))
    if raw_fit >= min_scale:
        fit_score = 100.0
    else:
        fit_score = max(0.0, 100.0 - ((min_scale - raw_fit) / max(0.01, min_scale)) * 100.0)
    return {
        "raw_fit_scale": round(raw_fit, 4),
        "scale": round(scale, 4),
        "fit_score": round(fit_score, 2),
        "width": round(width, 2),
        "height": round(height, 2),
    }


def _orientation(a: dict[str, float], b: dict[str, float], c: dict[str, float]) -> float:
    return (b["y"] - a["y"]) * (c["x"] - b["x"]) - (b["x"] - a["x"]) * (c["y"] - b["y"])


def _segments_cross(a: dict[str, float], b: dict[str, float], c: dict[str, float], d: dict[str, float]) -> bool:
    return (_orientation(a, b, c) * _orientation(a, b, d) < 0) and (
        _orientation(c, d, a) * _orientation(c, d, b) < 0
    )


def _edge_crossings(graph: dict[str, list[dict[str, Any]]], layout: dict[str, dict[str, float]]) -> int:
    edges = graph.get("edges", [])
    count = 0
    for i, edge_a in enumerate(edges):
        a_source = str(edge_a.get("source") or "")
        a_target = str(edge_a.get("target") or "")
        a = layout.get(a_source)
        b = layout.get(a_target)
        if not a or not b:
            continue
        for edge_b in edges[i + 1:]:
            b_source = str(edge_b.get("source") or "")
            b_target = str(edge_b.get("target") or "")
            if len({a_source, a_target, b_source, b_target}) < 4:
                continue
            c = layout.get(b_source)
            d = layout.get(b_target)
            if c and d and _segments_cross(a, b, c, d):
                count += 1
    return count


def _visible_label_nodes(nodes: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    property_budget = _int(config.get("property_label_budget"), 10)
    property_ids = {
        _node_id(node) for node in sorted(
            [node for node in nodes if node.get("type") == "property"],
            key=lambda node: _number(node.get("score")),
            reverse=True,
        )[:property_budget]
    }
    visible_types = {"tenant", "module", "partner", "campaign", "reaction", "objection", "action"}
    return [
        node for node in nodes
        if str(node.get("type") or "") in visible_types or _node_id(node) in property_ids
    ]


def _label_box(node: dict[str, Any], point: dict[str, float]) -> dict[str, float]:
    label = str(node.get("label") or node.get("id") or "")
    width = min(170.0, max(42.0, len(label[:24]) * 7.2))
    height = 34.0
    top = point["y"] + point["r"] + 7
    return {
        "left": point["x"] - width / 2,
        "right": point["x"] + width / 2,
        "top": top,
        "bottom": top + height,
    }


def _label_overlaps(graph: dict[str, list[dict[str, Any]]], layout: dict[str, dict[str, float]], config: dict[str, Any]) -> int:
    boxes = []
    for node in _visible_label_nodes(graph.get("nodes", []), config):
        point = layout.get(_node_id(node))
        if point:
            boxes.append(_label_box(node, point))
    overlaps = 0
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a["left"] < b["right"] and a["right"] > b["left"] and a["top"] < b["bottom"] and a["bottom"] > b["top"]:
                overlaps += 1
    return overlaps


def evaluate_graph_layout_quality(
    brain: dict[str, Any],
    layout_config: dict[str, Any] | None = None,
    node_budget: int = DEFAULT_NODE_BUDGET,
    edge_budget: int = DEFAULT_EDGE_BUDGET,
) -> dict[str, Any]:
    config = _merged_config(layout_config)
    graph = _ranked_graph(brain, node_budget=node_budget, edge_budget=edge_budget)
    started = time.perf_counter()
    layout = compute_graph_layout(graph, config)
    runtime_ms = (time.perf_counter() - started) * 1000

    nodes = graph.get("nodes", [])
    overlap_count = 0
    overlap_area = 0.0
    for i, node_a in enumerate(nodes):
        a = layout.get(_node_id(node_a))
        if not a:
            continue
        for node_b in nodes[i + 1:]:
            b = layout.get(_node_id(node_b))
            if not b:
                continue
            distance = max(0.1, math.hypot(b["x"] - a["x"], b["y"] - a["y"]))
            min_distance = a["r"] + b["r"] + _number(config["repulsion_padding"])
            if distance < min_distance:
                overlap_count += 1
                overlap_area += min_distance - distance

    crossing_count = _edge_crossings(graph, layout)
    label_overlap_count = _label_overlaps(graph, layout, config)
    fit = _fit_metrics(layout, config)
    width_ratio = min(1.2, fit["width"] / max(1.0, _number(config["world_width"])))
    height_ratio = min(1.2, fit["height"] / max(1.0, _number(config["world_height"])))
    spread_score = max(0.0, 100.0 - (abs(width_ratio - 0.74) + abs(height_ratio - 0.76)) * 70.0)

    overlap_score = max(0.0, 100.0 - min(100.0, overlap_count * 2.1 + overlap_area / 180.0))
    crossing_score = max(0.0, 100.0 - min(100.0, crossing_count * 0.42))
    label_score = max(0.0, 100.0 - min(100.0, label_overlap_count * 4.0))
    final_score = (
        overlap_score * 0.35
        + fit["fit_score"] * 0.2
        + crossing_score * 0.2
        + label_score * 0.15
        + spread_score * 0.1
    )
    return {
        "final_score": round(final_score, 3),
        "overlap_count": overlap_count,
        "overlap_amount": round(overlap_area, 2),
        "edge_crossing_proxy": crossing_count,
        "label_overlap_count": label_overlap_count,
        "fit_score": fit["fit_score"],
        "raw_fit_scale": fit["raw_fit_scale"],
        "scale": fit["scale"],
        "spread_score": round(spread_score, 2),
        "runtime_ms": round(runtime_ms, 2),
        "render_nodes": len(graph.get("nodes", [])),
        "render_edges": len(graph.get("edges", [])),
        "synthetic_demo_metric": True,
    }


def _variant_config(index: int) -> dict[str, Any]:
    config = _merged_config()
    repulsions = [36, 42, 50, 58, 66]
    edge_base = [145, 165, 185, 205]
    edge_force = [0.009, 0.012, 0.015]
    ticks = [110, 150, 190]
    center = [0.0015, 0.0025, 0.0035]
    property_x = [960, 1010, 1070]
    reaction_x = [1210, 1260, 1320]
    config["repulsion_padding"] = repulsions[index % len(repulsions)]
    config["edge_base_distance"] = edge_base[(index // 2) % len(edge_base)]
    config["edge_force"] = edge_force[(index // 3) % len(edge_force)]
    config["tick_count"] = ticks[(index // 5) % len(ticks)]
    config["center_gravity"] = center[(index // 7) % len(center)]
    config["lanes"]["property"]["x"] = property_x[(index // 11) % len(property_x)]
    config["lanes"]["reaction"]["x"] = reaction_x[(index // 13) % len(reaction_x)]
    config["lanes"]["objection"]["x"] = config["lanes"]["reaction"]["x"] + 70
    config["lanes"]["action"]["x"] = 1505 + ((index % 4) - 1) * 18
    config["property_label_budget"] = [8, 10, 12][(index // 17) % 3]
    return config


def run_layout_experiments(
    brain: dict[str, Any],
    run_count: int = 12,
    baseline_only: bool = False,
    node_budget: int = DEFAULT_NODE_BUDGET,
    edge_budget: int = DEFAULT_EDGE_BUDGET,
) -> list[dict[str, Any]]:
    experiments = [{"tag": "baseline", "layout_config": _merged_config(), "description": "current client defaults"}]
    if not baseline_only:
        for index in range(max(0, run_count)):
            experiments.append({
                "tag": f"variant_{index + 1:02d}",
                "layout_config": _variant_config(index),
                "description": "deterministic layout heuristic variant",
            })
    results = []
    for experiment in experiments:
        quality = evaluate_graph_layout_quality(
            brain,
            layout_config=experiment["layout_config"],
            node_budget=node_budget,
            edge_budget=edge_budget,
        )
        results.append({
            **experiment,
            "quality": quality,
            "status": "keep",
        })
    best = max(results, key=lambda row: (row["quality"]["final_score"], -row["quality"]["runtime_ms"], row["tag"]))
    for row in results:
        if row is not best:
            row["status"] = "discard"
    return sorted(results, key=lambda row: row["quality"]["final_score"], reverse=True)


def build_graph_layout_recommendation(
    brain: dict[str, Any],
    node_budget: int = DEFAULT_NODE_BUDGET,
    edge_budget: int = DEFAULT_EDGE_BUDGET,
    run_count: int = 6,
) -> dict[str, Any]:
    results = run_layout_experiments(
        brain,
        run_count=run_count,
        baseline_only=False,
        node_budget=node_budget,
        edge_budget=edge_budget,
    )
    best = results[0] if results else {
        "tag": "empty",
        "layout_config": _merged_config(),
        "quality": evaluate_graph_layout_quality({}, node_budget=node_budget, edge_budget=edge_budget),
    }
    baseline = next((row for row in results if row["tag"] == "baseline"), best)
    return {
        "layout_config": best["layout_config"],
        "layout_quality": best["quality"],
        "layout_research": {
            "source": "homepilot_autoresearch",
            "experiment_family": "second_brain_graph_layout",
            "experiment_count": len(results),
            "best_tag": best["tag"],
            "baseline_score": baseline["quality"]["final_score"],
            "best_score": best["quality"]["final_score"],
            "synthetic_demo_evidence": True,
            "non_mutating": True,
        },
    }


def write_results_tsv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "tag",
        "final_score",
        "overlap_count",
        "edge_crossing_proxy",
        "label_overlap_count",
        "fit_score",
        "runtime_ms",
        "status",
        "description",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for rank, row in enumerate(results, start=1):
            quality = row["quality"]
            writer.writerow({
                "rank": rank,
                "tag": row["tag"],
                "final_score": quality["final_score"],
                "overlap_count": quality["overlap_count"],
                "edge_crossing_proxy": quality["edge_crossing_proxy"],
                "label_overlap_count": quality["label_overlap_count"],
                "fit_score": quality["fit_score"],
                "runtime_ms": quality["runtime_ms"],
                "status": row["status"],
                "description": row["description"],
            })


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def render_report(pack: dict[str, Any]) -> str:
    best = pack["best"]
    quality = best["quality"]
    lines = [
        "# HomePilot Autoresearch Report",
        "",
        f"Status: {pack['status']}",
        f"Release: {pack['release_label']}",
        f"Experiment family: {pack['experiment_family']}",
        f"Best tag: {best['tag']}",
        f"Final score: {quality['final_score']}",
        "",
        "## Best Quality",
        "",
        f"- Overlap count: {quality['overlap_count']}",
        f"- Edge crossing proxy: {quality['edge_crossing_proxy']}",
        f"- Label overlap count: {quality['label_overlap_count']}",
        f"- Fit score: {quality['fit_score']}",
        f"- Runtime ms: {quality['runtime_ms']}",
        "",
        "## Guardrails",
        "",
        "- Synthetic fixture only; do not treat this as production customer evidence.",
        "- No live database writes, no outreach state changes, and no cross-tenant learning.",
        "- A winning config is a reviewable proposal, not an automatic production change.",
        "",
    ]
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


def build_autoresearch_pack(
    out_dir: Path,
    snapshot: dict[str, Any] | None = None,
    release_label: str = "local",
    run_count: int = 12,
    baseline_only: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if snapshot is None:
        from homepilot_visual_intelligence import build_visual_scale_fixture
        snapshot = build_visual_scale_fixture()
    brain = snapshot.get("brain") if isinstance(snapshot.get("brain"), dict) else {}
    results = run_layout_experiments(brain, run_count=run_count, baseline_only=baseline_only)
    best = results[0]
    paths = {
        "results": str(out_dir / "results.tsv"),
        "best_graph_layout": str(out_dir / "best_graph_layout.json"),
        "report": str(out_dir / "AUTORESEARCH_REPORT.md"),
        "pack": str(out_dir / "autoresearch_pack.json"),
    }
    pack = {
        "pack_type": "homepilot_autoresearch",
        "status": "pass",
        "release_label": release_label,
        "experiment_family": "second_brain_graph_layout",
        "baseline_only": baseline_only,
        "experiment_count": len(results),
        "best": best,
        "summary": {
            "best_tag": best["tag"],
            "best_score": best["quality"]["final_score"],
            "overlap_count": best["quality"]["overlap_count"],
            "fit_score": best["quality"]["fit_score"],
            "edge_crossing_proxy": best["quality"]["edge_crossing_proxy"],
            "label_overlap_count": best["quality"]["label_overlap_count"],
        },
        "guardrails": {
            "synthetic_demo_only": True,
            "non_mutating_pack": True,
            "writes_live_data": False,
            "writes_supabase": False,
            "changes_outreach_state": False,
            "raw_contact_values_written": False,
            "secret_values_written": False,
            "winning_config_requires_review": True,
        },
        "paths": paths,
    }
    write_results_tsv(Path(paths["results"]), results)
    write_json(Path(paths["best_graph_layout"]), {
        "layout_config": best["layout_config"],
        "layout_quality": best["quality"],
        "layout_research": {
            "source": "homepilot_autoresearch",
            "best_tag": best["tag"],
            "experiment_count": len(results),
            "synthetic_demo_evidence": True,
            "non_mutating": True,
        },
    })
    write_text(Path(paths["report"]), render_report(pack))
    findings = _secret_scan([Path(value) for value in paths.values()])
    pack["secret_scan"] = {"status": "pass" if not findings else "fail", "findings": findings}
    if findings:
        pack["status"] = "fail"
    write_json(out_dir / "autoresearch_pack.json", pack)
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HomePilot second-brain graph autoresearch")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--run", type=int, default=12)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
    pack = build_autoresearch_pack(
        out_dir=args.out_dir,
        snapshot=snapshot,
        release_label=args.release_label,
        run_count=args.run,
        baseline_only=args.baseline,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "best_tag": pack["summary"]["best_tag"],
        "best_score": pack["summary"]["best_score"],
        "results": pack["paths"]["results"],
        "best_graph_layout": pack["paths"]["best_graph_layout"],
        "report": pack["paths"]["report"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
