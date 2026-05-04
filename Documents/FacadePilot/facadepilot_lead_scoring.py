#!/usr/bin/env python3
"""
FacadePilot Lead Scoring — Rangschik leads voor gevelrenovatie.

Scores gebaseerd op 4 metrics:
  1. Woninggrootte       (35%) — meer geveloppervlak = meer renovatie-impact
  2. Buurtinkomen        (35%) — gevelrenovatie is duur (€12K-€50K+)
  3. Perceelgrootte      (15%) — proxy voor property-waarde
  4. Bebouwd ratio       (15%) — hoger = meer geveloppervlak per perceel

Gebruik:
  python3 facadepilot_lead_scoring.py --input facadepilot_leads_11005.csv
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent.resolve()

# ─── SCORING CONFIG ──────────────────────────────────────────────────────────

# Gewichten met bouwjaar/huistype (5 metrics, sommen = 1.00)
WEIGHTS = {
    "bebouwd_m2":    0.30,   # Meer geveloppervlak = meer impact
    "inkomen":       0.30,   # Gevelrenovatie is een serieuze investering
    "perceel_m2":    0.10,   # Algehele property-waarde
    "bebouwd_ratio": 0.10,   # Hoger = meer bebouwing per perceel
    "huistype":      0.20,   # Ouder/vrijstaand/halfopen profiel = beter
}

# Minimum drempels
MIN_BEBOUWD_M2 = 60      # Kleiner dan 60m² = te klein (garage, bijgebouw)

# Plafonds (diminishing returns)
CAP_BEBOUWD_M2 = 400     # 400+ m² = allemaal "grote woning"
CAP_PERCEEL_M2 = 3000
CAP_INKOMEN = 55000

# Lead klassen
LEAD_CLASSES = [
    (80, "A+", "Topkandidaat — welvarende buurt, groot huis, veel geveloppervlak"),
    (60, "A",  "Zeer goede kandidaat — ruim boven gemiddeld"),
    (40, "B",  "Goede kandidaat — gemiddeld profiel"),
    (20, "C",  "Matige kandidaat — kleiner huis of bescheidener buurt"),
    (0,  "D",  "Zwakke kandidaat — beperkt geveloppervlak of laag inkomen"),
]

# Statbel bestanden
SHAPEFILE_DIR = "sh_statbel_statistical_sectors_20200101.shp"
SHAPEFILE_NAME = "sh_statbel_statistical_sectors_20200101.shp"
INCOME_FILE = "TF_PSNL_INC_TAX_SECTOR.xlsx"

# Optioneel: Statbel "Woningen naar bouwjaar" per statistische sector
# Download via: https://statbel.fgov.be/nl/open-data
# Filenames variëren — we proberen een paar gangbare namen.
BUILDING_AGE_FILE_CANDIDATES = [
    "TF_BUILDING_AGE_SECTOR.xlsx",
    "TF_BUILDING_PERIOD_SECTOR.xlsx",
    "TF_DWELLINGS_BY_BUILDING_PERIOD.xlsx",
]


# ─── HUISTYPE CLASSIFICATIE ─────────────────────────────────────────────────
# Op basis van perceel + bebouwd_ratio bepalen we een huistype.
# Voor gevelrenovatie zijn vrijstaand/halfopen woningen het meest interessant
# (meer geveloppervlak zichtbaar, hogere gemiddelde investeringscapaciteit).
#
# huistype_score: 0-100, hoger = betere kandidaat voor gevelrenovatie

def classify_huistype(perceel_m2: float, bebouwd_ratio: float) -> tuple:
    """
    Classificeer de woning op basis van geometrische kenmerken.
    Returns (huistype: str, score: float 0-100).
    """
    if pd.isna(perceel_m2) or pd.isna(bebouwd_ratio):
        return ("onbekend", 50.0)

    # Vrijstaand met ruime tuin — typisch jaren '60-'80, sweet spot
    if perceel_m2 >= 400 and bebouwd_ratio <= 0.30:
        return ("vrijstaand_ruim", 90.0)

    # Vrijstaand klein of halfopen ruim — ook zeer goed
    if perceel_m2 >= 250 and bebouwd_ratio <= 0.45:
        return ("halfopen_ruim", 80.0)

    # Halfopen / kleinere vrijstaande
    if perceel_m2 >= 180 and bebouwd_ratio <= 0.55:
        return ("halfopen", 70.0)

    # Klassiek rijhuis — front + soms zijkant zichtbaar
    if perceel_m2 >= 100 and bebouwd_ratio <= 0.75:
        return ("rijwoning", 55.0)

    # Klein rijhuis stadskern — vaak oude gevels, soms al gerenoveerd
    if perceel_m2 >= 60 and bebouwd_ratio <= 0.85:
        return ("stadswoning", 45.0)

    # Volgebouwd kleine perceel — vermoedelijk appartement of bijgebouw
    return ("appartement_dicht", 25.0)


# ─── BUILDING AGE LOOKUP (optioneel) ────────────────────────────────────────

_building_age_lookup = None  # dict: sector_id -> pct_pre_1990


def _load_building_age_data():
    """Probeer Statbel bouwjaar-data te laden. Returns None als niet beschikbaar."""
    global _building_age_lookup
    if _building_age_lookup is not None:
        return _building_age_lookup if _building_age_lookup else None

    parent = HERE.parent
    age_path = None
    for fname in BUILDING_AGE_FILE_CANDIDATES:
        for search_dir in [HERE, parent]:
            candidate = search_dir / fname
            if candidate.exists():
                age_path = candidate
                break
        if age_path:
            break

    if not age_path:
        _building_age_lookup = {}  # marker: gezocht maar niet gevonden
        return None

    try:
        df = pd.read_excel(age_path)
    except Exception as e:
        print(f"   ⚠️  Kon {age_path.name} niet lezen: {e}")
        _building_age_lookup = {}
        return None

    # Detecteer sector-kolom + bouwjaar-kolommen
    sector_col = None
    for c in ["CD_SECTOR", "SECTOR_CD", "CS01012020", "CS_SECTOR"]:
        if c in df.columns:
            sector_col = c
            break

    if not sector_col:
        print(f"   ⚠️  {age_path.name}: geen herkenbare sector-kolom gevonden")
        _building_age_lookup = {}
        return None

    # Zoek "pre-1990" of vergelijkbare kolommen
    pre_1990_cols = [c for c in df.columns if any(
        token in c.upper() for token in ["VOOR_1900", "1900_1918", "1919_1945", "1946_1970", "1971_1990", "PRE_1990"]
    )]

    if not pre_1990_cols:
        print(f"   ⚠️  {age_path.name}: geen bouwjaar-kolommen herkend")
        _building_age_lookup = {}
        return None

    # Som percentages pre-1990
    df["_pct_pre_1990"] = df[pre_1990_cols].sum(axis=1)
    lookup = dict(zip(df[sector_col].astype(str), df["_pct_pre_1990"]))
    _building_age_lookup = lookup
    print(f"   📊 Bouwjaar-data: {len(lookup)} sectoren, {len(pre_1990_cols)} pre-1990 kolommen")
    return lookup


# ─── INCOME LOOKUP ──────────────────────────────────────────────────────────

_income_lookup = None

def _load_income_data():
    """Laad Statbel inkomensdata (shapefile + Excel)."""
    global _income_lookup
    if _income_lookup is not None:
        return _income_lookup

    # Zoek in FacadePilot map EN parent map (PoolPilot)
    parent = HERE.parent
    shp_path = None
    inc_path = None

    for search_dir in [HERE, parent]:
        candidate_shp = search_dir / SHAPEFILE_DIR / SHAPEFILE_NAME
        candidate_inc = search_dir / INCOME_FILE
        if candidate_shp.exists() and shp_path is None:
            shp_path = candidate_shp
        if candidate_inc.exists() and inc_path is None:
            inc_path = candidate_inc

    if not shp_path or not inc_path:
        print(f"   ⚠️  Statbel bestanden niet gevonden — buurtinkomen overgeslagen")
        return None

    try:
        import geopandas as gpd
    except ImportError:
        print("   ⚠️  geopandas niet geïnstalleerd")
        return None

    t0 = time.time()
    gdf = gpd.read_file(shp_path)
    gdf = gdf[gdf["C_REGIO"] == "02000"].copy()

    inc = pd.read_excel(inc_path)
    latest_year = inc["CD_YEAR"].max()
    inc_latest = inc[inc["CD_YEAR"] == latest_year][
        ["CD_SECTOR", "MS_MEDIAN_NET_TAXABLE_INC", "MS_AVG_TOT_NET_TAXABLE_INC"]
    ].copy()

    gdf = gdf.merge(inc_latest, left_on="CS01012020", right_on="CD_SECTOR", how="left")
    gdf = gdf.rename(columns={
        "MS_MEDIAN_NET_TAXABLE_INC": "mediaan_inkomen",
        "MS_AVG_TOT_NET_TAXABLE_INC": "gemiddeld_inkomen",
    })
    gdf.sindex  # spatial index

    elapsed = time.time() - t0
    n_with = gdf["mediaan_inkomen"].notna().sum()
    print(f"   📊 Statbel inkomensdata geladen: {n_with} sectoren, jaar {latest_year} ({elapsed:.1f}s)")

    _income_lookup = gdf
    return gdf


def enrich_with_income(df: pd.DataFrame) -> pd.DataFrame:
    """Voeg buurtinkomen + (optioneel) bouwjaar toe via spatial lookup."""
    gdf = _load_income_data()
    age_lookup = _load_building_age_data()  # kan None zijn

    if gdf is None:
        df["mediaan_inkomen"] = np.nan
        df["sector_naam"] = ""
        df["pct_pre_1990"] = np.nan
        df["sector_id"] = ""
        return df

    from pyproj import Transformer
    from shapely.geometry import Point

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:31370", always_xy=True)
    incomes = []
    sector_names = []
    sector_ids = []
    pct_pre_1990 = []

    for _, row in df.iterrows():
        lat, lon = row.get("lat"), row.get("lon")
        if pd.isna(lat) or pd.isna(lon):
            incomes.append(np.nan)
            sector_names.append("")
            sector_ids.append("")
            pct_pre_1990.append(np.nan)
            continue

        x, y = transformer.transform(lon, lat)
        point = Point(x, y)

        possible_idx = list(gdf.sindex.intersection(point.bounds))
        if possible_idx:
            matches = gdf.iloc[possible_idx]
            actual = matches[matches.geometry.contains(point)]
            if len(actual) > 0:
                row_match = actual.iloc[0]
                incomes.append(row_match.get("mediaan_inkomen", np.nan))
                sector_names.append(row_match.get("T_SEC_NL", ""))
                sid = str(row_match.get("CS01012020", row_match.get("CD_SECTOR", "")))
                sector_ids.append(sid)
                # Bouwjaar lookup
                if age_lookup and sid in age_lookup:
                    pct_pre_1990.append(age_lookup[sid])
                else:
                    pct_pre_1990.append(np.nan)
                continue

        incomes.append(np.nan)
        sector_names.append("")
        sector_ids.append("")
        pct_pre_1990.append(np.nan)

    df["mediaan_inkomen"] = incomes
    df["sector_naam"] = sector_names
    df["sector_id"] = sector_ids
    df["pct_pre_1990"] = pct_pre_1990

    n_found = sum(1 for v in incomes if not pd.isna(v))
    print(f"   📍 Buurtinkomen gekoppeld: {n_found}/{len(df)} adressen")
    if age_lookup:
        n_age = sum(1 for v in pct_pre_1990 if not pd.isna(v))
        print(f"   🏛️  Bouwjaar gekoppeld: {n_age}/{len(df)} adressen")
    else:
        print(f"   ℹ️  Bouwjaar-data overgeslagen (geen Statbel bouwjaar-bestand gevonden)")
        print(f"      Download via https://statbel.fgov.be/nl/open-data en plaats in {HERE.name}/")
    return df


# ─── SCORING ENGINE ──────────────────────────────────────────────────────────

def _percentile_score(series: pd.Series, cap: float = None) -> pd.Series:
    s = series.copy().astype(float)
    if cap:
        s = s.clip(upper=cap)
    return (s.rank(method="average", pct=True) * 100).round(1)


def _apply_penalty(score: pd.Series, metric: pd.Series,
                   threshold: float, penalty: float = 30) -> pd.Series:
    penalized = score.copy()
    mask = metric < threshold
    penalized[mask] = (penalized[mask] - penalty).clip(lower=0)
    return penalized


def score_leads(df: pd.DataFrame) -> pd.DataFrame:
    """Voeg lead scoring toe voor gevelrenovatie."""
    scored = df.copy()

    # Stap 1: Buurtinkomen + bouwjaar
    has_income_data = False
    has_age_data = False
    if "lat" in scored.columns and "lon" in scored.columns:
        scored = enrich_with_income(scored)
        has_income_data = scored["mediaan_inkomen"].notna().any()
        has_age_data = scored.get("pct_pre_1990") is not None and scored["pct_pre_1990"].notna().any()

    # Stap 2: Afgeleide metrics
    scored["bebouwd_ratio"] = np.where(
        scored["perceel_m2"] > 0,
        scored["bebouwd_m2"] / scored["perceel_m2"],
        0
    )

    # Stap 2b: Huistype classificatie (altijd uit perceel + ratio)
    huistype_results = scored.apply(
        lambda r: classify_huistype(r["perceel_m2"], r["bebouwd_ratio"]),
        axis=1
    )
    scored["huistype"] = [h[0] for h in huistype_results]
    scored["huistype_score"] = [h[1] for h in huistype_results]

    # Bouwjaar-bonus: als pct_pre_1990 beschikbaar is, gebruiken we
    # die om de huistype_score te verfijnen (oudere buurt = bonus).
    if has_age_data:
        # pct_pre_1990 0-100 → bonus -10..+15 op huistype_score
        bonus = ((scored["pct_pre_1990"].fillna(50) - 50) / 50 * 15).clip(-10, 15)
        scored["huistype_score"] = (scored["huistype_score"] + bonus).clip(0, 100).round(1)

    # Stap 3: Percentiel-scores
    scored["score_woning"]   = _percentile_score(scored["bebouwd_m2"], cap=CAP_BEBOUWD_M2)
    scored["score_perceel"]  = _percentile_score(scored["perceel_m2"], cap=CAP_PERCEEL_M2)
    scored["score_ratio"]    = _percentile_score(scored["bebouwd_ratio"])
    scored["score_huistype"] = scored["huistype_score"]  # is al 0-100

    if has_income_data:
        scored["score_inkomen"] = _percentile_score(scored["mediaan_inkomen"], cap=CAP_INKOMEN)
        scored["score_inkomen"] = scored["score_inkomen"].fillna(50.0)
    else:
        scored["score_inkomen"] = 50.0

    # Stap 4: Gewogen totaalscore (5 metrics)
    if has_income_data:
        scored["lead_score"] = (
            scored["score_woning"]   * WEIGHTS["bebouwd_m2"]
            + scored["score_inkomen"]  * WEIGHTS["inkomen"]
            + scored["score_perceel"]  * WEIGHTS["perceel_m2"]
            + scored["score_ratio"]    * WEIGHTS["bebouwd_ratio"]
            + scored["score_huistype"] * WEIGHTS["huistype"]
        ).round(1)
    else:
        # Zonder inkomen: herverdeel gewicht (huistype krijgt 25%)
        scored["lead_score"] = (
            scored["score_woning"]   * 0.40
            + scored["score_perceel"]  * 0.20
            + scored["score_ratio"]    * 0.15
            + scored["score_huistype"] * 0.25
        ).round(1)

    # Stap 5: Strafpunten
    scored["lead_score"] = _apply_penalty(
        scored["lead_score"], scored["bebouwd_m2"], MIN_BEBOUWD_M2, penalty=25
    )

    # Stap 6: Classificeer
    def _classify(score):
        for threshold, klasse, label in LEAD_CLASSES:
            if score >= threshold:
                return klasse, label
        return "D", LEAD_CLASSES[-1][2]

    classifications = scored["lead_score"].apply(_classify)
    scored["lead_klasse"] = classifications.apply(lambda x: x[0])
    scored["lead_label"]  = classifications.apply(lambda x: x[1])

    scored = scored.sort_values("lead_score", ascending=False).reset_index(drop=True)
    return scored


# ─── SUMMARY ─────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    total = len(df)
    has_income = "mediaan_inkomen" in df.columns and df["mediaan_inkomen"].notna().any()

    print(f"\n{'='*70}")
    print(f"  FACADEPILOT LEAD SCORING — {total} leads geanalyseerd")
    if has_income:
        print(f"  (met Statbel buurtinkomen)")
    print(f"{'='*70}\n")

    print("  Verdeling per klasse:")
    print("  " + "─" * 55)
    for threshold, klasse, label in LEAD_CLASSES:
        count = len(df[df["lead_klasse"] == klasse])
        pct = count / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {klasse:>3}  {count:>4} ({pct:4.1f}%)  {bar}")

    print(f"\n  Top 10 leads:")
    print("  " + "─" * 55)
    top = df.head(10)
    for i, row in top.iterrows():
        score = row["lead_score"]
        klasse = row["lead_klasse"]
        adres = str(row.get("adres", "?"))[:40]
        woning = row["bebouwd_m2"]
        ink = row.get("mediaan_inkomen", 0)
        ink_str = f"€{ink:,.0f}" if pd.notna(ink) and ink > 0 else "n/a"
        print(f"  {klasse:>3} [{score:5.1f}]  {adres:<40}  woning:{woning:,.0f}m²  buurt:{ink_str}")

    print(f"\n{'='*70}\n")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Lead Scoring")
    parser.add_argument("--input", required=True, type=Path, help="Input CSV")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV")
    parser.add_argument("--top", type=int, default=None, help="Top N leads")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"❌ Niet gevonden: {args.input}")

    df = pd.read_csv(args.input, encoding="utf-8-sig")
    print(f"📊 {len(df)} rijen ingelezen")

    scored = score_leads(df)

    if args.top:
        scored = scored.head(args.top)

    print_summary(scored)

    output = args.output or args.input.with_name(args.input.stem + "_scored.csv")
    scored.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"✅ Output: {output.name} ({len(scored)} leads)")

    return scored


if __name__ == "__main__":
    main()
