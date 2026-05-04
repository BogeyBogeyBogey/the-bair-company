#!/usr/bin/env python3
"""
FacadePilot Street View Module
===============================
Haalt Google Street View foto's op voor adressen in Vlaanderen.
Vervangt de luchtfoto-module uit PoolPilot.

Functies:
  - fetch_streetview()      : Haal een Street View foto op
  - check_streetview()      : Check of Street View beschikbaar is (gratis)
  - calculate_heading()     : Bereken kijkrichting van straat naar huis
  - batch_fetch()           : Haal foto's op voor een hele CSV

Vereist: GOOGLE_API_KEY in .env bestand of als environment variable.
Kosten:  $7 per 1.000 foto's (metadata checks zijn gratis).
"""

import io
import math
import os
import time
from pathlib import Path

import requests
from PIL import Image
from dotenv import load_dotenv

HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

# ─── CONFIG ──────────────────────────────────────────────────────────────────

STREETVIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
STREETVIEW_META_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

DEFAULT_SIZE = "1024x768"
DEFAULT_PITCH = 5        # licht omhoog, maar niet te veel (anders dak ipv gevel)
DEFAULT_FOV = 65         # smaller = meer focus op het doelhuis, minder buren
MAX_PANO_DISTANCE = 80   # meter — als panorama > 80m weg staat, is het onbetrouwbaar
REQUEST_DELAY = 0.2

# Kosten per Google Street View call
# Static API: $7 per 1000 = $0.007 per foto. Metadata is gratis.
COST_PER_PHOTO_USD = 0.007
COST_PER_METADATA_USD = 0.0  # metadata is gratis

_streetview_cost_state = {
    "metadata_calls": 0,
    "photo_calls": 0,
    "estimated_cost_usd": 0.0,
}


def get_streetview_cost_state() -> dict:
    return dict(_streetview_cost_state)


def reset_streetview_cost_state():
    _streetview_cost_state.update({
        "metadata_calls": 0,
        "photo_calls": 0,
        "estimated_cost_usd": 0.0,
    })


# ─── HEADING BEREKENING ─────────────────────────────────────────────────────

