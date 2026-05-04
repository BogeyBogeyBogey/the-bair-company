#!/usr/bin/env python3
"""
FacadePilot Facade Selector — auto-kies renovatietype per lead
================================================================
Beslislogica per lead op basis van:
  - huistype (vrijstaand_ruim / halfopen / rijwoning / stadswoning / appartement_dicht)
  - pct_pre_1990 (% buurtwoningen vóór 1990 — bouwjaar-proxy)
  - mediaan_inkomen (Statbel buurtinkomen)
  - bebouwd_m2 (geveloppervlak)
  - lead_klasse (A+/A/B/C/D)

Resultaat per lead: een preset-key uit facadepilot_render.FACADE_PRESETS,
plus een korte reden voor logging.

Gebruik (als integratie):
    from facadepilot_facade_selector import select_preset_for_row
    preset_key, reason = select_preset_for_row(row)

CLI:
    python3 facadepilot_facade_selector.py --csv leads_scored.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent.resolve()


# ─── BESLISLOGICA ──────────────────────────────────────────────────────────

def select_preset_for_row(row: pd.Series) -> tuple:
    """
    Return (preset_key, reason).

    Logica (in volgorde van prioriteit):

    1. Welvarende buurt (>€45K) + vrijstaand ruim + topklasse → totaalrenovatie
       (Investeringscapaciteit hoog, ruimte voor luxe afwerking)

    2. Oude buurt (>60% pre-1990) + bakstenen profiel (rijwoning/stadswoning)
       → baksteen_rejoint
       (Vlaamse stadskernen waar baksteen-restauratie typisch is)

    3. Halfopen of vrijstaand met gemiddeld inkomen → moderne_crepi
       (Standaard upgrade die altijd goed verkoopt)

    4. Halfopen ruim met groot geveloppervlak (>140m²) en hoog inkomen
       → isolatie_gevelbekleding
       (EPC-gedreven renovatie, energie-investering)

    5. Default → moderne_crepi
       (Veiligste, breedst toepasbare optie)
    """
    huistype = str(row.get("huistype", "") or "").strip()
    klasse = str(row.get("lead_klasse", "") or "").strip()
    bebouwd = float(row.get("bebouwd_m2", 0) or 0)
    inkomen = row.get("mediaan_inkomen")
    pct_oud = row.get("pct_pre_1990")

    inkomen_val = 0.0
    if pd.notna(inkomen):
        try:
            inkomen_val = float(inkomen)
        except (TypeError, ValueError):
            pass

    pct_oud_val = 0.0
    if pd.notna(pct_oud):
        try:
            pct_oud_val = float(pct_oud)
        except (TypeError, ValueError):
            pass

    # 1. Welvarend + ruim + top → totaalrenovatie
    if (klasse in ("A+", "A")
            and huistype in ("vrijstaand_ruim", "halfopen_ruim")
            and inkomen_val >= 45000):
        return ("totaalrenovatie",
                f"klasse {klasse} + {huistype} + inkomen €{inkomen_val:,.0f} → premium")

    # 2. Oude buurt + bakstenen profiel → baksteen_rejoint
    if pct_oud_val >= 60 and huistype in ("rijwoning", "stadswoning"):
        return ("baksteen_rejoint",
                f"buurt {pct_oud_val:.0f}% pre-1990 + {huistype} → restauratie")

    # 3. Halfopen ruim + groot oppervlak + hoog inkomen → isolatie + bekleding
    if (huistype in ("halfopen_ruim", "halfopen")
            and bebouwd >= 140
            and inkomen_val >= 38000):
        return ("isolatie_gevelbekleding",
                f"{huistype} + {bebouwd:.0f}m² + €{inkomen_val:,.0f} → energie")

    # 4. Default → moderne crepi (veilig, breed)
    return ("moderne_crepi",
            f"{huistype or 'onbekend'}: standaard upgrade")


def select_preset_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Voeg kolommen 'preset_auto' en 'preset_reden' toe aan DataFrame."""
    if df.empty:
        df["preset_auto"] = ""
        df["preset_reden"] = ""
        return df

    presets = []
    redenen = []
    for _, row in df.iterrows():
        p, r = select_preset_for_row(row)
        presets.append(p)
        redenen.append(r)

    out = df.copy()
    out["preset_auto"] = presets
    out["preset_reden"] = redenen
    return out


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Auto Facade Selector")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"Niet gevonden: {args.csv}")

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    print(f"📊 {len(df)} leads ingelezen")

    df = select_preset_dataframe(df)

    counts = df["preset_auto"].value_counts().to_dict()
    print("\nVerdeling per preset:")
    for p, n in sorted(counts.items(), key=lambda x: -x[1]):
        bar = "█" * int(n / max(counts.values()) * 30)
        print(f"  {p:<28} {n:>4}  {bar}")

    out_path = args.out or args.csv.with_name(args.csv.stem + "_with_presets.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ Output: {out_path.name}")

    print(f"\nVoorbeeld redeneringen (top 5):")
    for _, row in df.head(5).iterrows():
        print(f"  [{row.get('lead_klasse','?')}] {row.get('preset_auto')}: {row.get('preset_reden')}")


if __name__ == "__main__":
    main()
