#!/usr/bin/env python3
"""Local lead review decisions and Street View camera overrides."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent.resolve()
REVIEW_PATH = HERE / "lead_review.json"
LEARNING_PATH = HERE / "karpathyloop_property_feedback.jsonl"

DECISIONS = {"selected", "reserve", "removed", "unreviewed"}


def _blank_state() -> dict[str, Any]:
    return {"leads": {}}


def load_review_state() -> dict[str, Any]:
    if not REVIEW_PATH.exists():
        return _blank_state()
    try:
        data = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _blank_state()
    if not isinstance(data, dict):
        return _blank_state()
    data.setdefault("leads", {})
    return data


def save_review_state(state: dict[str, Any]) -> None:
    REVIEW_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_learning_event(capakey: str, item: dict[str, Any], changed: list[str]) -> None:
    if not changed:
        return
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "loop": "facadepilot_selection_feedback_v1",
        "capakey": str(capakey),
        "decision": item.get("decision", "unreviewed"),
        "note": item.get("note", ""),
        "changed": changed,
        "camera": {
            "heading": item.get("heading"),
            "pitch": item.get("pitch"),
            "fov": item.get("fov"),
            "strafe_m": item.get("strafe_m"),
            "target_box": item.get("target_box"),
        },
    }
    try:
        with LEARNING_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        # De leerlog mag de operationele review-flow nooit blokkeren.
        return


def _apply_updates(item: dict[str, Any], updates: dict[str, Any]) -> list[str]:
    changed: list[str] = []

    if "decision" in updates:
        decision = updates["decision"] or "unreviewed"
        if decision not in DECISIONS:
            raise ValueError(f"Onbekende review-status: {decision}")
        if item.get("decision") != decision:
            item["decision"] = decision
            changed.append("decision")

    for key in ("heading", "pitch", "fov", "strafe_m"):
        if key not in updates:
            continue
        value = updates[key]
        if value in (None, ""):
            if key in item:
                item.pop(key, None)
                changed.append(key)
            continue
        next_value = float(value) if key in {"heading", "strafe_m"} else int(float(value))
        if item.get(key) != next_value:
            item[key] = next_value
            changed.append(key)

    if "target_box" in updates:
        value = updates["target_box"]
        if value in (None, "", "null"):
            if "target_box" in item:
                item.pop("target_box", None)
                changed.append("target_box")
        else:
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValueError("target_box is geen geldige JSON") from exc
            if not isinstance(value, dict):
                raise ValueError("target_box moet een object zijn")
            box = {
                "x": float(value.get("x", 0)),
                "y": float(value.get("y", 0)),
                "w": float(value.get("w", 0)),
                "h": float(value.get("h", 0)),
            }
            if box["w"] <= 0.03 or box["h"] <= 0.03:
                raise ValueError("target_box is te klein")
            for key in box:
                box[key] = max(0.0, min(1.0, box[key]))
            if box["x"] + box["w"] > 1:
                box["w"] = 1 - box["x"]
            if box["y"] + box["h"] > 1:
                box["h"] = 1 - box["y"]
            if item.get("target_box") != box:
                item["target_box"] = box
                changed.append("target_box")

    if "note" in updates:
        note = str(updates["note"] or "")
        if item.get("note", "") != note:
            item["note"] = note
            changed.append("note")

    if changed:
        item["updated_at"] = datetime.now(timezone.utc).isoformat()

    return changed


def get_review(capakey: str) -> dict[str, Any]:
    state = load_review_state()
    item = state["leads"].get(str(capakey), {})
    return {
        "decision": item.get("decision", "unreviewed"),
        "heading": item.get("heading"),
        "pitch": item.get("pitch"),
        "fov": item.get("fov"),
        "strafe_m": item.get("strafe_m"),
        "target_box": item.get("target_box"),
        "note": item.get("note", ""),
    }


def update_review(capakey: str, **updates) -> dict[str, Any]:
    capakey = str(capakey or "").strip()
    if not capakey:
        raise ValueError("capakey ontbreekt")

    state = load_review_state()
    item = state["leads"].setdefault(capakey, {})
    changed = _apply_updates(item, updates)

    save_review_state(state)
    _append_learning_event(capakey, item, changed)
    return get_review(capakey)


def bulk_update_reviews(capakeys: list[str], **updates) -> dict[str, Any]:
    clean_keys = [str(key or "").strip() for key in capakeys]
    clean_keys = [key for key in clean_keys if key]
    if not clean_keys:
        return {"updated": 0, "reviews": []}

    state = load_review_state()
    changed_items: list[tuple[str, dict[str, Any], list[str]]] = []
    reviews: list[dict[str, Any]] = []

    for capakey in clean_keys:
        item = state["leads"].setdefault(capakey, {})
        changed = _apply_updates(item, updates)
        if changed:
            changed_items.append((capakey, item.copy(), changed))

    save_review_state(state)
    for capakey, item, changed in changed_items:
        _append_learning_event(capakey, item, changed)
    for capakey in clean_keys[:50]:
        reviews.append(get_review(capakey))
    return {"updated": len(clean_keys), "changed": len(changed_items), "reviews": reviews}


def review_counts() -> dict[str, int]:
    counts = {decision: 0 for decision in DECISIONS}
    state = load_review_state()
    for item in state["leads"].values():
        decision = item.get("decision", "unreviewed")
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def apply_review_filter(df):
    """Filter a lead DataFrame before rendering.

    If at least one lead is explicitly selected, render only selected leads.
    Otherwise, render all leads except leads marked removed or reserve.
    """
    state = load_review_state()
    reviews = state.get("leads", {})
    if not reviews or "CAPAKEY" not in df.columns:
        return df

    selected = {k for k, v in reviews.items() if v.get("decision") == "selected"}
    blocked = {k for k, v in reviews.items() if v.get("decision") in {"removed", "reserve"}}

    capakeys = df["CAPAKEY"].astype(str)
    selected_in_df = selected.intersection(set(capakeys))
    if selected_in_df:
        return df[capakeys.isin(selected)].copy()
    return df[~capakeys.isin(blocked)].copy()


def camera_for(capakey: str) -> dict[str, Any]:
    item = get_review(capakey)
    camera = {k: item.get(k) for k in ("heading", "pitch", "fov", "strafe_m") if item.get(k) is not None}
    if item.get("target_box"):
        camera["target_box"] = item["target_box"]
    return camera
