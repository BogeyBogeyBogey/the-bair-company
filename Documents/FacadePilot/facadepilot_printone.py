#!/usr/bin/env python3
"""
FacadePilot Print.one integratie
==================================
Wrapper rond de Print.one v2 API om PDF-flyers automatisch te laten drukken
en bezorgen op de adressen uit een gescoorde CSV.

Vereist:
    PRINTONE_API_KEY in .env
    Flyers in flyers/ map (output van facadepilot_flyer.py)

Default = DRY RUN — geen echte verzending. Echte verzending vereist:
    - CLI: --live flag
    - Code: PrintOneClient(dry_run=False)

Beschermingen:
    - Idempotency-Key per adres (postcode_huisnummer_fileid) → geen
      dubbele bestellingen bij retry of dubbele runs
    - Retry + exponential backoff bij netwerk/5xx errors
    - printone_jobs.csv met file_id/order_id/status/error per rij
      (onmisbaar voor debugging als deel mislukt)

Gebruik:
    python3 facadepilot_printone.py --csv leads_scored_with_renders.csv
    python3 facadepilot_printone.py --csv ... --live  # ECHT versturen

Disclaimer: Print.one body-velden (format, finish, files[].id) zijn op basis
van publieke conventies — eerste live-test op 1 adres voor je een batch verstuurt.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

PRINTONE_API_BASE = "https://api.print.one/v2"
PRINTONE_API_KEY = os.environ.get("PRINTONE_API_KEY", "")

# Default product-config voor flyer-formaat
DEFAULT_FORMAT = "POSTCARD_A5"   # Print.one product-keys, vul aan op basis van account
DEFAULT_FINISH = "GLOSSY"
DEFAULT_FILE_TYPE = "FRONT_BACK"  # of "FRONT_ONLY"


# ─── ADRES PARSER ──────────────────────────────────────────────────────────

# Patroon: "Straat 12 bus 3, 2840 Rumst" of "Kerkstraat 1A, 3300 Tienen"
# Suffix mag tot 4 letters lang zijn (1A, 12B, 35BIS, 7TER)
_ADRES_RE = re.compile(
    r"^(?P<straat>.+?)\s+(?P<huisnr>\d+\s*[A-Za-z]{0,4})(?:\s+bus\s+(?P<bus>[A-Za-z0-9]+))?\s*,?\s*"
    r"(?P<postcode>\d{4})\s+(?P<gemeente>.+)$",
    re.IGNORECASE,
)


def parse_vlaams_adres(adres: str) -> dict | None:
    """
    Parse Vlaams adres-string naar {straat, huisnummer, bus, postcode, gemeente}.

    Voorbeelden:
      "Sint-Annalaan 12 bus 3, 2840 Rumst"
      "Kerkstraat 1A, 3300 Tienen"
      "Veemarkt 35BIS, 3300 Tienen"
    """
    if not adres:
        return None
    s = adres.strip()
    m = _ADRES_RE.match(s)
    if not m:
        return None
    huisnr_raw = m.group("huisnr").strip().upper().replace(" ", "")
    # Splits "12A" naar nummer + suffix
    nrm = re.match(r"(\d+)([A-Z]+)?", huisnr_raw)
    huisnummer = nrm.group(1) if nrm else huisnr_raw
    suffix = nrm.group(2) if nrm and nrm.group(2) else ""
    return {
        "straat": m.group("straat").strip(),
        "huisnummer": huisnummer,
        "huisnummer_suffix": suffix,
        "bus": (m.group("bus") or "").strip(),
        "postcode": m.group("postcode").strip(),
        "gemeente": m.group("gemeente").strip(),
    }


# ─── PRINT.ONE CLIENT ─────────────────────────────────────────────────────

class PrintOneClient:
    """Wrapper rond Print.one v2 met retry, idempotency en dry-run."""

    def __init__(self, api_key: str = PRINTONE_API_KEY, dry_run: bool = True,
                 max_retries: int = 3, base_url: str = PRINTONE_API_BASE):
        self.api_key = api_key
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.base_url = base_url.rstrip("/")
        if not dry_run and not api_key:
            raise ValueError("PRINTONE_API_KEY ontbreekt in .env (nodig voor live)")

    # ─── HTTP HELPER ─────────────────────────────────────────────

    def _headers(self, idempotency_key: str = "") -> dict:
        h = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h

    def _request(self, method: str, path: str,
                 idempotency_key: str = "",
                 files=None, **kwargs):
        if self.dry_run:
            return {"_dry_run": True, "method": method, "path": path,
                    "idempotency_key": idempotency_key, "kwargs": kwargs}

        url = f"{self.base_url}/{path.lstrip('/')}"
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                # files (multipart) niet via JSON-content-type
                hdrs = self._headers(idempotency_key)
                if files:
                    hdrs.pop("Content-Type", None)
                    r = requests.request(method, url, headers=hdrs,
                                          files=files, timeout=60, **kwargs)
                else:
                    r = requests.request(method, url, headers=hdrs,
                                          timeout=30, **kwargs)
                # 4xx (behalve 429) → geen retry
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    raise RuntimeError(f"Print.one {r.status_code}: {r.text[:200]}")
                # 5xx of 429 → retry
                if r.status_code >= 500 or r.status_code == 429:
                    raise RuntimeError(f"transient {r.status_code}: {r.text[:120]}")
                if r.status_code == 204 or not r.text:
                    return {}
                return r.json()
            except (requests.RequestException, RuntimeError) as e:
                last_exc = e
                if attempt < self.max_retries - 1:
                    backoff = 2 ** (attempt + 1)
                    time.sleep(backoff)
                else:
                    raise
        if last_exc:
            raise last_exc

    # ─── HOGE-NIVEAU ACTIES ──────────────────────────────────────

    def upload_file(self, pdf_path: Path, idempotency_key: str = "") -> dict:
        """
        Upload PDF naar Print.one. Returns {file_id, ...}.

        Print.one verwacht typisch een POST naar /files met multipart.
        (Exacte vorm kan per account verschillen — eerste live-test = klein!)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)

        if self.dry_run:
            return {"_dry_run": True, "file_id": f"DRY-{pdf_path.stem}",
                    "filename": pdf_path.name}

        with open(pdf_path, "rb") as f:
            return self._request(
                "POST", "files",
                idempotency_key=idempotency_key,
                files={"file": (pdf_path.name, f, "application/pdf")}
            )

    def create_order(self, file_id: str, recipient: dict,
                     format_: str = DEFAULT_FORMAT,
                     finish: str = DEFAULT_FINISH,
                     idempotency_key: str = "") -> dict:
        """
        Plaats order voor één geadresseerde.

        recipient = {straat, huisnummer, bus, postcode, gemeente, naam (optioneel)}
        """
        body = {
            "format": format_,
            "finish": finish,
            "files": [{"id": file_id}],
            "recipient": {
                "name": recipient.get("naam", "Bewoner"),
                "street": recipient.get("straat", ""),
                "houseNumber": recipient.get("huisnummer", ""),
                "houseNumberSuffix": recipient.get("huisnummer_suffix", "") or recipient.get("bus", ""),
                "postalCode": recipient.get("postcode", ""),
                "city": recipient.get("gemeente", ""),
                "country": "BE",
            },
        }
        return self._request("POST", "orders",
                             idempotency_key=idempotency_key,
                             json=body)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"orders/{order_id}")


