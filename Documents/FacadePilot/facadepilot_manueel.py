#!/usr/bin/env python3
"""
FacadePilot Manueel Adres
==========================
Voeg één specifiek adres toe zonder volledige gemeente-scan.
Geocoded via Geopunt Location v4 (gratis, geen API key).
Optioneel perceel-lookup via GRB ADP (10-30s extra).

Use case: aannemer ziet huis op straat, wil meteen render + flyer.

Gebruik:
    from facadepilot_manueel import add_manual_address
    rec = add_manual_address("Sint-Annalaan 12 bus 3, 2840 Rumst")
    # rec is een dict met dezelfde kolommen als adresselectie

CLI:
    python3 facadepilot_manueel.py geocode --adres "Kerkstraat 1, 3300 Tienen"
    python3 facadepilot_manueel.py add --adres "..." --csv manual_leads.csv
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).parent.resolve()

GEOPUNT_URL = "https://geo.api.vlaanderen.be/geolocation/v4/Location"
MANUAL_CSV = HERE / "manual_leads.csv"

# Kolom-volgorde compatibel met facadepilot_adresselectie output
LEAD_COLUMNS = [
    "adres", "CAPAKEY", "perceel_m2", "bebouwd_m2", "bebouwd_ratio",
    "tuin_m2", "lat", "lon", "google_maps", "manual",
]


# ─── GEOCODER ──────────────────────────────────────────────────────────────

def _geopunt_query(query: str) -> dict | None:
    """Eén Geopunt-call. Returns eerste hit of None."""
    try:
        r = requests.get(GEOPUNT_URL, params={"q": query}, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("LocationResult", [])
        if not results:
            return None
        return results[0]
    except requests.RequestException:
        return None


def geocode_adres(adres: str) -> dict | None:
    """
    Geocodeer Vlaams adres → dict met lat/lon, gemeente, postcode, capakey indien beschikbaar.

    Strategie: probeer eerst met komma's, dan zonder (Geopunt is inconsistent).
    """
    adres = adres.strip()
    if not adres:
        return None

    # Try 1: zoals ingevoerd
    hit = _geopunt_query(adres)

    # Try 2: zonder komma's (soms verwart Geopunt komma met multi-search)
    if not hit and "," in adres:
        hit = _geopunt_query(adres.replace(",", " "))

    if not hit:
        return None

    loc = hit.get("Location", {})
    lat = loc.get("Lat_WGS84")
    lon = loc.get("Lon_WGS84")
    if lat is None or lon is None:
        return None

    return {
        "adres_normalized": hit.get("FormattedAddress", adres),
        "lat": float(lat),
        "lon": float(lon),
        "gemeente": hit.get("Municipality", ""),
        "postcode": str(hit.get("Zipcode", "")),
        "x_lambert": loc.get("X_Lambert72"),
        "y_lambert": loc.get("Y_Lambert72"),
        "match_type": hit.get("LocationType", ""),
    }


# ─── PERCEEL LOOKUP (optioneel) ───────────────────────────────────────────

def lookup_perceel(x_lambert: float, y_lambert: float) -> dict | None:
    """
    GRB ADP perceel-lookup op Lambert72-coordinaat.
    Returns {capakey, perceel_m2} of None.

    Duurt 10-30s, dus default uit voor snelle UI.
    """
    if x_lambert is None or y_lambert is None:
        return None
    url = "https://geo.api.vlaanderen.be/GRB/ogc/features/v1/collections/ADP/items"
    # Klein bbox rond het punt (1m radius)
    bbox = f"{x_lambert-1},{y_lambert-1},{x_lambert+1},{y_lambert+1}"
    try:
        r = requests.get(url, params={
            "f": "json",
            "limit": 1,
            "bbox": bbox,
            "bbox-crs": "http://www.opengis.net/def/crs/EPSG/0/31370",
            "crs": "http://www.opengis.net/def/crs/EPSG/0/31370",
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
        feats = data.get("features", [])
        if not feats:
            return None
        feat = feats[0]
        props = feat.get("properties", {})
        capakey = props.get("CAPAKEY", "")
        # Bereken perceel oppervlakte uit polygon
        from shapely.geometry import shape
        geom = shape(feat["geometry"])
        return {
            "CAPAKEY": capakey,
            "perceel_m2": round(geom.area, 1),
        }
    except Exception:
        return None


# ─── MAIN HELPER ──────────────────────────────────────────────────────────

def add_manual_address(adres: str, with_perceel: bool = False) -> dict | None:
    """
    Verwerk één manueel adres tot een lead-dict (zelfde kolommen als adresselectie).

    Returns dict of None als geocoding mislukt.
    """
    geo = geocode_adres(adres)
    if not geo:
        return None

    rec = {
        "adres": geo["adres_normalized"],
        "CAPAKEY": "",
        "perceel_m2": None,
        "bebouwd_m2": None,
        "bebouwd_ratio": None,
        "tuin_m2": None,
        "lat": geo["lat"],
        "lon": geo["lon"],
        "google_maps": f"https://www.google.com/maps/@{geo['lat']},{geo['lon']},3a,75y,0h,90t/data=!3m1!1e1",
        "manual": "1",
    }

    if with_perceel:
        perceel = lookup_perceel(geo["x_lambert"], geo["y_lambert"])
        if perceel:
            rec["CAPAKEY"] = perceel["CAPAKEY"]
            rec["perceel_m2"] = perceel["perceel_m2"]

    # Fake CAPAKEY als er geen is — anders kan de CRM hem niet uniek tracken
    if not rec["CAPAKEY"]:
        rec["CAPAKEY"] = f"MAN-{int(time.time())}-{abs(hash(adres)) % 10000}"

    return rec


def append_to_csv(rec: dict, csv_path: Path = MANUAL_CSV):
    """Append rec aan manual_leads.csv (maakt header als file niet bestaat)."""
    csv_path = Path(csv_path)
    write_header = not csv_path.exists()
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEAD_COLUMNS)
        if write_header:
            w.writeheader()
        w.writerow({k: rec.get(k, "") for k in LEAD_COLUMNS})


def list_manual_addresses(csv_path: Path = MANUAL_CSV) -> list:
    """Lijst alle manueel toegevoegde adressen."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def clear_manual(csv_path: Path = MANUAL_CSV):
    """Wis manual_leads.csv."""
    csv_path = Path(csv_path)
    if csv_path.exists():
        csv_path.unlink()


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Manueel Adres")
    sub = parser.add_subparsers(dest="cmd")

    p_g = sub.add_parser("geocode", help="Test geocoding van een adres")
    p_g.add_argument("--adres", required=True)

    p_a = sub.add_parser("add", help="Voeg adres toe aan manual_leads.csv")
    p_a.add_argument("--adres", required=True)
    p_a.add_argument("--with-perceel", action="store_true")
    p_a.add_argument("--csv", type=Path, default=MANUAL_CSV)

    p_l = sub.add_parser("list", help="Lijst manueel toegevoegde adressen")

    p_c = sub.add_parser("clear", help="Wis manual_leads.csv")

    args = parser.parse_args()

    if args.cmd == "geocode":
        geo = geocode_adres(args.adres)
        if not geo:
            sys.exit("❌ Geen match")
        print(f"✅ {geo['adres_normalized']}")
        print(f"   Lat/Lon: {geo['lat']:.6f}, {geo['lon']:.6f}")
        print(f"   Gemeente: {geo['gemeente']} ({geo['postcode']})")
        print(f"   Match: {geo['match_type']}")

    elif args.cmd == "add":
        rec = add_manual_address(args.adres, with_perceel=args.with_perceel)
        if not rec:
            sys.exit("❌ Geocoding mislukt")
        append_to_csv(rec, args.csv)
        print(f"✅ Toegevoegd: {rec['adres']}")
        print(f"   CAPAKEY: {rec['CAPAKEY']}")
        if rec.get("perceel_m2"):
            print(f"   Perceel: {rec['perceel_m2']:.0f} m²")

    elif args.cmd == "list":
        items = list_manual_addresses()
        print(f"{len(items)} manueel adressen:")
        for it in items:
            print(f"  {it['adres']}")

    elif args.cmd == "clear":
        clear_manual()
        print("✅ Manual leads gewist")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