def calculate_heading(street_lat: float, street_lon: float,
                      house_lat: float, house_lon: float) -> float:
    """Bereken kijkrichting (0-360°) van straat naar huis."""
    d_lon = math.radians(house_lon - street_lon)
    lat1 = math.radians(street_lat)
    lat2 = math.radians(house_lat)
    x = math.sin(d_lon) * math.cos(lat2)
    y = (math.cos(lat1) * math.sin(lat2)
         - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon))
    heading = math.degrees(math.atan2(x, y))
    return (heading + 360) % 360


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Afstand in meters tussen twee GPS-coördinaten (haversine)."""
    R = 6371000  # aardstraal in meter
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── METADATA CHECK ─────────────────────────────────────────────────────────

def check_streetview(lat: float, lon: float) -> dict:
    """Check of Street View beschikbaar is (GRATIS, geen kosten)."""
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY niet ingesteld. Voeg toe aan .env bestand.")

    params = {"location": f"{lat},{lon}", "key": GOOGLE_API_KEY}
    r = requests.get(STREETVIEW_META_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    _streetview_cost_state["metadata_calls"] += 1

    result = {
        "available": data.get("status") == "OK",
        "status": data.get("status", "UNKNOWN"),
        "pano_lat": None,
        "pano_lon": None,
        "pano_id": data.get("pano_id"),
    }
    if result["available"] and "location" in data:
        result["pano_lat"] = data["location"].get("lat")
        result["pano_lon"] = data["location"].get("lng")

    return result


# ─── STREETVIEW FOTO OPHALEN ────────────────────────────────────────────────

def fetch_streetview(lat: float, lon: float, heading: float = None,
                     size: str = DEFAULT_SIZE, pitch: int = DEFAULT_PITCH,
                     fov: int = DEFAULT_FOV) -> Image.Image:
    """
    Haal een Google Street View foto op voor een adres.
    Auto-heading: berekent richting van panorama naar huis als heading=None.
    """
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY niet ingesteld. Voeg toe aan .env bestand.")

    if heading is None:
        meta = check_streetview(lat, lon)
        if not meta["available"]:
            raise ValueError(f"Geen Street View beschikbaar voor {lat}, {lon}")
        if meta["pano_lat"] and meta["pano_lon"]:
            # Check of panorama dichtbij genoeg staat
            dist = haversine_distance(meta["pano_lat"], meta["pano_lon"], lat, lon)
            if dist > MAX_PANO_DISTANCE:
                raise ValueError(
                    f"Street View panorama te ver weg ({dist:.0f}m > {MAX_PANO_DISTANCE}m) — "
                    f"foto zou verkeerd gebouw tonen"
                )
            heading = calculate_heading(meta["pano_lat"], meta["pano_lon"], lat, lon)

    params = {
        "size": size,
        "location": f"{lat},{lon}",
        "pitch": pitch,
        "fov": fov,
        "key": GOOGLE_API_KEY,
    }
    if heading is not None:
        params["heading"] = round(heading, 1)

    for attempt in range(3):
        try:
            r = requests.get(STREETVIEW_URL, params=params, timeout=30)
            r.raise_for_status()
            _streetview_cost_state["photo_calls"] += 1
            _streetview_cost_state["estimated_cost_usd"] += COST_PER_PHOTO_USD
            return Image.open(io.BytesIO(r.content)).convert("RGB")
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(1)
            else:
                raise e


# ─── BATCH VERWERKING ───────────────────────────────────────────────────────

def batch_check_coverage(df, progress_callback=None) -> dict:
    """Check Street View coverage voor een hele DataFrame (gratis metadata API)."""
    available = 0
    unavailable = 0
    total = len(df)
    sv_available = []

    for i, (_, row) in enumerate(df.iterrows()):
        try:
            meta = check_streetview(row["lat"], row["lon"])
            sv_available.append(meta["available"])
            if meta["available"]:
                available += 1
            else:
                unavailable += 1
        except Exception:
            sv_available.append(False)
            unavailable += 1

        if progress_callback and (i + 1) % 20 == 0:
            progress_callback(i + 1, total, f"{available}/{i+1} beschikbaar")
        time.sleep(0.05)

    df["streetview_available"] = sv_available
    return {
        "available": available,
        "unavailable": unavailable,
        "total": total,
        "pct": round(available / total * 100, 1) if total > 0 else 0,
    }


def batch_fetch_streetview(df, output_dir: Path, progress_callback=None):
    """Haal Street View foto's op voor alle rijen. Slaat op als JPG."""
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(df)
    paths = []
    success = 0
    errors = 0

    for i, (_, row) in enumerate(df.iterrows()):
        adres = str(row.get("adres", f"rij_{i}"))
        safe_name = f"{i:03d}_{adres[:35].replace(' ', '_').replace(',', '').replace('/', '_')}"
        img_path = output_dir / f"{safe_name}_streetview.jpg"

        if img_path.exists():
            paths.append(str(img_path))
            success += 1
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ⏭️ {adres[:40]}... (bestaat al)")
            continue

        try:
            img = fetch_streetview(row["lat"], row["lon"])
            img.save(img_path, "JPEG", quality=90)
            paths.append(str(img_path))
            success += 1
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ✅ {adres[:40]}...")
        except Exception as e:
            paths.append("")
            errors += 1
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ❌ {adres[:40]}... ({e})")

        time.sleep(REQUEST_DELAY)

    df = df.copy()
    df["streetview_path"] = paths
    return df, {"success": success, "errors": errors, "total": total}


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import pandas as pd

    parser = argparse.ArgumentParser(description="FacadePilot Street View Module")
    parser.add_argument("--check", nargs=2, type=float, metavar=("LAT", "LON"),
                        help="Check Street View beschikbaarheid")
    parser.add_argument("--fetch", nargs=2, type=float, metavar=("LAT", "LON"),
                        help="Haal één Street View foto op → test_streetview.jpg")
    parser.add_argument("--batch-check", type=Path,
                        help="Check coverage voor een CSV")
    parser.add_argument("--batch-fetch", type=Path,
                        help="Haal foto's op voor een CSV")
    parser.add_argument("--output-dir", type=Path, default=HERE / "streetview",
                        help="Map voor foto's")
    args = parser.parse_args()

    if args.check:
        lat, lon = args.check
        result = check_streetview(lat, lon)
        print(f"Street View ({lat}, {lon}): {'✅ Beschikbaar' if result['available'] else '❌ Niet beschikbaar'}")
        if result["pano_lat"]:
            h = calculate_heading(result["pano_lat"], result["pano_lon"], lat, lon)
            print(f"  Heading: {h:.1f}°")
    elif args.fetch:
        lat, lon = args.fetch
        img = fetch_streetview(lat, lon)
        img.save("test_streetview.jpg", "JPEG", quality=90)
        print(f"✅ test_streetview.jpg ({img.size[0]}x{img.size[1]})")
    elif args.batch_check:
        df = pd.read_csv(args.batch_check, encoding="utf-8-sig")
        stats = batch_check_coverage(df)
        print(f"{stats['available']}/{stats['total']} beschikbaar ({stats['pct']}%)")
    elif args.batch_fetch:
        df = pd.read_csv(args.batch_fetch, encoding="utf-8-sig")
        df, stats = batch_fetch_streetview(df, args.output_dir)
        print(f"✅ {stats['success']}/{stats['total']} foto's, {stats['errors']} fouten")
    else:
        parser.print_help()
