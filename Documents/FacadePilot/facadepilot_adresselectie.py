#!/usr/bin/env python3
"""
FacadePilot Adresselectie Tool
===============================
Genereert een lijst van adressen met woningen die geschikt zijn voor gevelrenovatie.

Workflow:
1. Haal alle kadastrale percelen (ADP) op via GRB OGC API
2. Haal alle gebouwen (GBG) op in hetzelfde gebied
3. Bereken woninggrootte (bebouwd oppervlak) en perceelgrootte
4. Filter op minimale woninggrootte (grotere gevel = meer impact)
5. Koppel adressen via GRB Adres-collectie
6. Exporteer CSV met adres, perceelgrootte, woninggrootte, coördinaten

Focus: OUDERE woningen (jaren '60-'90) met grotere geveloppervlakken.
Data: Vlaamse open data (GRB), gratis, geen API-key nodig.

Gebruik:
    python facadepilot_adresselectie.py --niscode 11005 --min-woning 60
    python facadepilot_adresselectie.py --niscode 12040 --output willebroek_leads.csv
"""

import argparse
import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

# ─── CONFIG ────────────────────────────────────────────────────────────────────
GRB_BASE = "https://geo.api.vlaanderen.be/GRB/ogc/features/v1/collections"
CRS_LAMBERT = "http://www.opengis.net/def/crs/EPSG/0/31370"
CRS_WGS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"

PAGE_SIZE = 1000
REQUEST_DELAY = 0.3

# Voorbeeldgemeenten — focus op oudere wijken (jaren '60-'90)
VOORBEELD_GEMEENTEN = {
    "11001": "Aartselaar",
    "11002": "Antwerpen",
    "11004": "Boechout",
    "11005": "Boom",
    "11007": "Borsbeek",
    "11008": "Brasschaat",
    "11009": "Brecht",
    "11013": "Edegem",
    "11016": "Essen",
    "11018": "Hemiksem",
    "11021": "Hove",
    "11022": "Kalmthout",
    "11023": "Kapellen",
    "11024": "Kontich",
    "11025": "Lint",
    "11029": "Mortsel",
    "11030": "Niel",
    "11035": "Ranst",
    "11037": "Rumst",
    "11038": "Schelle",
    "11039": "Schilde",
    "11040": "Schoten",
    "11044": "Stabroek",
    "11050": "Wijnegem",
    "11052": "Wommelgem",
    "11053": "Wuustwezel",
    "11054": "Zandhoven",
    "11055": "Zoersel",
    "11056": "Zwijndrecht",
    "11057": "Malle",
    "12025": "Mechelen",
    "12040": "Willebroek",
    "24137": "Glabbeek",
}


# ─── API HELPERS ───────────────────────────────────────────────────────────

def fetch_features(collection: str, niscode: str = None, bbox: str = None,
                   crs: str = CRS_LAMBERT, max_features: int = None) -> list:
    """Haal features op van de GRB OGC API met automatische paginering."""
    url = f"{GRB_BASE}/{collection}/items"
    all_features = []
    offset = 0

    while True:
        params = {
            "f": "json",
            "limit": PAGE_SIZE,
            "startIndex": offset,
            "crs": crs,
        }
        if niscode:
            params["filter"] = f"NISCODE='{niscode}'"
            params["filter-lang"] = "cql-text"
        if bbox:
            params["bbox"] = bbox
            params["bbox-crs"] = crs

        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ⚠ API fout bij offset {offset}: {e}")
            break

        data = resp.json()
        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        count = len(all_features)
        print(f"  → {count} {collection}-features opgehaald...", end="\r")

        if max_features and count >= max_features:
            all_features = all_features[:max_features]
            break

        num_returned = data.get("numberReturned", len(features))
        if num_returned < PAGE_SIZE:
            break

        offset += PAGE_SIZE
        time.sleep(REQUEST_DELAY)

    print(f"  ✓ {len(all_features)} {collection}-features opgehaald" + " " * 20)
    return all_features


def features_to_geodataframe(features: list, crs: str = "EPSG:31370") -> gpd.GeoDataFrame:
    """Converteer GeoJSON features naar een GeoDataFrame."""
    if not features:
        return gpd.GeoDataFrame()

    geometries = []
    properties = []
    for f in features:
        try:
            geom = shape(f["geometry"])
            if geom.is_valid:
                geometries.append(geom)
                properties.append(f.get("properties", {}))
        except Exception:
            continue

    if not geometries:
        return gpd.GeoDataFrame()
    return gpd.GeoDataFrame(properties, geometry=geometries, crs=crs)


