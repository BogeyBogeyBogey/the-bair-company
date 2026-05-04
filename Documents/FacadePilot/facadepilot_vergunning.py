#!/usr/bin/env python3
"""
FacadePilot Omgevingsvergunning Pre-filter
============================================
Checkt of er recent (laatste N jaar) een omgevingsvergunning is afgeleverd
voor gevelwerken op een adres. Zo ja → die lead skippen, want:
  - Vermoedelijk al gerenoveerd
  - Of de bewoner is al in een proces met een andere aannemer

Status: STUB met duidelijke aanhechtingspunt.

De officiele Vlaamse Omgevingsloket open data zit verspreid over:
  - https://omgevingsloketdocumenten.omgeving.vlaanderen.be/  (publieke documenten)
  - https://www.vlaanderen.be/datavindplaats  (datasets)
  - https://download.vlaanderen.be/Producten/Detail?id=1170  (Omgevingsvergunningen,
    geleverd als kwartaalbestand met geo-coordinaten en CAPAKEY)

Implementatie-strategie (productie):
  1. Download het laatste kwartaalbestand naar `vergunningen_YYYYQX.csv`
  2. Filter op procedure/object-type 'gevelwerken' / 'verbouwen'
  3. Filter op afgegeven datum > today - YEARS_BACK
  4. Bouw een set van CAPAKEYs in de cache
  5. check_vergunning(capakey) doet een set-lookup → instant

Voor nu: stub die altijd False teruggeeft, met een lokale CSV-cache hook
zodat je het manueel kan voeden tijdens testen.

Gebruik:
    from facadepilot_vergunning import VergunningChecker
    checker = VergunningChecker()
    if checker.has_recent_permit(capakey, lat=..., lon=...):
        # skip deze lead
"""

import argparse
import csv
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent.resolve()

# Cache-bestand: een eenvoudige CSV met CAPAKEY,datum,type
# Voor productie: vervang met API-call of download het Vlaamse kwartaalbestand.
CACHE_FILE = HERE / "vergunningen_cache.csv"

# Hoeveel jaar terugkijken
DEFAULT_YEARS_BACK = 5


# ─── DATA ACCESS ───────────────────────────────────────────────────────────

class VergunningChecker:
    """Pre-filter voor recente gevelvergunningen.

    Werkt nu via een lokale CSV-cache. Bij productie:
    vervang `_load_cache()` met een echte API-call naar het Omgevingsloket.
    """

    def __init__(self, cache_file: Path = CACHE_FILE,
                 years_back: int = DEFAULT_YEARS_BACK):
        self.cache_file = Path(cache_file)
        self.years_back = years_back
        self._capakeys = set()  # set van CAPAKEYs met recent permit
        self._loaded = False
        self._load_cache()

    def _load_cache(self):
        """Laad bekende vergunningen uit lokale CSV."""
        self._loaded = True
        if not self.cache_file.exists():
            print(f"   ℹ️  Vergunning-cache niet aanwezig ({self.cache_file.name})")
            print(f"      Pre-filter is no-op. Maak een CSV met kolommen: CAPAKEY,datum,type")
            print(f"      om de filter te activeren, OF schakel productie-API in.")
            return

        try:
            df = pd.read_csv(self.cache_file, encoding="utf-8-sig")
        except Exception as e:
            print(f"   ⚠️  Kon vergunning-cache niet lezen: {e}")
            return

        # Verwacht kolommen: CAPAKEY, datum, type
        if "CAPAKEY" not in df.columns:
            print(f"   ⚠️  Vergunning-cache mist 'CAPAKEY' kolom")
            return

        cutoff = datetime.now() - timedelta(days=self.years_back * 365)
        n_total = len(df)
        n_recent = 0
        for _, row in df.iterrows():
            capakey = str(row.get("CAPAKEY", "")).strip()
            if not capakey:
                continue
            datum_str = str(row.get("datum", "")).strip()
            try:
                d = pd.to_datetime(datum_str, errors="coerce")
                if pd.isna(d) or d.to_pydatetime() < cutoff:
                    continue
            except Exception:
                continue
            self._capakeys.add(capakey)
            n_recent += 1

        print(f"   📋 Vergunning-cache: {n_recent}/{n_total} relevant (laatste {self.years_back}j)")

    def has_recent_permit(self, capakey: str,
                          lat: float = None, lon: float = None) -> bool:
        """Check of dit adres een recente gevelvergunning heeft.

        Voor nu: pure CAPAKEY-lookup. lat/lon zijn parameters voor toekomstige
        uitbreiding (geo-spatial join met vergunningen-shapefile).
        """
        if not capakey:
            return False
        return capakey in self._capakeys

    def filter_dataframe(self, df: pd.DataFrame,
                         capakey_col: str = "CAPAKEY") -> tuple:
        """Filter een DataFrame: verwijder rijen met recent permit.

        Returns: (filtered_df, n_skipped)
        """
        if not self._capakeys or capakey_col not in df.columns:
            return df, 0
        mask = ~df[capakey_col].astype(str).isin(self._capakeys)
        n_skipped = int((~mask).sum())
        return df[mask].copy(), n_skipped


