"""Stable lead keys for FacadePilot output files and public URLs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


CAMERA_FIELDS = (
    "camera_hash",
    "camera_heading",
    "streetview_heading",
    "heading",
    "pitch",
    "fov",
)


def _row_get(row: Any, key: str, default: Any = "") -> Any:
    if hasattr(row, "get"):
        return row.get(key, default)
    return default


def slugify(value: Any, fallback: str = "lead") -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return text or fallback


def lead_slug(row: Any, fallback_index: int | None = None) -> str:
    """Return the stable lead slug, preferring CAPAKEY over row position."""
    for key in ("CAPAKEY", "capakey", "lead_id", "property_id"):
        value = str(_row_get(row, key, "") or "").strip()
        if value:
            return slugify(value)
    if fallback_index is not None:
        return f"row-{fallback_index:03d}"
    return "lead"


def camera_hash(row: Any) -> str:
    values = []
    for key in CAMERA_FIELDS:
        value = str(_row_get(row, key, "") or "").strip()
        if value:
            values.append(f"{key}={value}")
    if not values:
        return ""
    digest = hashlib.sha1("|".join(values).encode("utf-8")).hexdigest()[:8]
    return f"cam-{digest}"


def output_stem(row: Any, fallback_index: int | None = None) -> str:
    parts = [lead_slug(row, fallback_index)]
    camera = camera_hash(row)
    if camera:
        parts.append(camera)
    return "_".join(parts)


def legacy_index_stem(row: Any, fallback_index: int) -> str:
    adres = str(_row_get(row, "adres", f"rij_{fallback_index}") or f"rij_{fallback_index}")
    adres_slug = adres[:35].replace(" ", "_").replace(",", "").replace("/", "_")
    return f"{fallback_index:03d}_{adres_slug}"


def render_path(output_dir: Path, row: Any, fallback_index: int, preset_key: str) -> Path:
    return Path(output_dir) / f"{output_stem(row, fallback_index)}_{slugify(preset_key)}_render.jpg"


def streetview_path(output_dir: Path, row: Any, fallback_index: int) -> Path:
    return Path(output_dir) / f"{output_stem(row, fallback_index)}_streetview.jpg"


def legacy_render_candidates(output_dir: Path, row: Any, fallback_index: int, preset_key: str) -> list[Path]:
    stem = legacy_index_stem(row, fallback_index)
    return [
        Path(output_dir) / f"{stem}_{slugify(preset_key)}_render.jpg",
        Path(output_dir) / f"{stem}_render.jpg",
    ]


def legacy_streetview_candidates(output_dir: Path, row: Any, fallback_index: int) -> list[Path]:
    return [Path(output_dir) / f"{legacy_index_stem(row, fallback_index)}_streetview.jpg"]


def first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)