# ─── CORE LOGIC ───────────────────────────────────────────────────────────────

def bereken_woninggrootte(percelen: gpd.GeoDataFrame, gebouwen: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Bereken woninggrootte (bebouwd oppervlak) per perceel.
    Voor gevelrenovatie is de woninggrootte belangrijker dan tuingrootte.
    """
    print("\n📐 Woninggrootte berekenen...")

    percelen = percelen.copy()
    percelen["perceel_m2"] = percelen.geometry.area.round(1)

    if gebouwen.empty:
        percelen["bebouwd_m2"] = 0.0
        percelen["tuin_m2"] = percelen["perceel_m2"]
        return percelen

    print("  → Gebouwen koppelen aan percelen (spatial join)...")

    bebouwd_per_perceel = []
    gebouwen_sindex = gebouwen.sindex

    for idx, perceel in percelen.iterrows():
        possible_matches_idx = list(gebouwen_sindex.intersection(perceel.geometry.bounds))
        if not possible_matches_idx:
            bebouwd_per_perceel.append(0.0)
            continue

        possible_matches = gebouwen.iloc[possible_matches_idx]
        total_bebouwd = 0.0
        for _, gebouw in possible_matches.iterrows():
            try:
                intersection = perceel.geometry.intersection(gebouw.geometry)
                total_bebouwd += intersection.area
            except Exception:
                continue

        bebouwd_per_perceel.append(round(total_bebouwd, 1))

    percelen["bebouwd_m2"] = bebouwd_per_perceel
    percelen["tuin_m2"] = (percelen["perceel_m2"] - percelen["bebouwd_m2"]).round(1)

    print(f"  ✓ Woninggrootte berekend voor {len(percelen)} percelen")
    return percelen


def koppel_adressen(percelen: gpd.GeoDataFrame, niscode: str) -> gpd.GeoDataFrame:
    """Koppel adressen aan percelen via GRB Adres-collectie."""
    print("\n📬 Adressen ophalen en koppelen...")

    adres_features = fetch_features("Adres", niscode=niscode)
    if not adres_features:
        print("  ⚠ Geen adressen gevonden")
        percelen["adres"] = ""
        return percelen

    adressen = features_to_geodataframe(adres_features)
    if adressen.empty:
        percelen["adres"] = ""
        return percelen

    print(f"  → {len(adressen)} adressen koppelen aan percelen...")

    try:
        joined = gpd.sjoin(adressen, percelen[["geometry", "CAPAKEY"]], how="inner", predicate="within")

        adres_cols = []
        for col in ["STRAATNM", "HUISNR", "APPTNR", "BUSNR", "POSTCODE", "GEMEENTE"]:
            if col in joined.columns:
                adres_cols.append(col)

        if "ADRESNAAM" in joined.columns or adres_cols:
            def maak_adres(groep):
                eerste = groep.iloc[0]
                if "ADRESNAAM" in groep.columns and pd.notna(eerste.get("ADRESNAAM")):
                    return str(eerste["ADRESNAAM"])
                parts = []
                if "STRAATNM" in groep.columns and pd.notna(eerste.get("STRAATNM")):
                    parts.append(str(eerste["STRAATNM"]))
                if "HUISNR" in groep.columns and pd.notna(eerste.get("HUISNR")):
                    parts.append(str(eerste["HUISNR"]))
                if "BUSNR" in groep.columns and pd.notna(eerste.get("BUSNR")) and str(eerste.get("BUSNR", "")) != "":
                    parts.append(f"bus {eerste['BUSNR']}")
                adres = " ".join(parts)
                postcode_gemeente = []
                if "POSTCODE" in groep.columns and pd.notna(eerste.get("POSTCODE")):
                    postcode_gemeente.append(str(int(eerste["POSTCODE"])))
                if "GEMEENTE" in groep.columns and pd.notna(eerste.get("GEMEENTE")):
                    postcode_gemeente.append(str(eerste["GEMEENTE"]))
                if postcode_gemeente:
                    adres += ", " + " ".join(postcode_gemeente)
                return adres

            adres_per_perceel = joined.groupby("CAPAKEY").apply(maak_adres, include_groups=False).reset_index()
            adres_per_perceel.columns = ["CAPAKEY", "adres"]
            percelen = percelen.merge(adres_per_perceel, on="CAPAKEY", how="left")
            percelen["adres"] = percelen["adres"].fillna("")
        else:
            percelen["adres"] = ""
    except Exception as e:
        print(f"  ⚠ Adreskoppeling mislukt: {e}")
        percelen["adres"] = ""

    gekoppeld = (percelen["adres"] != "").sum()
    print(f"  ✓ {gekoppeld}/{len(percelen)} percelen hebben een adres")
    return percelen


def genereer_google_maps_link(lat: float, lon: float) -> str:
    """Google Maps link (straatweergave) voor snelle visuele verificatie."""
    return (
        f"https://www.google.com/maps/@{lat},{lon},3a,75y,0h,90t"
        f"/data=!3m1!1e1"
    )


def genereer_streetview_link(lat: float, lon: float) -> str:
    """Directe Google Street View link."""
    return f"https://www.google.com/maps/@{lat},{lon},3a,75y,0h,90t/data=!3m1!1e1"


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="FacadePilot Adresselectie — vind woningen geschikt voor gevelrenovatie",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  python facadepilot_adresselectie.py --niscode 11005
  python facadepilot_adresselectie.py --niscode 12040 --min-woning 60 --output willebroek.csv
  python facadepilot_adresselectie.py --lijst-gemeenten
        """
    )

    parser.add_argument("--niscode", type=str, help="NIS-code gemeente (bijv. 11005 = Boom)")
    parser.add_argument("--min-woning", type=float, default=60.0,
                        help="Min. woninggrootte m² (standaard: 60 — grotere gevel = meer impact)")
    parser.add_argument("--min-perceel", type=float, default=100.0,
                        help="Min. perceelgrootte m² (standaard: 100)")
    parser.add_argument("--max-perceel", type=float, default=5000.0,
                        help="Max. perceelgrootte m² (standaard: 5000)")
    parser.add_argument("--max-woning", type=float, default=350.0,
                        help="Max. woninggrootte m² (standaard: 350 — filtert loodsen/magazijnen)")
    parser.add_argument("--max-bebouwd-ratio", type=float, default=0.75,
                        help="Max. bebouwd/perceel ratio (standaard: 0.75 — filtert industriebouw)")
    parser.add_argument("--max-results", type=int, default=None,
                        help="Max. aantal percelen (voor testen)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV")
    parser.add_argument("--lijst-gemeenten", action="store_true",
                        help="Toon bekende gemeenten")

    args = parser.parse_args()

    if args.lijst_gemeenten:
        print("\n📋 Bekende gemeenten:\n")
        for code, naam in sorted(VOORBEELD_GEMEENTEN.items(), key=lambda x: x[1]):
            print(f"  {code}  {naam}")
        return

    if not args.niscode:
        parser.error("--niscode is verplicht")

    niscode = args.niscode
    gemeente = VOORBEELD_GEMEENTEN.get(niscode, f"Gemeente {niscode}")
    output_file = args.output or f"facadepilot_leads_{niscode}.csv"

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  🏠 FacadePilot Adresselectie Tool                          ║
╚══════════════════════════════════════════════════════════════╝

  Gemeente:          {gemeente} (NIS {niscode})
  Min. woninggrootte: {args.min_woning} m²
  Perceelgrootte:    {args.min_perceel}–{args.max_perceel} m²
  Output:            {output_file}