# ─── PRODUCTIE-HOOK (toekomstige uitbreiding) ─────────────────────────────

def fetch_omgevingsloket_recent(niscode: str = None,
                                years_back: int = DEFAULT_YEARS_BACK) -> pd.DataFrame:
    """
    PLACEHOLDER voor de echte API-call.

    De officiële Vlaamse open data voor omgevingsvergunningen zit op:
      https://download.vlaanderen.be/Producten/Detail?id=1170

    Het is een kwartaalbestand (geen real-time API). Implementatie:
      1. Download het laatste shapefile/CSV
      2. Parse, filter op type='gevelwerken' OR object_type bevat 'gevel'
      3. Filter op datum > today - years_back
      4. Return DataFrame met CAPAKEY, datum, type

    Voor nu retourneert deze functie een lege DataFrame; de checker werkt
    via de lokale CSV-cache.
    """
    return pd.DataFrame(columns=["CAPAKEY", "datum", "type"])


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Vergunning Pre-filter")
    sub = parser.add_subparsers(dest="cmd")

    p_check = sub.add_parser("check", help="Check één CAPAKEY")
    p_check.add_argument("--capakey", required=True)

    p_filter = sub.add_parser("filter", help="Filter een CSV")
    p_filter.add_argument("--csv", required=True, type=Path)
    p_filter.add_argument("--out", type=Path, default=None)

    p_seed = sub.add_parser("seed", help="Maak een lege cache-file aan")

    args = parser.parse_args()
    checker = VergunningChecker()

    if args.cmd == "check":
        result = checker.has_recent_permit(args.capakey)
        print(f"{args.capakey}: {'❌ recent permit (skip)' if result else '✅ geen recent permit'}")

    elif args.cmd == "filter":
        if not args.csv.exists():
            raise SystemExit(f"Niet gevonden: {args.csv}")
        df = pd.read_csv(args.csv, encoding="utf-8-sig")
        out, n_skip = checker.filter_dataframe(df)
        out_path = args.out or args.csv.with_name(args.csv.stem + "_no_permits.csv")
        out.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"✅ {len(out)} leads behouden, {n_skip} geskipt → {out_path.name}")

    elif args.cmd == "seed":
        if CACHE_FILE.exists():
            print(f"Bestaat al: {CACHE_FILE}")
            return
        with open(CACHE_FILE, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["CAPAKEY", "datum", "type"])
            w.writerow(["# Vul aan met capakeys uit het Omgevingsloket", "", ""])
            w.writerow(["# Voorbeeld:", "", ""])
            w.writerow(["24107A0123/00B000", "2024-08-15", "gevelwerken"])
        print(f"✅ Lege cache aangemaakt: {CACHE_FILE}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