# ─── BATCH FLOW ────────────────────────────────────────────────────────────

def _idempotency_key(adres_parts: dict, file_path: Path) -> str:
    """
    Stabiele key per (adres + bestand). Garandeert dat dezelfde adres-flyer-combo
    niet 2x besteld wordt, ook bij dubbele runs.
    """
    base = (
        f"{adres_parts.get('postcode','')}_"
        f"{adres_parts.get('huisnummer','')}{adres_parts.get('huisnummer_suffix','')}_"
        f"{adres_parts.get('bus','')}_"
        f"{file_path.name}"
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:32]


def build_printone_csv(scored_csv: Path, flyers_dir: Path,
                       flyer_format: str = "A5",
                       output_csv: Path = None) -> Path:
    """
    Combineer een scored CSV + flyers/ map tot een Print.one input-CSV.

    Returns het pad van de output (default: printone_input_<niscode>.csv).
    """
    scored_csv = Path(scored_csv)
    flyers_dir = Path(flyers_dir)
    df = pd.read_csv(scored_csv, encoding="utf-8-sig")

    output = output_csv or scored_csv.with_name(
        scored_csv.stem.replace("_scored", "").replace("_with_renders", "")
        + f"_printone_{flyer_format.lower()}.csv"
    )

    rows = []
    for i, row in df.iterrows():
        adres = str(row.get("adres", "")).strip()
        if not adres:
            continue
        parts = parse_vlaams_adres(adres)
        if not parts:
            continue

        # Vind flyer in flyers_dir (matcht op idx en adres)
        safe_name = f"{i:03d}_{adres[:35].replace(' ', '_').replace(',', '').replace('/', '_')}"
        flyer = flyers_dir / f"{safe_name}_flyer_{flyer_format}.pdf"
        if not flyer.exists():
            # try lowercase format
            flyer = flyers_dir / f"{safe_name}_flyer_{flyer_format.lower()}.pdf"
        if not flyer.exists():
            continue

        rows.append({
            "idx": i,
            "adres": adres,
            "straat": parts["straat"],
            "huisnummer": parts["huisnummer"],
            "huisnummer_suffix": parts["huisnummer_suffix"],
            "bus": parts["bus"],
            "postcode": parts["postcode"],
            "gemeente": parts["gemeente"],
            "flyer_pdf": str(flyer.relative_to(HERE)),
            "lead_klasse": row.get("lead_klasse", ""),
            "CAPAKEY": row.get("CAPAKEY", ""),
        })

    if not rows:
        raise RuntimeError(f"Geen flyers gematcht tussen {scored_csv.name} en {flyers_dir}/")

    with open(output, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    return output


def send_csv_to_printone(input_csv: Path, dry_run: bool = True,
                         format_: str = DEFAULT_FORMAT,
                         finish: str = DEFAULT_FINISH,
                         progress_callback=None) -> Path:
    """
    Verstuur alle rijen uit een Print.one input-CSV.

    Schrijft printone_jobs.csv met file_id, order_id, status en eventuele error
    per rij. ALTIJD geschreven, ook bij partial failure — onmisbaar voor debug.

    Returns het pad van het jobs-bestand.
    """
    input_csv = Path(input_csv)
    df = pd.read_csv(input_csv, encoding="utf-8-sig")

    client = PrintOneClient(dry_run=dry_run)

    jobs_csv = input_csv.with_name(
        input_csv.stem.replace("_printone_", "_printone_jobs_") + ".csv"
    )

    results = []
    total = len(df)
    success = 0
    errors = 0

    print(f"\n📮 Print.one verzending — {total} rijen "
          f"({'DRY RUN' if dry_run else '⚠️  LIVE'})")
    print()

    for i, row in df.iterrows():
        adres = str(row.get("adres", ""))
        flyer_path = HERE / str(row.get("flyer_pdf", ""))
        recipient = {
            "naam": "Bewoner",
            "straat": row.get("straat", ""),
            "huisnummer": str(row.get("huisnummer", "")),
            "huisnummer_suffix": str(row.get("huisnummer_suffix", "") or ""),
            "bus": str(row.get("bus", "") or ""),
            "postcode": str(row.get("postcode", "")),
            "gemeente": row.get("gemeente", ""),
        }

        idem_key = _idempotency_key(recipient, flyer_path)
        result = {
            "idx": row.get("idx", i),
            "adres": adres,
            "flyer_pdf": str(flyer_path.relative_to(HERE)) if flyer_path.exists() else "",
            "idempotency_key": idem_key,
            "file_id": "",
            "order_id": "",
            "status": "",
            "error": "",
        }

        try:
            if not flyer_path.exists():
                raise FileNotFoundError(f"flyer niet gevonden: {flyer_path}")

            # 1. Upload PDF
            print(f"   [{i+1}/{total}] {adres[:50]} — upload...", end="", flush=True)
            up = client.upload_file(flyer_path, idempotency_key=f"file_{idem_key}")
            file_id = up.get("file_id") or up.get("id") or "DRY-FILE"
            result["file_id"] = file_id
            print(f" file={file_id[:18]}", end="")

            # 2. Plaats order
            print(f", order...", end="", flush=True)
            order = client.create_order(
                file_id, recipient,
                format_=format_, finish=finish,
                idempotency_key=f"order_{idem_key}"
            )
            order_id = order.get("order_id") or order.get("id") or "DRY-ORDER"
            result["order_id"] = order_id
            result["status"] = order.get("status", "DRY" if dry_run else "CREATED")
            print(f" ✅ {order_id[:18]} ({result['status']})")
            success += 1

        except Exception as e:
            result["status"] = "ERROR"
            result["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            print(f" ❌ {result['error']}")
            errors += 1

        results.append(result)

        if progress_callback:
            progress_callback(i + 1, total, f"[{i+1}/{total}] {result['status']}")

        # Beleefdheid
        time.sleep(0.3 if not dry_run else 0.05)

    # Schrijf jobs-CSV ALTIJD
    with open(jobs_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print(f"\n{'='*60}")
    print(f"  ✅ {success} succes, ❌ {errors} fouten")
    print(f"  📄 Jobs log: {jobs_csv.name}")
    if dry_run:
        print(f"  ℹ️  DRY RUN — geen echte bestellingen geplaatst.")
        print(f"      Voeg --live toe om echt te versturen.")
    print(f"{'='*60}\n")

    return jobs_csv


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Print.one integratie")
    parser.add_argument("--csv", required=True, type=Path,
                        help="Scored CSV met adressen (output van scoring stap)")
    parser.add_argument("--flyers-dir", type=Path, default=HERE / "flyers")
    parser.add_argument("--format", default="A5", choices=["A5", "A4"],
                        help="Welk flyer-formaat te gebruiken (matched op bestand)")
    parser.add_argument("--printone-format", default=DEFAULT_FORMAT,
                        help="Print.one product-format key")
    parser.add_argument("--printone-finish", default=DEFAULT_FINISH)
    parser.add_argument("--live", action="store_true",
                        help="ECHT versturen (default = dry-run)")
    parser.add_argument("--prepare-only", action="store_true",
                        help="Maak alleen de printone_input CSV aan, niet versturen")
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"Niet gevonden: {args.csv}")
    if not args.flyers_dir.exists():
        sys.exit(f"Flyers map niet gevonden: {args.flyers_dir}")

    # Stap 1: input CSV bouwen
    input_csv = build_printone_csv(args.csv, args.flyers_dir, flyer_format=args.format)
    print(f"📄 Input CSV: {input_csv.name}")

    if args.prepare_only:
        return

    if args.live:
        confirm = input("⚠️  LIVE mode — typ 'JA' om door te gaan: ")
        if confirm.strip() != "JA":
            sys.exit("Geannuleerd.")

    if args.live and not PRINTONE_API_KEY:
        sys.exit("❌ PRINTONE_API_KEY ontbreekt in .env")

    # Stap 2: versturen
    jobs_csv = send_csv_to_printone(
        input_csv,
        dry_run=not args.live,
        format_=args.printone_format,
        finish=args.printone_finish,
    )
    print(f"✅ Klaar. Jobs: {jobs_csv}")


if __name__ == "__main__":
    main()
