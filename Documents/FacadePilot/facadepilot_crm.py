#!/usr/bin/env python3
"""
FacadePilot CRM — Supabase-based persistent lead-store
=======================================================
Houdt alle leads bij over runs heen, met status-tracking voor opvolging.

Backend: Supabase project FacadePilot (xndfyjhpmuaqaxndznji.supabase.co)

Tables:
  - leads          : alle gegenereerde leads + status + paden
  - lead_events    : analytics (scans, clicks, form submits, status changes)

Vereist in .env:
  SUPABASE_URL          = https://xndfyjhpmuaqaxndznji.supabase.co
  SUPABASE_SERVICE_KEY  = <service_role key uit Supabase dashboard>
  SUPABASE_ANON_KEY     = <anon/publishable key>     (voor landingpagina)

Gebruik:
    from facadepilot_crm import LeadStore
    store = LeadStore()
    store.upsert_leads(scored_df, niscode="24107", gemeente="Tienen")
    store.update_status("24107A1234/00B000", "geflyerd")
    counts = store.status_counts()
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

# ─── CONFIG ────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xndfyjhpmuaqaxndznji.supabase.co").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

# Status workflow
STATUSES = [
    "gegenereerd",   # Net uit de pipeline
    "geflyerd",      # Flyer is bezorgd / verstuurd
    "gescand",       # QR-code is gescand op landingpagina
    "contact",       # Klant heeft eerste contact opgenomen
    "afspraak",      # Plaatsbezoek/offerte ingepland
    "klant",         # Geconverteerd
    "afgewezen",     # Niet geinteresseerd / niet bereikbaar
]

STATUS_LABELS = {
    "gegenereerd": "Gegenereerd",
    "geflyerd":    "Flyer bezorgd",
    "gescand":     "QR gescand",
    "contact":     "Eerste contact",
    "afspraak":    "Afspraak",
    "klant":       "Klant",
    "afgewezen":   "Afgewezen",
}

# Welke kolommen sturen we naar Supabase (matcht het schema)
LEAD_COLS = [
    "capakey", "niscode", "gemeente", "adres", "lat", "lon",
    "perceel_m2", "bebouwd_m2", "bebouwd_ratio",
    "huistype", "huistype_score", "mediaan_inkomen", "sector_id", "pct_pre_1990",
    "lead_score", "lead_klasse", "facade_preset",
    "render_path", "streetview_path", "flyer_path", "landing_url",
]


# ─── HELPERS ───────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(v):
    """Converteer pandas-NaN/None naar None en numpy types naar Python natives."""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    # numpy types -> python natives
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


# ─── LEAD STORE ────────────────────────────────────────────────────────────

class LeadStore:
    """Supabase PostgREST-gebaseerde lead-store."""

    def __init__(self, url: str = SUPABASE_URL, key: str = SUPABASE_SERVICE_KEY):
        self.url = url.rstrip("/")
        self.key = key
        if not self.key:
            print("⚠️  SUPABASE_SERVICE_KEY ontbreekt in .env — CRM is in dry-run modus")
            print("    Voeg toe: SUPABASE_SERVICE_KEY=eyJ... (uit Supabase dashboard)")

    # ─── HTTP HELPERS ────────────────────────────────────────────────

    def _headers(self, prefer: str = "") -> dict:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def _check_configured(self) -> bool:
        return bool(self.url and self.key)

    def _request(self, method: str, path: str, **kwargs):
        if not self._check_configured():
            return None
        url = f"{self.url}/rest/v1/{path.lstrip('/')}"
        r = requests.request(method, url, headers=self._headers(kwargs.pop("prefer", "")),
                             timeout=30, **kwargs)
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {method} {path}: {r.status_code} — {r.text[:200]}")
        if r.status_code == 204 or not r.text:
            return None
        try:
            return r.json()
        except json.JSONDecodeError:
            return None

    # ─── UPSERT LEADS ────────────────────────────────────────────────

    def upsert_leads(self, df: pd.DataFrame, niscode: str = "",
                     gemeente: str = "", facade_preset: str = "") -> dict:
        """
        Insert of update leads uit een gescoorde DataFrame.

        Bestaande capakey: update score, klasse, render_path, etc. (status NIET overschrijven)
        Nieuwe capakey: insert met status='gegenereerd'

        Returns: {"inserted": N, "updated": N, "skipped_no_key": N}
        """
        if not self._check_configured():
            print("⚠️  Supabase niet geconfigureerd — upsert overgeslagen")
            return {"inserted": 0, "updated": 0, "skipped_no_key": len(df)}

        skipped = 0

        # Welke kolommen matchen tussen DF en schema?
        col_map = {
            "capakey": "CAPAKEY",
            "adres": "adres",
            "lat": "lat",
            "lon": "lon",
            "perceel_m2": "perceel_m2",
            "bebouwd_m2": "bebouwd_m2",
            "bebouwd_ratio": "bebouwd_ratio",
            "huistype": "huistype",
            "huistype_score": "huistype_score",
            "mediaan_inkomen": "mediaan_inkomen",
            "sector_id": "sector_id",
            "pct_pre_1990": "pct_pre_1990",
            "lead_score": "lead_score",
            "lead_klasse": "lead_klasse",
            "render_path": "render_path",
        }

        # Existing capakeys ophalen om insert vs update te kunnen tellen
        capakeys = [_safe(row.get("CAPAKEY")) for _, row in df.iterrows()]
        capakeys = [c for c in capakeys if c]
        existing_keys = set()
        if capakeys:
            # Chunk om URL-lengte te beheren
            for chunk_start in range(0, len(capakeys), 100):
                chunk = capakeys[chunk_start:chunk_start + 100]
                # in.(key1,key2,...) - quote elke key
                quoted = ",".join(f'"{k}"' for k in chunk)
                resp = self._request(
                    "GET",
                    f"leads?select=capakey&capakey=in.({quoted})"
                )
                if resp:
                    existing_keys.update(r["capakey"] for r in resp)

        # Build payload
        payload = []
        for _, row in df.iterrows():
            capakey = _safe(row.get("CAPAKEY"))
            if not capakey:
                skipped += 1
                continue

            record = {db_col: _safe(row.get(src_col))
                      for db_col, src_col in col_map.items()}
            record["niscode"] = niscode or None
            record["gemeente"] = gemeente or None
            record["facade_preset"] = facade_preset or None

            # Voor nieuwe leads: initial status_history
            if capakey not in existing_keys:
                record["status_history"] = [
                    {"ts": _now_iso(), "status": "gegenereerd", "note": "auto-import na scoring"}
                ]
                # status default is al 'gegenereerd' in DB

            payload.append(record)

        if not payload:
            return {"inserted": 0, "updated": 0, "skipped_no_key": skipped}

        # Upsert in batches van 100
        for i in range(0, len(payload), 100):
            batch = payload[i:i + 100]
            self._request(
                "POST", "leads",
                prefer="resolution=merge-duplicates,return=minimal",
                json=batch
            )

        inserted = sum(1 for p in payload if p["capakey"] not in existing_keys)
        updated = len(payload) - inserted

        return {"inserted": inserted, "updated": updated, "skipped_no_key": skipped}

    # ─── UPDATE PATHS ────────────────────────────────────────────────

    def set_render_paths(self, capakey: str, render_path: str = None,
                         streetview_path: str = None):
        if not self._check_configured():
            return
        update = {}
        if render_path is not None:
            update["render_path"] = render_path
        if streetview_path is not None:
            update["streetview_path"] = streetview_path
        if not update:
            return
        self._request("PATCH", f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}",
                      json=update, prefer="return=minimal")

    def set_flyer_path(self, capakey: str, flyer_path: str):
        if not self._check_configured():
            return
        self._request("PATCH", f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}",
                      json={"flyer_path": flyer_path}, prefer="return=minimal")

    def set_landing_url(self, capakey: str, landing_url: str):
        if not self._check_configured():
            return
        self._request("PATCH", f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}",
                      json={"landing_url": landing_url}, prefer="return=minimal")

    # ─── STATUS ──────────────────────────────────────────────────────

    def update_status(self, capakey: str, new_status: str, note: str = "") -> bool:
        if new_status not in STATUSES:
            raise ValueError(f"Onbekende status: {new_status}. Toegestaan: {STATUSES}")
        if not self._check_configured():
            return False

        # Lees huidige status_history
        cur = self._request(
            "GET",
            f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}&select=status_history"
        )
        if not cur:
            return False
        history = cur[0].get("status_history") or []
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except json.JSONDecodeError:
                history = []
        history.append({"ts": _now_iso(), "status": new_status, "note": note})

        self._request(
            "PATCH",
            f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}",
            json={"status": new_status, "status_history": history},
            prefer="return=minimal"
        )

        # Log event
        self.log_event(capakey, "status_change", f"{new_status}: {note}")
        return True

    def add_note(self, capakey: str, note: str) -> bool:
        if not self._check_configured():
            return False
        cur = self._request(
            "GET",
            f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}&select=notes"
        )
        if not cur:
            return False
        existing = cur[0].get("notes") or ""
        new_notes = (existing + f"\n[{_now_iso()}] {note}").strip()
        self._request(
            "PATCH",
            f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}",
            json={"notes": new_notes}, prefer="return=minimal"
        )
        return True

    # ─── EVENTS ──────────────────────────────────────────────────────

    def log_event(self, capakey: str, event: str, detail: str = "",
                  user_agent: str = "", ip_hash: str = ""):
        if not self._check_configured():
            return
        self._request("POST", "lead_events", prefer="return=minimal",
                      json={
                          "capakey": capakey,
                          "event": event,
                          "detail": detail,
                          "user_agent": user_agent or None,
                          "ip_hash": ip_hash or None,
                      })

    # ─── QUERIES ─────────────────────────────────────────────────────

    def get_lead(self, capakey: str) -> dict:
        if not self._check_configured():
            return None
        resp = self._request(
            "GET",
            f"leads?capakey=eq.{requests.utils.quote(capakey, safe='')}"
        )
        return resp[0] if resp else None

    def list_leads(self, niscode: str = None, status: str = None,
                   klasse: str = None, limit: int = 1000) -> list:
        if not self._check_configured():
            return []
        params = []
        if niscode:
            params.append(f"niscode=eq.{niscode}")
        if status:
            params.append(f"status=eq.{status}")
        if klasse:
            # capakey "+" in URL escapen niet nodig voor +; hash is "%23"
            klasse_enc = klasse.replace("+", "%2B")
            params.append(f"lead_klasse=eq.{klasse_enc}")
        params.append(f"order=lead_score.desc")
        params.append(f"limit={limit}")
        q = "&".join(params)
        resp = self._request("GET", f"leads?{q}")
        return resp or []

    def status_counts(self, niscode: str = None) -> dict:
        if not self._check_configured():
            return {s: 0 for s in STATUSES}
        # PostgREST kan groeperen via een view of we doen het client-side
        params = ["select=status"]
        if niscode:
            params.append(f"niscode=eq.{niscode}")
        params.append("limit=10000")
        resp = self._request("GET", f"leads?{'&'.join(params)}") or []
        counts = {s: 0 for s in STATUSES}
        for r in resp:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        return counts

    def klasse_counts(self, niscode: str = None) -> dict:
        if not self._check_configured():
            return {}
        params = ["select=lead_klasse"]
        if niscode:
            params.append(f"niscode=eq.{niscode}")
        params.append("limit=10000")
        resp = self._request("GET", f"leads?{'&'.join(params)}") or []
        counts = {}
        for r in resp:
            k = r.get("lead_klasse") or "?"
            counts[k] = counts.get(k, 0) + 1
        return counts

    def total_leads(self, niscode: str = None) -> int:
        if not self._check_configured():
            return 0
        # HEAD met Prefer count=exact zou efficiënter zijn
        params = ["select=capakey"]
        if niscode:
            params.append(f"niscode=eq.{niscode}")
        params.append("limit=10000")
        resp = self._request("GET", f"leads?{'&'.join(params)}") or []
        return len(resp)

    def conversion_funnel(self, niscode: str = None) -> dict:
        counts = self.status_counts(niscode)
        total = sum(counts.values())
        funnel = {}
        for status in STATUSES:
            n = counts.get(status, 0)
            funnel[status] = {
                "count": n,
                "pct": round(n / total * 100, 1) if total > 0 else 0,
                "label": STATUS_LABELS[status],
            }
        return {"total": total, "funnel": funnel}


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot CRM (Supabase)")
    sub = parser.add_subparsers(dest="cmd")

    p_import = sub.add_parser("import", help="Importeer een gescoorde CSV naar Supabase")
    p_import.add_argument("--csv", required=True, type=Path)
    p_import.add_argument("--niscode", default="")
    p_import.add_argument("--gemeente", default="")
    p_import.add_argument("--preset", default="")

    p_status = sub.add_parser("status", help="Verander status van één lead")
    p_status.add_argument("--capakey", required=True)
    p_status.add_argument("--to", required=True, choices=STATUSES)
    p_status.add_argument("--note", default="")

    p_list = sub.add_parser("list", help="Lijst leads")
    p_list.add_argument("--niscode", default=None)
    p_list.add_argument("--status", default=None, choices=STATUSES)
    p_list.add_argument("--klasse", default=None)
    p_list.add_argument("--limit", type=int, default=20)

    p_funnel = sub.add_parser("funnel", help="Toon conversion funnel")
    p_funnel.add_argument("--niscode", default=None)

    p_check = sub.add_parser("check", help="Test Supabase verbinding")

    args = parser.parse_args()
    store = LeadStore()

    if args.cmd == "check":
        if not store._check_configured():
            print("❌ SUPABASE_URL of SUPABASE_SERVICE_KEY ontbreekt in .env")
            sys.exit(1)
        try:
            n = store.total_leads()
            print(f"✅ Verbonden met {SUPABASE_URL} — {n} leads in database")
        except Exception as e:
            print(f"❌ Verbindingsfout: {e}")
            sys.exit(1)

    elif args.cmd == "import":
        if not args.csv.exists():
            sys.exit(f"Niet gevonden: {args.csv}")
        df = pd.read_csv(args.csv, encoding="utf-8-sig")
        result = store.upsert_leads(df, niscode=args.niscode,
                                    gemeente=args.gemeente,
                                    facade_preset=args.preset)
        print(f"Geimporteerd: {result['inserted']} nieuw, {result['updated']} update, {result['skipped_no_key']} skip")

    elif args.cmd == "status":
        ok = store.update_status(args.capakey, args.to, args.note)
        print(f"{'OK' if ok else 'NIET GEVONDEN'}: {args.capakey} -> {args.to}")

    elif args.cmd == "list":
        leads = store.list_leads(args.niscode, args.status, args.klasse, args.limit)
        print(f"{len(leads)} leads:")
        for l in leads:
            print(f"  {l.get('lead_klasse','?'):>3} [{l.get('lead_score',0):5.1f}] {l.get('status','?'):>12}  {(l.get('adres') or '')[:50]}")

    elif args.cmd == "funnel":
        result = store.conversion_funnel(args.niscode)
        print(f"\n  Conversion funnel ({result['total']} leads totaal):")
        print("  " + "─" * 55)
        for status in STATUSES:
            row = result["funnel"][status]
            bar = "█" * int(row["pct"] / 2)
            print(f"  {row['label']:<18} {row['count']:>4} ({row['pct']:>5.1f}%)  {bar}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