""")

    # STAP 1: Percelen ophalen
    print("=" * 60)
    print("STAP 1: Kadastrale percelen ophalen")
    print("=" * 60)

    perceel_features = fetch_features("ADP", niscode=niscode, max_features=args.max_results)
    if not perceel_features:
        print("❌ Geen percelen gevonden.")
        sys.exit(1)

    percelen = features_to_geodataframe(perceel_features)
    print(f"  → {len(percelen)} percelen geladen")

    percelen["_area"] = percelen.geometry.area
    percelen = percelen[
        (percelen["_area"] >= args.min_perceel) &
        (percelen["_area"] <= args.max_perceel)
    ].copy()
    percelen.drop(columns=["_area"], inplace=True)
    print(f"  → {len(percelen)} percelen na filter ({args.min_perceel}–{args.max_perceel}m²)")

    if percelen.empty:
        print("❌ Geen percelen over na filtering.")
        sys.exit(1)

    # STAP 2: Gebouwen ophalen
    print(f"\n{'=' * 60}")
    print("STAP 2: Gebouwen ophalen")
    print("=" * 60)

    bounds = percelen.total_bounds
    bbox_str = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
    gebouw_features = fetch_features("GBG", bbox=bbox_str)
    gebouwen = features_to_geodataframe(gebouw_features)
    print(f"  → {len(gebouwen)} gebouwen geladen")

    # STAP 3: Woninggrootte berekenen
    print(f"\n{'=' * 60}")
    print("STAP 3: Woninggrootte berekenen")
    print("=" * 60)

    percelen = bereken_woninggrootte(percelen, gebouwen)

    # Filter: moet gebouw hebben, minimale EN maximale woninggrootte, ratio-check
    percelen["bebouwd_ratio"] = (percelen["bebouwd_m2"] / percelen["perceel_m2"]).round(3)
    percelen["bebouwd_ratio"] = percelen["bebouwd_ratio"].fillna(0)

    leads = percelen[
        (percelen["bebouwd_m2"] >= args.min_woning) &
        (percelen["bebouwd_m2"] <= args.max_woning) &
        (percelen["bebouwd_ratio"] <= args.max_bebouwd_ratio)
    ].copy()

    # Log wat er gefilterd is
    te_groot = (percelen["bebouwd_m2"] > args.max_woning).sum()
    te_vol = ((percelen["bebouwd_ratio"] > args.max_bebouwd_ratio) & (percelen["bebouwd_m2"] <= args.max_woning)).sum()
    print(f"\n  🏠 {len(leads)} woningen na filter ({args.min_woning}–{args.max_woning}m²)")
    if te_groot > 0:
        print(f"  🏭 {te_groot} percelen uitgesloten: te groot (>{args.max_woning}m² — vermoedelijk loods/magazijn)")
    if te_vol > 0:
        print(f"  🏗️  {te_vol} percelen uitgesloten: te volgebouwd (>{args.max_bebouwd_ratio*100:.0f}% — vermoedelijk industrieel)")

    if leads.empty:
        print("❌ Geen geschikte percelen gevonden.")
        sys.exit(1)

    # STAP 4: Adressen koppelen
    print(f"\n{'=' * 60}")
    print("STAP 4: Adressen koppelen")
    print("=" * 60)

    leads = koppel_adressen(leads, niscode)

    # STAP 5: Coördinaten en export
    print(f"\n{'=' * 60}")
    print("STAP 5: Export voorbereiden")
    print("=" * 60)

    centroids_lambert = leads.geometry.centroid
    centroids_wgs84 = gpd.GeoSeries(centroids_lambert, crs="EPSG:31370").to_crs("EPSG:4326")
    leads["lat"] = centroids_wgs84.y.round(6)
    leads["lon"] = centroids_wgs84.x.round(6)
    leads["google_maps"] = leads.apply(
        lambda row: genereer_google_maps_link(row["lat"], row["lon"]), axis=1
    )
    leads["streetview_link"] = leads.apply(
        lambda row: genereer_streetview_link(row["lat"], row["lon"]), axis=1
    )

    export_cols = [
        "adres", "CAPAKEY", "perceel_m2", "bebouwd_m2", "tuin_m2",
        "lat", "lon", "google_maps", "streetview_link"
    ]
    export_cols = [c for c in export_cols if c in leads.columns]

    # Sorteer op woninggrootte (grootste eerst — meeste geveloppervlak)
    leads_export = leads[export_cols].sort_values("bebouwd_m2", ascending=False)
    leads_export.to_csv(output_file, index=False, encoding="utf-8-sig")

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  ✅ KLAAR — Resultaten                                      ║
╚══════════════════════════════════════════════════════════════╝

  Gemeente:                {gemeente}
  Totaal percelen:         {len(percelen)}
  Geschikt (woning ≥{args.min_woning}m²): {len(leads)} ({len(leads)/len(percelen)*100:.1f}%)

  Gem. woninggrootte:      {leads['bebouwd_m2'].mean():.0f} m²
  Grootste woning:         {leads['bebouwd_m2'].max():.0f} m²
  Kleinste woning:         {leads['bebouwd_m2'].min():.0f} m²

  📄 Bestand: {output_file}

  💡 Tip: Klik op de Street View-links in de CSV om de gevels
     visueel te beoordelen.
""")


if __name__ == "__main__":
    main()
