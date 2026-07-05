#!/usr/bin/env python3
"""
FacadePilot Pipeline — Gevelrenovatie lead-campagne in één klik
================================================================
Unified dashboard dat alle stappen orkestreert:
  1. Adresselectie (GIS data → lead CSV)
  2. Lead scoring (rangschik op woninggrootte/bouwjaar)
  3. Gevelrenovatie renders (Street View → GPT Image)
  4. Flyer generatie (PDF per lead)

Gebruik:
    python3 facadepilot_pipeline.py
    → opent http://localhost:8769

Geen extra config nodig — detecteert automatisch welke modules beschikbaar zijn.
"""

import argparse
import asyncio
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import pandas as pd

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
SHARED_PY = HERE.parent.parent / "shared" / "python"
if SHARED_PY.exists():
    sys.path.insert(0, str(SHARED_PY))

from homepilot_shared.flyer_editor import (  # noqa: E402
    flyer_editor_payload,
    install_flyer_editor,
    save_flyer_editor_export,
)

DEFAULT_PORT = 8769
DEFAULT_LANDING_BASE_URL = os.environ.get("FACADEPILOT_LANDING_BASE_URL", "https://facadepilot.be")
DEFAULT_PUBLISH_ONLINE = os.environ.get("FACADEPILOT_PUBLISH_ONLINE", "1") != "0"


def find_free_port(start: int = DEFAULT_PORT, end: int = 8900) -> int:
    """Zoek een vrije poort vanaf start tot end."""
    import socket
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Geen vrije poort gevonden tussen {start} en {end}")


def attach_source_registry(df: pd.DataFrame, stage: str = "pipeline") -> pd.DataFrame:
    """Add lightweight provenance columns for new campaign exports.

    Existing columns are preserved. The values are deliberately source-level,
    not homeowner-intent claims: they document where the opportunity signals
    came from and when this local run attached them.
    """
    if df is None or len(df) == 0:
        return df
    result = df.copy()
    retrieved = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    defaults = {
        "source_grb": "Digitaal Vlaanderen GRB/Capakey",
        "source_crab": "Digitaal Vlaanderen adresregister/CRAB",
        "source_statbel": "Statbel sectorstatistiek indien beschikbaar",
        "source_streetview": "Google Street View indien render/review gebruikt",
        "retrieved_at_grb": retrieved,
        "retrieved_at_crab": retrieved,
        "retrieved_at_statbel": retrieved,
        "retrieved_at_streetview": "",
        "provenance_stage": stage,
    }
    for col, value in defaults.items():
        if col not in result.columns:
            result[col] = value
        elif col.startswith("retrieved_at") or col.startswith("source_"):
            result[col] = result[col].fillna(value)
    return result


# ─── MODULE AVAILABILITY CHECK ───────────────────────────────────────────────

def check_modules():
    """Check welke pipeline modules beschikbaar zijn."""
    available = {}
    try:
        import facadepilot_adresselectie as m
        available["adresselectie"] = True
    except ImportError:
        available["adresselectie"] = False
    try:
        from facadepilot_lead_scoring import score_leads
        available["lead_scoring"] = True
    except ImportError:
        available["lead_scoring"] = False
    try:
        import facadepilot_render as m
        available["render"] = bool(os.environ.get("OPENAI_API_KEY"))
    except ImportError:
        available["render"] = False
    try:
        import facadepilot_flyer as m
        available["flyer"] = True
    except ImportError:
        available["flyer"] = False
    try:
        import facadepilot_streetview as m
        available["streetview"] = bool(os.environ.get("GOOGLE_API_KEY"))
    except ImportError:
        available["streetview"] = False
    return available

MODULES = check_modules()

# ─── POSTCODE → NIS-CODE MAPPING (519 Vlaamse postcodes) ────────────────────
# Geladen uit data/postcodes_vlaanderen.json
def _load_postcodes():
    pc_path = HERE / "data" / "postcodes_vlaanderen.json"
    if not pc_path.exists():
        return {}
    with open(pc_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {pc: tuple(v) for pc, v in raw.items()}

POSTCODE_NIS = _load_postcodes()


def resolve_gemeente(code: str) -> tuple:
    """Resolve postcode of NIS-code naar (niscode, gemeente_naam).

    Detecteert automatisch:
    - 4 cijfers -> postcode -> opzoeken in POSTCODE_NIS
    - 5 cijfers -> NIS-code -> rechtstreeks gebruiken

    Returns: (niscode, gemeente_naam) of raises ValueError
    """
    code = code.strip()

    # Probeer als postcode (4 cijfers)
    if len(code) == 4 and code.isdigit():
        if code in POSTCODE_NIS:
            nis, naam = POSTCODE_NIS[code]
            return nis, naam
        else:
            raise ValueError(f"Postcode {code} niet gevonden in Vlaanderen. Probeer een NIS-code (5 cijfers).")

    # Probeer als NIS-code (5 cijfers)
    if len(code) == 5 and code.isdigit():
        # Zoek naam in VOORBEELD_GEMEENTEN of POSTCODE_NIS reverse
        naam = VOORBEELD_GEMEENTEN.get(code, "")
        if not naam:
            # Reverse lookup in postcode dict
            for pc, (nis, gnaam) in POSTCODE_NIS.items():
                if nis == code:
                    naam = gnaam
                    break
        if not naam:
            naam = f"Gemeente {code}"
        return code, naam

    raise ValueError(f"Ongeldige invoer '{code}'. Voer een postcode (4 cijfers, bv. 3300) of NIS-code (5 cijfers, bv. 24107) in.")


# ─── FACADE PRESETS (imported from render module at runtime) ─────────────────

try:
    from facadepilot_render import FACADE_PRESETS, DEFAULT_PRESET as DEFAULT_FACADE_PRESET
except ImportError:
    FACADE_PRESETS = {
        "moderne_crepi": {
            "label": "Moderne crepi-afwerking",
            "prompt": "Renoveer de gevel met strakke witte crepi, moderne aluminium ramen en buitenverlichting.",
            "afmeting": '100<span class="unit">m2</span>',
            "afmeting_label": "Geveloppervlak",
            "prijs": 'vanaf <span class="unit">EUR20K</span>',
            "bouwtijd": '3-6<span class="unit">wk</span>',
        },
        "baksteen_rejoint": {
            "label": "Baksteen gevelreiniging + hervoegen",
            "prompt": "Reinig en hervoeg de bakstenen gevel met nieuwe mortel en moderne ramen.",
            "afmeting": '80<span class="unit">m2</span>',
            "afmeting_label": "Geveloppervlak",
            "prijs": 'vanaf <span class="unit">EUR12K</span>',
            "bouwtijd": '2-4<span class="unit">wk</span>',
        },
        "isolatie_gevelbekleding": {
            "label": "Buitenisolatie + gevelbekleding",
            "prompt": "Renoveer de gevel met buitenisolatie en moderne gevelbekleding.",
            "afmeting": '120<span class="unit">m2</span>',
            "afmeting_label": "Isolatie + bekleding",
            "prijs": 'vanaf <span class="unit">EUR30K</span>',
            "bouwtijd": '4-8<span class="unit">wk</span>',
        },
        "totaalrenovatie": {
            "label": "Totale gevelrenovatie",
            "prompt": "Voer een complete gevelrenovatie uit met luxe materialen.",
            "afmeting": '150<span class="unit">m2</span>',
            "afmeting_label": "Totaalrenovatie",
            "prijs": 'vanaf <span class="unit">EUR45K</span>',
            "bouwtijd": '6-10<span class="unit">wk</span>',
        },
    }
    DEFAULT_FACADE_PRESET = "moderne_crepi"


# ─── GLOBAL STATE ─────────────────────────────────────────────────────────────
state_lock = threading.Lock()
pipeline_state = {
    "running": False,
    "done": False,
    "cancelled": False,
    "error": None,
    "current_step": None,
    "start_time": None,
    "mode": "full",
    "gemeente": "",
    "niscode": "",
    "steps": {
        "adresselectie": {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "scoring":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "render":        {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "flyer":         {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "landing":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "publish":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "email":         {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
    },
    "log": [],
    "summary": {},
    "output_files": [],
    "costs": {
        "streetview_photos": 0,
        "streetview_metadata": 0,
        "streetview_usd": 0.0,
        "quality_checks": 0,
        "quality_failed": 0,
        "quality_usd": 0.0,
        "renders_done": 0,
        "renders_skipped_quality": 0,
        "render_usd": 0.0,
        "total_usd": 0.0,
    },
}
MAX_LOG = 300


def _empty_costs():
    return {
        "streetview_photos": 0,
        "streetview_metadata": 0,
        "streetview_usd": 0.0,
        "quality_checks": 0,
        "quality_failed": 0,
        "quality_usd": 0.0,
        "renders_done": 0,
        "renders_skipped_quality": 0,
        "render_usd": 0.0,
        "total_usd": 0.0,
    }


def refresh_costs():
    """Lees de cost-counters uit de modules en aggregeer in pipeline_state."""
    try:
        from facadepilot_streetview import get_streetview_cost_state
        sv = get_streetview_cost_state()
    except Exception:
        sv = {"metadata_calls": 0, "photo_calls": 0, "estimated_cost_usd": 0.0}

    try:
        from facadepilot_render import get_render_cost_state
        rd = get_render_cost_state()
    except Exception:
        rd = {"renders_done": 0, "renders_skipped_quality": 0, "estimated_cost_usd": 0.0}

    try:
        from facadepilot_quality_check import get_cost_state
        qc = get_cost_state()
    except Exception:
        qc = {"checks_done": 0, "checks_failed": 0, "estimated_cost_usd": 0.0}

    with state_lock:
        pipeline_state["costs"] = {
            "streetview_photos": sv["photo_calls"],
            "streetview_metadata": sv["metadata_calls"],
            "streetview_usd": round(sv["estimated_cost_usd"], 4),
            "quality_checks": qc["checks_done"],
            "quality_failed": qc["checks_failed"],
            "quality_usd": round(qc["estimated_cost_usd"], 4),
            "renders_done": rd["renders_done"],
            "renders_skipped_quality": rd["renders_skipped_quality"],
            "render_usd": round(rd["estimated_cost_usd"], 4),
            "total_usd": round(
                sv["estimated_cost_usd"] + qc["estimated_cost_usd"] + rd["estimated_cost_usd"], 4
            ),
        }


def reset_costs():
    """Reset de cost-counters in alle modules."""
    try:
        from facadepilot_streetview import reset_streetview_cost_state
        reset_streetview_cost_state()
    except Exception:
        pass
    try:
        from facadepilot_render import reset_render_cost_state
        reset_render_cost_state()
    except Exception:
        pass
    try:
        from facadepilot_quality_check import reset_cost_state
        reset_cost_state()
    except Exception:
        pass


def reset_state():
    with state_lock:
        pipeline_state.update({
            "running": False,
            "done": False,
            "cancelled": False,
            "error": None,
            "current_step": None,
            "start_time": None,
            "mode": "full",
            "gemeente": "",
            "niscode": "",
            "steps": {
                "adresselectie": {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "scoring":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "render":        {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "flyer":         {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "landing":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "publish":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "email":         {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
            },
            "log": [],
            "summary": {},
            "output_files": [],
            "costs": _empty_costs(),
        })
    reset_costs()


def log(msg):
    with state_lock:
        pipeline_state["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if len(pipeline_state["log"]) > MAX_LOG:
            pipeline_state["log"] = pipeline_state["log"][-MAX_LOG:]


def update_step(step, **kwargs):
    with state_lock:
        pipeline_state["steps"][step].update(kwargs)


def is_cancelled():
    with state_lock:
        return pipeline_state.get("cancelled", False)


# ─── PIPELINE STEPS ──────────────────────────────────────────────────────────

def step_adresselectie(niscode: str, min_woning: float, max_woning: float,
                       max_bebouwd_ratio: float, min_perceel: float, max_perceel: float,
                       vergunning_filter: bool = True):
    """Stap 1: Adresselectie via GIS data + optionele vergunning-filter."""
    import facadepilot_adresselectie as adres

    gemeente = adres.VOORBEELD_GEMEENTEN.get(niscode, f"Gemeente {niscode}")
    log(f"Adresselectie voor {gemeente} (NIS {niscode})")
    update_step("adresselectie", status="running", message=f"Percelen ophalen voor {gemeente}...")

    # Stap 1a: Percelen ophalen
    log("  -> Kadastrale percelen ophalen via GRB API (dit kan 30-60s duren)...")
    update_step("adresselectie", message=f"API-call: kadastrale percelen ophalen voor {gemeente}... (kan even duren)")
    perceel_features = adres.fetch_features("ADP", niscode=niscode)
    if not perceel_features:
        raise Exception(f"Geen percelen gevonden voor NIS-code {niscode}")

    percelen = adres.features_to_geodataframe(perceel_features)
    log(f"  -> {len(percelen)} percelen geladen")
    update_step("adresselectie", message=f"{len(percelen)} percelen geladen, filteren...")

    if is_cancelled():
        return None

    # Filter op perceelgrootte
    percelen["_area"] = percelen.geometry.area
    percelen = percelen[
        (percelen["_area"] >= min_perceel) &
        (percelen["_area"] <= max_perceel)
    ].copy()
    percelen.drop(columns=["_area"], inplace=True)
    log(f"  -> {len(percelen)} percelen na filter ({min_perceel}-{max_perceel}m2)")

    if percelen.empty:
        raise Exception("Geen percelen over na filtering")

    # Stap 1b: Gebouwen ophalen
    log("  -> Gebouwen ophalen via GRB API...")
    update_step("adresselectie", message=f"API-call: gebouwen ophalen ({len(percelen)} percelen gevonden)...")
    bounds = percelen.total_bounds
    bbox_str = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
    gebouw_features = adres.fetch_features("GBG", bbox=bbox_str)
    gebouwen = adres.features_to_geodataframe(gebouw_features)
    log(f"  -> {len(gebouwen)} gebouwen geladen")

    if is_cancelled():
        return None

    # Stap 1c: Woninggrootte berekenen
    log("  -> Woninggrootte berekenen (percelen x gebouwen)...")
    update_step("adresselectie", message="Woninggrootte berekenen (bebouwd oppervlak)...")
    percelen = adres.bereken_woninggrootte(percelen, gebouwen)
    percelen_met_gebouw = percelen[percelen["bebouwd_m2"] > 0].copy()

    # Bebouwd ratio berekenen (gebouw / perceel)
    percelen_met_gebouw["bebouwd_ratio"] = (
        percelen_met_gebouw["bebouwd_m2"] / percelen_met_gebouw["perceel_m2"]
    ).round(3)
    percelen_met_gebouw["bebouwd_ratio"] = percelen_met_gebouw["bebouwd_ratio"].fillna(0)

    n_voor = len(percelen_met_gebouw)
    leads = percelen_met_gebouw[
        (percelen_met_gebouw["bebouwd_m2"] >= min_woning) &
        (percelen_met_gebouw["bebouwd_m2"] <= max_woning) &
        (percelen_met_gebouw["bebouwd_ratio"] <= max_bebouwd_ratio)
    ].copy()

    n_loods = n_voor - len(percelen_met_gebouw[percelen_met_gebouw["bebouwd_m2"] <= max_woning])
    n_industrie = n_voor - len(percelen_met_gebouw[percelen_met_gebouw["bebouwd_ratio"] <= max_bebouwd_ratio])
    log(f"  -> {len(leads)} woningen na filter ({min_woning}-{max_woning}m2, ratio<={max_bebouwd_ratio})")
    log(f"     Uitgesloten: {n_loods} te groot (loods/magazijn), {n_industrie} te hoge bebouwingsgraad (industrieel)")

    if leads.empty:
        raise Exception(f"Geen woningen gevonden (filter: {min_woning}-{max_woning}m2, ratio<={max_bebouwd_ratio})")

    if is_cancelled():
        return None

    # Stap 1d: Adressen koppelen
    log(f"  -> Adressen koppelen voor {len(leads)} percelen via CRAB API...")
    update_step("adresselectie", message=f"Adressen koppelen voor {len(leads)} percelen (API-call)...")
    leads = adres.koppel_adressen(leads, niscode)

    # Stap 1e: Coordinaten
    import geopandas as gpd
    centroids_lambert = leads.geometry.centroid
    centroids_wgs84 = gpd.GeoSeries(centroids_lambert, crs="EPSG:31370").to_crs("EPSG:4326")
    leads["lat"] = centroids_wgs84.y.round(6)
    leads["lon"] = centroids_wgs84.x.round(6)
    leads["google_maps"] = leads.apply(
        lambda row: adres.genereer_google_maps_link(row["lat"], row["lon"]), axis=1
    )

    # Vergunning pre-filter
    n_skipped_permit = 0
    if vergunning_filter:
        try:
            from facadepilot_vergunning import VergunningChecker
            checker = VergunningChecker()
            leads, n_skipped_permit = checker.filter_dataframe(leads, capakey_col="CAPAKEY")
            if n_skipped_permit > 0:
                log(f"  -> {n_skipped_permit} leads geskipt: recente gevelvergunning")
        except Exception as e:
            log(f"  -> Vergunning-filter fout (skipping): {e}")

    # Export
    leads = attach_source_registry(leads, "adresselectie")
    export_cols = ["adres", "CAPAKEY", "perceel_m2", "bebouwd_m2", "bebouwd_ratio", "tuin_m2", "lat", "lon", "google_maps", "source_grb", "source_crab", "source_statbel", "source_streetview", "retrieved_at_grb", "retrieved_at_crab", "retrieved_at_statbel", "retrieved_at_streetview", "provenance_stage"]
    export_cols = [c for c in export_cols if c in leads.columns]
    leads_export = leads[export_cols].sort_values("bebouwd_m2", ascending=False)

    output_file = f"facadepilot_leads_{niscode}.csv"
    leads_export.to_csv(HERE / output_file, index=False, encoding="utf-8-sig")

    log(f"  -> {len(leads_export)} adressen geexporteerd -> {output_file}")
    update_step("adresselectie", status="done", progress=len(leads_export), total=len(leads_export),
                message=f"{len(leads_export)} adressen", output_file=output_file)

    with state_lock:
        pipeline_state["output_files"].append({"name": output_file, "label": "Lead-adressen CSV", "rows": len(leads_export)})

    return output_file


def step_scoring(input_file: str, niscode: str = "", gemeente: str = "",
                 facade_preset: str = "", crm_sync: bool = True):
    """Stap 2: Lead scoring + (optioneel) Supabase CRM sync."""
    from facadepilot_lead_scoring import score_leads

    input_path = HERE / input_file
    log(f"Lead scoring starten voor {input_file}")
    update_step("scoring", status="running", message="Leads scoren...")

    df = pd.read_csv(input_path, encoding="utf-8-sig")

    if len(df) == 0:
        log("  Geen leads om te scoren")
        update_step("scoring", status="done", message="Geen leads")
        return input_file

    scored_df = score_leads(df)
    scored_df = attach_source_registry(scored_df, "scoring")

    scored_file = input_path.stem + "_scored.csv"
    scored_path = HERE / scored_file
    scored_df.to_csv(scored_path, index=False, encoding="utf-8-sig")

    klassen = scored_df["lead_klasse"].value_counts().to_dict()
    klassen_str = " / ".join(f"{k}={v}" for k, v in sorted(klassen.items()))
    log(f"  -> {len(scored_df)} leads gescoord: {klassen_str}")

    # CRM sync (Supabase)
    crm_msg = ""
    if crm_sync:
        try:
            from facadepilot_crm import LeadStore
            store = LeadStore()
            if store._check_configured():
                log("  -> CRM sync naar Supabase...")
                result = store.upsert_leads(scored_df, niscode=niscode,
                                             gemeente=gemeente, facade_preset=facade_preset)
                log(f"     {result['inserted']} nieuw, {result['updated']} update, {result['skipped_no_key']} skip")
                crm_msg = f" • CRM: +{result['inserted']} nieuw"
            else:
                log("  -> CRM skip: SUPABASE_SERVICE_KEY ontbreekt")
        except Exception as e:
            log(f"  -> CRM sync fout: {e}")

    update_step("scoring", status="done", progress=len(scored_df), total=len(scored_df),
                message=f"{len(scored_df)} leads -- {klassen_str}{crm_msg}", output_file=scored_file)

    with state_lock:
        pipeline_state["output_files"].append({"name": scored_file, "label": "Gescoorde leads", "rows": len(scored_df)})
        pipeline_state["summary"]["scoring"] = {
            "total": len(scored_df),
            "klassen": klassen,
            "avg_score": round(scored_df["lead_score"].mean(), 1) if "lead_score" in scored_df.columns else 0,
        }

    return scored_file


def step_render(input_file: str, top_n: int | None, klassen: list | None,
                facade_preset: str | None = None,
                quality_check: bool = True,
                multi_preset_klassen: list | None = None,
                multi_presets: list | None = None,
                auto_preset: bool = False):
    """Stap 3: Gevelrenovatie renders via GPT Image."""
    import facadepilot_render as renderer

    input_path = HERE / input_file
    log(f"Gevelrenovatie renders starten voor {input_file}")
    update_step("render", status="running", message="Leads laden voor render...")

    df = pd.read_csv(input_path, encoding="utf-8-sig")

    # Filter op klasse als opgegeven
    if klassen and "lead_klasse" in df.columns:
        df = df[df["lead_klasse"].isin(klassen)].copy()
        log(f"  -> Gefilterd op klasse {klassen}: {len(df)} leads")

    try:
        from facadepilot_lead_review import apply_review_filter, review_counts
        before_review = len(df)
        df = apply_review_filter(df)
        if len(df) != before_review:
            counts = review_counts()
            log(
                "  -> Kaartselectie toegepast: "
                f"{len(df)}/{before_review} leads "
                f"(selectie={counts.get('selected', 0)}, reserve={counts.get('reserve', 0)}, verwijderd={counts.get('removed', 0)})"
            )
    except Exception as e:
        log(f"  -> Kaartselectie overgeslagen: {e}")

    if top_n:
        df = df.head(top_n).copy()
        log(f"  -> Top {top_n} geselecteerd")

    total = len(df)
    if total == 0:
        log("  Geen leads om te renderen")
        update_step("render", status="done", message="Geen leads")
        return input_file

    # Facade preset prompt
    render_prompt = renderer.DEFAULT_PROMPT
    if facade_preset and facade_preset in FACADE_PRESETS:
        preset = FACADE_PRESETS[facade_preset]
        render_prompt = preset["prompt"]
        log(f"  -> Renovatie type: {preset['label']}")

    if quality_check:
        log(f"  -> Quality check AAN (gpt-4o-mini pre-filter)")
    if multi_presets:
        doelgroep = (
            f"voor klassen {multi_preset_klassen}"
            if multi_preset_klassen else
            "voor elke woning die gerenderd wordt"
        )
        log(f"  -> Meerdere afwerkingen: {multi_presets} {doelgroep}")

    update_step("render", total=total, message=f"0/{total} renders...")
    output_dir = HERE / "renders"

    def render_progress(done, total_r, msg):
        update_step("render", progress=done, total=total_r, message=msg)
        refresh_costs()  # Live cost update na elke stap
        log(f"  {msg}")

    result_df = renderer.process_renders(
        df, output_dir,
        prompt=render_prompt,
        progress_callback=render_progress,
        quality_check=quality_check,
        multi_preset_for_klassen=multi_preset_klassen,
        multi_presets=multi_presets,
        auto_preset=auto_preset,
        preset_key=facade_preset or "default",
    )

    # Tel successen
    success = sum(1 for p in result_df.get("render_path", []) if p)
    log(f"  -> {success}/{total} renders gegenereerd")

    # CRM: render-paden syncen
    try:
        from facadepilot_crm import LeadStore
        store = LeadStore()
        if store._check_configured():
            n_synced = 0
            for _, row in result_df.iterrows():
                capakey = str(row.get("CAPAKEY", "") or "").strip()
                rp = str(row.get("render_path", "") or "")
                if capakey and rp:
                    # Sla relatieve paden op (vanuit FacadePilot/)
                    rel_render = rp.replace(str(HERE) + "/", "").replace(str(HERE) + "\\", "")
                    store.set_render_paths(capakey, render_path=rel_render)
                    n_synced += 1
            if n_synced:
                log(f"  -> {n_synced} render-paden gesynced naar CRM")
    except Exception as e:
        log(f"  -> CRM render-sync fout: {e}")

    # Sla CSV met render paden op
    render_csv = input_path.stem + "_with_renders.csv"
    result_df.to_csv(HERE / render_csv, index=False, encoding="utf-8-sig")

    update_step("render", status="done", progress=success, total=total,
                message=f"{success}/{total} renders", output_file=render_csv)

    with state_lock:
        pipeline_state["output_files"].append({"name": render_csv, "label": "Leads met render-paden", "rows": len(result_df)})
        pipeline_state["output_files"].append({"name": "renders/", "label": "Gevelrenovatie renders", "rows": success})

    return render_csv


def step_landing(input_file: str, niscode: str, builder_profile: dict,
                 facade_preset: str | None = None,
                 base_url: str = DEFAULT_LANDING_BASE_URL,
                 facade_presets: list | None = None):
    """Stap 5: Landingpagina's per adres genereren + URL terugkoppelen naar CRM."""
    import facadepilot_landing as landing_mod

    input_path = HERE / input_file
    log(f"Landingpagina's genereren voor {input_file}")
    update_step("landing", status="running", message="Voorbereiden...")

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    if len(df) == 0:
        update_step("landing", status="done", message="Geen leads")
        return

    landing_campaign = str(niscode or "").strip() or "manual"
    landing_base = str(base_url or DEFAULT_LANDING_BASE_URL).strip().rstrip("/")
    if not landing_base.startswith(("http://", "https://")):
        landing_base = f"https://{landing_base}"
    df = df.reset_index(drop=True)
    df["_landing_idx"] = range(len(df))
    df["landing_url"] = [
        f"{landing_base}/r/{landing_campaign}-{i:03d}"
        for i in range(len(df))
    ]

    # Filter alleen leads met minstens een succesvolle render, inclusief presetkolommen.
    render_cols = [c for c in df.columns if c == "render_path" or str(c).startswith("render_path_")]
    if render_cols:
        mask = pd.Series(False, index=df.index)
        for col in render_cols:
            mask = mask | df[col].astype(str).str.len().gt(5)
        df = df[mask].copy()
    total = len(df)
    if total == 0:
        log("  Geen renders beschikbaar voor landingpagina's")
        update_step("landing", status="done", message="Geen renders")
        return

    update_step("landing", total=total, message=f"0/{total}...")
    output_dir = HERE / "landing" / landing_campaign
    renders_dir = HERE / "renders"

    preset_dict = FACADE_PRESETS.get(facade_preset or "moderne_crepi", {})
    selected_facade_presets = [
        p for p in (facade_presets or [facade_preset or DEFAULT_FACADE_PRESET])
        if p in FACADE_PRESETS
    ] or [DEFAULT_FACADE_PRESET]

    def landing_progress(done, total_l, msg):
        update_step("landing", progress=done, total=total_l, message=msg)
        log(f"  {msg}")

    results = landing_mod.generate_landing_pages(
        df, niscode, output_dir, renders_dir,
        builder_naam=builder_profile.get("naam", "Uw Gevelrenoveerder"),
        builder_telefoon=builder_profile.get("telefoon", "0800 00 000"),
        builder_email=builder_profile.get("email", ""),
        accent_color=builder_profile.get("accent_color", "#3b5998"),
        base_url=base_url,
        facade_preset=preset_dict,
        facade_presets=selected_facade_presets,
        preset_catalog=FACADE_PRESETS,
        progress_callback=landing_progress,
    )

    log(f"  -> {len(results)} landingpagina's gegenereerd")

    if results:
        pd.DataFrame(results).to_csv(output_dir / "_manifest.csv", index=False, encoding="utf-8-sig")
        log(f"  -> manifest geschreven: landing/{landing_campaign}/_manifest.csv")

    # Sync URL naar CRM
    try:
        from facadepilot_crm import LeadStore
        store = LeadStore()
        if store._check_configured():
            for r in results:
                store.set_landing_url(r["capakey"], r["public_url"])
            log(f"  -> {len(results)} landing-URL's gesynced naar CRM")
    except Exception as e:
        log(f"  -> CRM landing-sync fout: {e}")

    update_step("landing", status="done", progress=len(results), total=total,
                message=f"{len(results)} pagina's", output_file=f"landing/{landing_campaign}/")

    with state_lock:
        pipeline_state["output_files"].append({
            "name": f"landing/{landing_campaign}/",
            "label": "Landingpagina's (HTML)",
            "rows": len(results)
        })

    return {
        "campaign": landing_campaign,
        "dir": f"landing/{landing_campaign}/",
        "output_dir": str(output_dir),
        "results": results,
    }


def step_publish_landing(landing_result: dict | None,
                         base_url: str = DEFAULT_LANDING_BASE_URL,
                         site_dir: str | None = None,
                         deploy_online: bool = True):
    """Publiceer gegenereerde QR-landingspagina's naar de statische site."""
    update_step("publish", status="running", message="Voorbereiden...")

    # Campagne go/no-go-poort (HITL stap 3): publiceren is de verzend/export-
    # stap van de pipeline. Alleen afgedwongen bij FACADEPILOT_REQUIRE_GO=1.
    blocked = _campaign_go_blocked_message()
    if blocked:
        update_step("publish", status="error", message="Campagne niet vrijgegeven")
        raise RuntimeError(blocked)

    results = (landing_result or {}).get("results") or []
    if not results:
        update_step("publish", status="skipped", message="Geen landingpagina's")
        return []

    resolved_site_dir = Path(site_dir or os.environ.get("FACADEPILOT_SITE_DIR") or (HERE / "facedepilotsite")).expanduser()
    if not resolved_site_dir.exists() or not resolved_site_dir.is_dir():
        raise RuntimeError(f"Site-map niet gevonden voor publicatie: {resolved_site_dir}")

    target_root = resolved_site_dir / "r"
    target_root.mkdir(parents=True, exist_ok=True)

    copied = []
    total = len(results)
    for idx, item in enumerate(results, start=1):
        slug = str(item.get("slug") or "").strip()
        src = Path(str(item.get("file_path") or ""))
        if not slug and src.exists():
            slug = src.stem
        if not slug:
            log(f"  -> Publicatie overgeslagen: landing zonder slug ({item})")
            continue
        if not src.exists():
            src = HERE / str(landing_result.get("dir", "")).strip("/") / str(item.get("filename") or f"{slug}.html")
        if not src.exists():
            log(f"  -> Publicatie overgeslagen: bestand ontbreekt voor {slug}")
            continue

        dest_dir = target_root / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "index.html"
        shutil.copy2(src, dest)
        copied.append({
            "slug": slug,
            "path": str(dest),
            "url": f"{str(base_url or DEFAULT_LANDING_BASE_URL).rstrip('/')}/r/{slug}",
        })
        update_step("publish", progress=idx, total=total, message=f"{idx}/{total} gekopieerd")

    if not copied:
        raise RuntimeError("Geen landingpagina's konden worden gekopieerd voor publicatie.")

    log(f"  -> {len(copied)} landingpagina's gekopieerd naar {target_root}")

    if deploy_online:
        update_step("publish", progress=len(copied), total=total, message="Vercel deploy...")
        if not shutil.which("vercel"):
            raise RuntimeError("Vercel CLI niet gevonden. Installeer/verbind Vercel of zet online publiceren uit.")
        deploy = subprocess.run(
            ["vercel", "deploy", "--prod", "--yes"],
            cwd=str(resolved_site_dir),
            text=True,
            capture_output=True,
            timeout=600,
        )
        if deploy.returncode != 0:
            details = (deploy.stderr or deploy.stdout or "").strip()
            raise RuntimeError(f"Vercel deploy mislukt: {details[-800:]}")
        deploy_msg = (deploy.stdout or "").strip().splitlines()
        deploy_url = deploy_msg[-1] if deploy_msg else str(base_url or "").rstrip("/")
        log(f"  -> Online gepubliceerd: {deploy_url}")
        message = f"{len(copied)} pagina's online"
    else:
        deploy_url = ""
        message = f"{len(copied)} pagina's klaar voor deploy"

    update_step("publish", status="done", progress=len(copied), total=total,
                message=message, output_file="online")
    with state_lock:
        pipeline_state["output_files"].append({
            "name": f"online {str(base_url or DEFAULT_LANDING_BASE_URL).rstrip('/')}/r/",
            "label": "QR-landingspagina's gepubliceerd",
            "rows": len(copied),
        })
    return copied


def step_email(input_file: str, niscode: str, builder_profile: dict,
               facade_preset: str | None = None,
               landing_base_url: str = DEFAULT_LANDING_BASE_URL):
    """Stap 6: HTML e-mail-flyers genereren (alternatief voor PDF)."""
    import facadepilot_email as email_mod

    input_path = HERE / input_file
    log(f"E-mail-flyers genereren voor {input_file}")
    update_step("email", status="running", message="Voorbereiden...")

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    if "render_path" in df.columns:
        df = df[df["render_path"].astype(str).str.len() > 5].copy()
    total = len(df)
    if total == 0:
        update_step("email", status="done", message="Geen renders")
        return

    update_step("email", total=total, message=f"0/{total}...")
    output_dir = HERE / "emails" / niscode
    renders_dir = HERE / "renders"
    preset_dict = FACADE_PRESETS.get(facade_preset or "moderne_crepi", {})

    def email_progress(done, total_e, msg):
        update_step("email", progress=done, total=total_e, message=msg)
        log(f"  {msg}")

    results = email_mod.generate_emails(
        df, niscode, output_dir, renders_dir,
        builder_naam=builder_profile.get("naam", "Uw Gevelrenoveerder"),
        builder_telefoon=builder_profile.get("telefoon", "0800 00 000"),
        builder_email=builder_profile.get("email", ""),
        accent_color=builder_profile.get("accent_color", "#3b5998"),
        landing_base_url=landing_base_url,
        facade_preset=preset_dict,
        progress_callback=email_progress,
    )

    log(f"  -> {len(results)} e-mail-flyers gegenereerd")
    update_step("email", status="done", progress=len(results), total=total,
                message=f"{len(results)} mails", output_file=f"emails/{niscode}/")

    with state_lock:
        pipeline_state["output_files"].append({
            "name": f"emails/{niscode}/",
            "label": "E-mail-flyers (HTML + .eml)",
            "rows": len(results)
        })


def step_flyer(input_file: str, flyer_format: str, builder_naam: str,
               builder_telefoon: str, top_n: int | None,
               facade_preset: str | None = None, builder_profile: dict | None = None,
               flyer_style: str = "premium",
               flyer_styles: list | None = None,
               facade_presets: list | None = None,
               niscode: str = "",
               landing_base_url: str = DEFAULT_LANDING_BASE_URL):
    """Stap 4: Flyer generatie."""
    import facadepilot_flyer as flyer_mod

    input_path = HERE / input_file
    log(f"Flyer generatie starten voor {input_file}")
    update_step("flyer", status="running", message="Flyers voorbereiden...")

    df = pd.read_csv(input_path, encoding="utf-8-sig")

    if top_n:
        df = df.head(top_n).copy()

    df = df.reset_index(drop=True)
    landing_campaign = str(niscode or "").strip() or "manual"
    landing_base = str(landing_base_url or DEFAULT_LANDING_BASE_URL).strip().rstrip("/")
    if not landing_base.startswith(("http://", "https://")):
        landing_base = f"https://{landing_base}"
    df["_landing_idx"] = range(len(df))
    df["landing_url"] = [
        f"{landing_base}/r/{landing_campaign}-{i:03d}"
        for i in range(len(df))
    ]

    total = len(df)
    if total == 0:
        log("  Geen leads voor flyers")
        update_step("flyer", status="done", message="Geen leads")
        return

    update_step("flyer", total=total, message=f"0/{total} flyers...")

    formats = ["a4", "a5"] if flyer_format == "both" else [flyer_format]
    output_dir = HERE / "flyers"
    renders_dir = HERE / "renders"

    # Build extra template variables from builder profile + facade preset
    extra_vars = {}
    if builder_profile:
        try:
            from facadepilot_flyer_copy import template_vars
            flyer_copy = builder_profile.get("flyer_copy") or {}
            if builder_profile.get("headline") and not flyer_copy.get("front_headline"):
                flyer_copy["front_headline"] = builder_profile["headline"]
            extra_vars.update(template_vars(flyer_copy))
        except Exception as e:
            log(f"  -> Flyer copy profiel overgeslagen: {e}")
        if builder_profile.get("accent_color"):
            extra_vars["accent_color"] = builder_profile["accent_color"]
        if builder_profile.get("headline"):
            extra_vars["headline"] = builder_profile["headline"]
        if builder_profile.get("subheadline"):
            extra_vars["subheadline"] = builder_profile["subheadline"]
        # Logo as data URI
        logo_path = builder_profile.get("logo_path", "")
        if logo_path and Path(logo_path).exists():
            extra_vars["logo_uri"] = flyer_mod.image_to_data_uri(logo_path)

    selected_facade_presets = [
        p for p in (facade_presets or [facade_preset or DEFAULT_FACADE_PRESET])
        if p in FACADE_PRESETS
    ] or [DEFAULT_FACADE_PRESET]

    preset_template_vars = {}
    for preset_key in selected_facade_presets:
        preset = FACADE_PRESETS[preset_key]
        preset_template_vars[preset_key] = {
            "facade_afmeting": preset["afmeting"],
            "facade_afmeting_label": preset["afmeting_label"],
            "facade_prijs": preset["prijs"],
            "facade_bouwtijd": preset["bouwtijd"],
        }

    if facade_preset and facade_preset in FACADE_PRESETS:
        preset = FACADE_PRESETS[facade_preset]
        extra_vars["facade_afmeting"] = preset["afmeting"]
        extra_vars["facade_afmeting_label"] = preset["afmeting_label"]
        extra_vars["facade_prijs"] = preset["prijs"]
        extra_vars["facade_bouwtijd"] = preset["bouwtijd"]
        log(f"  -> Renovatie type op flyer: {preset['label']}")

    def flyer_progress(done, total_f, msg):
        update_step("flyer", progress=done, total=total_f, message=msg)
        log(f"  {msg}")

    selected_flyer_styles = flyer_styles or [flyer_style or "auto"]
    log(f"  -> Folderstijl: automatisch ({', '.join(selected_flyer_styles)})")
    log(f"  -> Afwerkingen op flyers: {', '.join(selected_facade_presets)}")

    # Run async flyer generation
    asyncio.run(flyer_mod.generate_flyers(
        df, output_dir, formats,
        builder_naam=builder_naam,
        builder_telefoon=builder_telefoon,
        landing_base_url=landing_base,
        renders_dir=renders_dir,
        progress_callback=flyer_progress,
        extra_vars=extra_vars if extra_vars else None,
        flyer_style=flyer_style,
        flyer_styles=selected_flyer_styles,
        facade_presets=selected_facade_presets,
        preset_vars=preset_template_vars,
    ))

    log(f"  -> Flyers gegenereerd voor {total} leads")
    update_step("flyer", status="done", progress=total, total=total,
                message=f"{total} flyers", output_file="flyers/")

    with state_lock:
        pipeline_state["output_files"].append({"name": "flyers/", "label": "PDF Flyers", "rows": total})


# ─── MAIN PIPELINE RUNNER ────────────────────────────────────────────────────

def run_pipeline(config: dict):
    """Run de volledige pipeline in een background thread."""
    try:
        reset_costs()  # Schone teller per run
        with state_lock:
            pipeline_state["running"] = True
            pipeline_state["start_time"] = time.time()
            pipeline_state["mode"] = config.get("mode", "full")
            pipeline_state["costs"] = _empty_costs()

        # ── Resolve postcode/NIS-code ─────────────────────────────
        raw_code = config.get("niscode", "").strip()
        if raw_code:
            niscode, gemeente_naam = resolve_gemeente(raw_code)
            log(f"Gemeente: {gemeente_naam} (NIS {niscode}, invoer: {raw_code})")
            with state_lock:
                pipeline_state["gemeente"] = gemeente_naam
                pipeline_state["niscode"] = niscode
        else:
            niscode = ""
            gemeente_naam = ""

        steps_enabled = config.get("steps", {})
        map_only = config.get("mode") == "map_only"
        current_file = config.get("input_csv", None)  # optioneel: start vanaf bestaand CSV
        profile_bits = []
        if config.get("client_profile"):
            profile_bits.append(f"klantprofiel={Path(config['client_profile']).name}")
        if config.get("client_brand_mode"):
            profile_bits.append(f"merk={config['client_brand_mode']}")
        if config.get("target_regions"):
            profile_bits.append(f"streek={config['target_regions']}")
        if config.get("target_house_types"):
            profile_bits.append("woningtypes=" + ", ".join(config["target_house_types"]))
        if config.get("income_target") and config.get("income_target") != "any":
            profile_bits.append(f"inkomen={config['income_target']}")
        if profile_bits:
            log("Campagneprofiel: " + " | ".join(profile_bits))

        # ── STAP 1: Adresselectie ─────────────────────────────────
        if steps_enabled.get("adresselectie", True) and not current_file:
            with state_lock:
                pipeline_state["current_step"] = "adresselectie"
            current_file = step_adresselectie(
                niscode=niscode,
                min_woning=config.get("min_woning", 60),
                max_woning=config.get("max_woning", 350),
                max_bebouwd_ratio=config.get("max_bebouwd_ratio", 0.75),
                min_perceel=config.get("min_perceel", 100),
                max_perceel=config.get("max_perceel", 5000),
                vergunning_filter=config.get("vergunning_filter", True),
            )
            if is_cancelled() or not current_file:
                raise Exception("Geannuleerd")
        elif current_file:
            log(f"Adresselectie overgeslagen -- start vanaf {current_file}")
            update_step("adresselectie", status="skipped", message=f"Overgeslagen (input: {current_file})")
        else:
            update_step("adresselectie", status="skipped", message="Overgeslagen")

        # ── STAP 2: Lead scoring + CRM sync ──────────────────────
        if steps_enabled.get("scoring", True) and current_file:
            with state_lock:
                pipeline_state["current_step"] = "scoring"
            current_file = step_scoring(
                current_file,
                niscode=niscode,
                gemeente=gemeente_naam,
                facade_preset=config.get("facade_preset", ""),
                crm_sync=config.get("crm_sync", True),
            )
            if is_cancelled():
                raise Exception("Geannuleerd")
        else:
            update_step("scoring", status="skipped", message="Overgeslagen")

        if map_only:
            log("Leads/Map only voltooid: de kaart en selectielijst staan klaar.")
            for step_name in ("render", "flyer", "landing", "publish", "email"):
                update_step(step_name, status="skipped", message="Overgeslagen in Leads/Map only")
            with state_lock:
                pipeline_state["done"] = True
                pipeline_state["current_step"] = None
                pipeline_state["summary"]["map_only"] = {
                    "input_file": current_file or "",
                    "message": "Kaartselectie klaar",
                }
            return

        # ── STAP 3: Gevelrenovatie Renders ────────────────────────
        if steps_enabled.get("render", True) and current_file:
            with state_lock:
                pipeline_state["current_step"] = "render"
            current_file = step_render(
                input_file=current_file,
                top_n=config.get("render_top"),
                klassen=config.get("render_klassen"),
                facade_preset=config.get("facade_preset"),
                quality_check=config.get("quality_check", True),
                multi_preset_klassen=config.get("multi_preset_klassen"),
                multi_presets=config.get("multi_presets"),
                auto_preset=config.get("auto_preset", False),
            )
            refresh_costs()
            if is_cancelled():
                raise Exception("Geannuleerd")
        else:
            update_step("render", status="skipped", message="Overgeslagen")

        # ── STAP 4: Flyers ────────────────────────────────────────
        if steps_enabled.get("flyer", True) and current_file:
            with state_lock:
                pipeline_state["current_step"] = "flyer"
            step_flyer(
                input_file=current_file,
                flyer_format=config.get("flyer_format", "both"),
                builder_naam=config.get("builder_naam", "Uw Gevelrenoveerder"),
                builder_telefoon=config.get("builder_telefoon", "0800 00 000"),
                top_n=config.get("flyer_top"),
                facade_preset=config.get("facade_preset"),
                builder_profile=config.get("builder_profile"),
                flyer_style=config.get("flyer_style", "premium"),
                flyer_styles=config.get("flyer_styles"),
                facade_presets=config.get("facade_presets") or config.get("multi_presets"),
                niscode=niscode,
                landing_base_url=config.get("landing_base_url", DEFAULT_LANDING_BASE_URL),
            )
            if is_cancelled():
                raise Exception("Geannuleerd")
        else:
            update_step("flyer", status="skipped", message="Overgeslagen")

        # ── STAP 5: Landingpagina's ───────────────────────────────
        landing_result = None
        if steps_enabled.get("landing", True) and current_file:
            with state_lock:
                pipeline_state["current_step"] = "landing"
            landing_result = step_landing(
                input_file=current_file,
                niscode=niscode,
                builder_profile=config.get("builder_profile") or {},
                facade_preset=config.get("facade_preset"),
                base_url=config.get("landing_base_url", DEFAULT_LANDING_BASE_URL),
                facade_presets=config.get("facade_presets") or config.get("multi_presets"),
            )
            if is_cancelled():
                raise Exception("Geannuleerd")
        else:
            update_step("landing", status="skipped", message="Overgeslagen")

        # ── STAP 6: Publiceer QR-landingspagina's ────────────────
        if steps_enabled.get("publish", DEFAULT_PUBLISH_ONLINE) and landing_result:
            with state_lock:
                pipeline_state["current_step"] = "publish"
            step_publish_landing(
                landing_result,
                base_url=config.get("landing_base_url", DEFAULT_LANDING_BASE_URL),
                site_dir=config.get("publish_site_dir"),
                deploy_online=config.get("publish_online", DEFAULT_PUBLISH_ONLINE),
            )
            if is_cancelled():
                raise Exception("Geannuleerd")
        else:
            update_step("publish", status="skipped", message="Overgeslagen")

        # ── STAP 7: E-mail-flyers ────────────────────────────────
        if steps_enabled.get("email", False) and current_file:
            with state_lock:
                pipeline_state["current_step"] = "email"
            step_email(
                input_file=current_file,
                niscode=niscode,
                builder_profile=config.get("builder_profile") or {},
                facade_preset=config.get("facade_preset"),
                landing_base_url=config.get("landing_base_url", DEFAULT_LANDING_BASE_URL),
            )
        else:
            update_step("email", status="skipped", message="Overgeslagen")

        log("Pipeline voltooid!")
        with state_lock:
            pipeline_state["done"] = True
            pipeline_state["current_step"] = None

    except Exception as e:
        err_msg = str(e)
        if err_msg != "Geannuleerd":
            log(f"Fout: {err_msg}")
        with state_lock:
            pipeline_state["error"] = err_msg
    finally:
        with state_lock:
            pipeline_state["running"] = False


# ─── LIST EXISTING CSVs ──────────────────────────────────────────────────────

def list_csv_files():
    """Lijst beschikbare CSV bestanden om vanaf te starten."""
    files = []
    for p in sorted(HERE.glob("*.csv")):
        files.append({
            "name": p.name,
            "size_kb": round(p.stat().st_size / 1024),
            "rows": _count_rows(p),
        })
    return files


def _count_rows(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f) - 1
    except Exception:
        return 0


# ─── LIST OUTPUT FILES ────────────────────────────────────────────────────────

def list_output_files():
    """Lijst alle relevante output bestanden."""
    files = []
    for p in sorted(HERE.glob("*.csv")):
        files.append({"name": p.name, "type": "csv", "size_kb": round(p.stat().st_size / 1024)})
    renders_dir = HERE / "renders"
    if renders_dir.exists():
        renders = list(renders_dir.glob("*_render.jpg"))
        if renders:
            files.append({"name": f"renders/ ({len(renders)} afbeeldingen)", "type": "folder",
                          "size_kb": sum(r.stat().st_size for r in renders) // 1024})
    flyers_dir = HERE / "flyers"
    if flyers_dir.exists():
        flyers = list(flyers_dir.glob("*.pdf"))
        if flyers:
            files.append({"name": f"flyers/ ({len(flyers)} PDF's)", "type": "folder",
                          "size_kb": sum(f.stat().st_size for f in flyers) // 1024})
    return files


def list_landing_pages(rel_dir: str = ""):
    """Lijst lokaal gegenereerde QR-landingspagina's voor preview."""
    raw = str(rel_dir or "").strip()
    if raw.startswith("landing/"):
        raw = raw[len("landing/"):]
    raw = raw.strip("/")

    base_dir = HERE / "landing"
    landing_dir = (base_dir / raw).resolve() if raw else base_dir.resolve()
    try:
        landing_dir.relative_to(base_dir.resolve())
    except ValueError:
        return []

    if not landing_dir.exists() or not landing_dir.is_dir():
        return []

    pages = []
    for page in sorted(landing_dir.glob("*.html")):
        rel_path = page.relative_to(base_dir.resolve())
        pages.append({
            "name": page.name,
            "slug": page.stem,
            "dir": str(rel_path.parent) if str(rel_path.parent) != "." else "",
            "size_kb": round(page.stat().st_size / 1024),
            "preview_url": "/landing-preview/" + quote(str(rel_path).replace("\\", "/")),
        })
    return pages


def list_render_details():
    """Lijst renders gegroepeerd per woning, inclusief afwerkingsvarianten."""
    renders_dir = HERE / "renders"
    if not renders_dir.exists():
        return []

    try:
        from facadepilot_render import RENDER_PROMPT_VERSION as render_version
    except Exception:
        render_version = "scope_v2"

    def rel_existing(value):
        if value is None:
            return None
        raw = str(value).strip()
        if not raw or raw.lower() == "nan":
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = HERE / p
        if not p.exists():
            return None
        try:
            return p.relative_to(HERE).as_posix()
        except ValueError:
            return str(p)

    def preset_from_name(filename: str):
        for key in FACADE_PRESETS:
            suffix = f"_{key}_{render_version}_render.jpg"
            if filename.endswith(suffix):
                return key
            legacy = f"_render_{key}_{render_version}.jpg"
            if filename.endswith(legacy):
                return key
        return ""

    def streetview_for_render(render_rel):
        if not render_rel:
            return None
        render_name = Path(render_rel).name
        candidates = [render_name.replace("_render.jpg", "_streetview.jpg")]
        for key in FACADE_PRESETS:
            suffix = f"_{key}_{render_version}_render.jpg"
            if render_name.endswith(suffix):
                candidates.append(render_name[:-len(suffix)] + "_streetview.jpg")
            legacy = f"_render_{key}_{render_version}.jpg"
            if render_name.endswith(legacy):
                candidates.append(render_name[:-len(legacy)] + "_streetview.jpg")
        for name in candidates:
            rel = rel_existing(renders_dir / name)
            if rel:
                return rel
        return None

    def make_variant(path_value, preset_key=""):
        rel = rel_existing(path_value)
        if not rel:
            return None
        key = preset_key or preset_from_name(Path(rel).name)
        label = FACADE_PRESETS.get(key, {}).get("label", key or "Render")
        return {
            "id": Path(rel).name.replace("_render.jpg", ""),
            "preset_key": key,
            "preset_label": label,
            "render": rel,
        }

    items = []

    csv_files = sorted(HERE.glob("*_with_renders.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if csv_files:
        try:
            df = pd.read_csv(csv_files[0], encoding="utf-8-sig")
            for idx, row in df.iterrows():
                variants = []
                seen = set()
                main_variant = make_variant(row.get("render_path"))
                if main_variant:
                    variants.append(main_variant)
                    seen.add(main_variant["render"])
                for key in FACADE_PRESETS:
                    variant = make_variant(row.get(f"render_path_{key}"), key)
                    if variant and variant["render"] not in seen:
                        variants.append(variant)
                        seen.add(variant["render"])
                if not variants:
                    continue
                main = variants[0]
                items.append({
                    "id": main["id"],
                    "lead_id": str(row.get("CAPAKEY", "") or idx),
                    "adres": str(row.get("adres", "") or main["id"]),
                    "render": main["render"],
                    "streetview": streetview_for_render(main["render"]),
                    "has_render": True,
                    "variants": variants,
                    "variant_count": len(variants),
                    "size_kb": sum(round((HERE / v["render"]).stat().st_size / 1024) for v in variants if (HERE / v["render"]).exists()),
                })
            if items:
                return items
        except Exception as e:
            log(f"Rendergalerij CSV-fallback: {e}")

    grouped = {}
    for render_file in sorted(renders_dir.glob("*_render.jpg")):
        preset_key = preset_from_name(render_file.name)
        group_key = render_file.name.replace("_render.jpg", "")
        if preset_key:
            suffix = f"_{preset_key}_{render_version}"
            if group_key.endswith(suffix):
                group_key = group_key[:-len(suffix)]
        rel = f"renders/{render_file.name}"
        grouped.setdefault(group_key, []).append(make_variant(rel, preset_key))

    for group_key, variants in grouped.items():
        variants = [v for v in variants if v]
        if not variants:
            continue
        main = variants[0]
        items.append({
            "id": main["id"],
            "lead_id": group_key,
            "adres": group_key.replace("_", " "),
            "render": main["render"],
            "streetview": streetview_for_render(main["render"]),
            "has_render": True,
            "variants": variants,
            "variant_count": len(variants),
            "size_kb": sum(round((HERE / v["render"]).stat().st_size / 1024) for v in variants if (HERE / v["render"]).exists()),
        })

    # Also list streetview photos without renders (failed renders)
    for sv_file in sorted(renders_dir.glob("*_streetview.jpg")):
        base = sv_file.name.replace("_streetview.jpg", "")
        has_any_render = any((renders_dir / f"{base}_{key}_{render_version}_render.jpg").exists() for key in FACADE_PRESETS)
        if not has_any_render and not (renders_dir / f"{base}_render.jpg").exists():
            items.append({
                "id": base,
                "lead_id": base,
                "adres": base.replace("_", " "),
                "render": None,
                "streetview": f"renders/{sv_file.name}",
                "has_render": False,
                "variants": [],
                "variant_count": 0,
                "size_kb": 0,
            })
    return items


def list_flyer_details():
    """Lijst alle flyer PDFs."""
    flyers_dir = HERE / "flyers"
    if not flyers_dir.exists():
        return []
    items = []
    for f in sorted(flyers_dir.glob("*.pdf")):
        items.append({
            "name": f"flyers/{f.name}",
            "size_kb": round(f.stat().st_size / 1024),
        })
    return items


# ─── BOUWER PROFIEL ──────────────────────────────────────────────────────────

BUILDER_PROFILE_PATH = HERE / "builder_profile.json"

def load_builder_profile() -> dict:
    """Laad het opgeslagen bouwer-profiel (of defaults)."""
    try:
        from facadepilot_flyer_copy import DEFAULT_FLYER_COPY, normalize_copy
        default_flyer_copy = normalize_copy(DEFAULT_FLYER_COPY)
    except Exception:
        default_flyer_copy = {}

    defaults = {
        "naam": "Uw Gevelrenoveerder",
        "telefoon": "0800 00 000",
        "email": "",
        "website": "",
        "accent_color": "#3b5998",
        "headline": "",
        "subheadline": "",
        "facade_preset": DEFAULT_FACADE_PRESET,
        "logo_path": "",
        "flyer_copy": default_flyer_copy,
    }
    if BUILDER_PROFILE_PATH.exists():
        try:
            with open(BUILDER_PROFILE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
            if default_flyer_copy:
                defaults["flyer_copy"] = normalize_copy(defaults.get("flyer_copy"))
        except Exception:
            pass
    return defaults


def save_builder_profile(profile: dict):
    """Sla het bouwer-profiel op."""
    with open(BUILDER_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


# ─── CLIENT CAMPAIGN WORKFLOW ────────────────────────────────────────────────

CLIENT_CAMPAIGN_STATE = {
    "running": False,
    "status": "idle",
    "message": "Nog niet gestart",
    "log": "",
    "output_root": "",
    "public_base_url": "",
    "started_at": None,
    "done_at": None,
    "error": "",
}
client_campaign_lock = threading.Lock()


def _campaign_append_log(line: str):
    with client_campaign_lock:
        current = CLIENT_CAMPAIGN_STATE.get("log", "")
        CLIENT_CAMPAIGN_STATE["log"] = (current + line)[-24000:]


def _resolve_local_path(value: str | Path, default_base: Path = HERE) -> Path:
    path = Path(str(value or "")).expanduser()
    if path.is_absolute():
        return path
    return (default_base / path).resolve()


def _path_for_ui(path: Path) -> str:
    try:
        return path.resolve().relative_to(HERE.resolve()).as_posix()
    except Exception:
        return str(path)


def list_client_campaign_options() -> dict:
    """Lijst klantprofielen en campagne-leadsbestanden voor de moderne flow."""
    profiles = []
    leads = []
    profiles_dir = HERE / "client_profiles"
    if profiles_dir.exists():
        for path in sorted(profiles_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, list):
                leads.append({
                    "path": _path_for_ui(path),
                    "name": path.name,
                    "count": len(data),
                })
                continue
            if not isinstance(data, dict) or not data.get("key"):
                continue
            key = str(data.get("key", path.stem))
            copy = data.get("copy") or {}
            is_facade = "gevel" in str(copy.get("landing_hero_title", "")).lower()
            default_brand = "facadepilot" if is_facade else "windowpilot"
            base_domain = "https://www.facadepilot.be/r" if is_facade else "https://www.windowpilot.be/r"
            suggested_leads = profiles_dir / f"{key}_latest_leads.json"
            colors = data.get("colors") or {}
            profiles.append({
                "key": key,
                "name": data.get("name") or data.get("brand_name") or key,
                "brand_name": data.get("brand_name") or data.get("name") or key,
                "default_brand": default_brand,
                "phone": data.get("phone") or "",
                "email": data.get("email") or "",
                "website_url": data.get("website_url") or "",
                "accent_color": colors.get("primary") or colors.get("accent") or "",
                "path": _path_for_ui(path),
                "suggested_leads": _path_for_ui(suggested_leads) if suggested_leads.exists() else "",
                "suggested_public_base_url": f"{base_domain}/{key}",
                "suggested_output_root": _path_for_ui(HERE / "client_campaigns" / f"{key}_output"),
            })
    return {"profiles": profiles, "leads": leads}


def validate_client_campaign(profile_path: str, leads_path: str, source_dir: str = "",
                             render_source_dir: str = "", strict_assets: bool = False) -> tuple[bool, str]:
    scripts_dir = HERE / "scripts"
    profile = _resolve_local_path(profile_path)
    leads = _resolve_local_path(leads_path)
    source = _resolve_local_path(source_dir, leads.parent) if source_dir else leads.parent

    commands = [
        [sys.executable, str(scripts_dir / "validate_client_profile.py"), str(profile)],
        [sys.executable, str(scripts_dir / "validate_campaign_leads.py"), str(leads), "--source-dir", str(source)],
    ]
    if render_source_dir:
        commands[1].extend(["--render-source-dir", str(_resolve_local_path(render_source_dir, source))])
    if strict_assets:
        commands[1].append("--strict-assets")

    chunks = []
    ok = True
    for cmd in commands:
        proc = subprocess.run(cmd, cwd=str(HERE), text=True, capture_output=True, timeout=120)
        output = (proc.stdout or "") + (proc.stderr or "")
        chunks.append(output.strip())
        if proc.returncode != 0:
            ok = False
    return ok, "\n\n".join(c for c in chunks if c)


def _editable_client_json_path(value: str) -> Path:
    path = _resolve_local_path(value)
    allowed_root = (HERE / "client_profiles").resolve()
    try:
        path.resolve().relative_to(allowed_root)
    except ValueError:
        raise ValueError("Alleen JSON-bestanden in client_profiles kunnen via de app worden bewerkt.")
    if path.suffix.lower() != ".json":
        raise ValueError("Alleen .json-bestanden kunnen via deze editor worden bewerkt.")
    if path.name.startswith("_"):
        raise ValueError("Templates worden niet via deze editor overschreven.")
    return path


def read_editable_client_json(path_value: str) -> tuple[Path, str]:
    path = _editable_client_json_path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Bestand niet gevonden: {path}")
    return path, path.read_text(encoding="utf-8")


def save_editable_client_json(path_value: str, content: str) -> tuple[Path, str]:
    path = _editable_client_json_path(path_value)
    parsed = json.loads(content)
    formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
    path.write_text(formatted + "\n", encoding="utf-8")
    return path, formatted


def open_local_path(path_value: str, create: bool = False) -> Path:
    """Open een projectbestand of map in Finder vanuit de lokale dashboard-app."""
    if not str(path_value or "").strip():
        raise ValueError("Geen pad opgegeven.")
    path = _resolve_local_path(path_value)
    project_root = HERE.resolve()
    try:
        path.resolve().relative_to(project_root)
    except ValueError:
        raise ValueError("Alleen paden binnen de FacadePilot-map kunnen vanuit de app worden geopend.")

    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        raise FileNotFoundError(f"Pad bestaat nog niet: {_path_for_ui(path)}")

    if path.is_file():
        subprocess.run(["open", "-R", str(path)], check=False)
    else:
        subprocess.run(["open", str(path)], check=False)
    return path


def run_client_campaign(config: dict):
    scripts_dir = HERE / "scripts"
    args = [
        sys.executable,
        str(scripts_dir / "generate_client_campaign.py"),
        "--client-profile", str(_resolve_local_path(config["profile"])),
        "--leads-json", str(_resolve_local_path(config["leads"])),
        "--output-root", str(_resolve_local_path(config["output_root"])),
        "--public-base-url", str(config["public_base_url"]).rstrip("/"),
    ]
    brand_mode = str(config.get("brand_mode") or "auto").lower()
    if brand_mode in {"facadepilot", "windowpilot"}:
        args.extend(["--product-brand", brand_mode])
    if config.get("source_dir"):
        args.extend(["--source-dir", str(_resolve_local_path(config["source_dir"]))])
    if config.get("render_source_dir"):
        args.extend(["--render-source-dir", str(_resolve_local_path(config["render_source_dir"]))])
    if config.get("source_env"):
        args.extend(["--source-env", str(_resolve_local_path(config["source_env"]))])
    if config.get("skip_renders", True):
        args.append("--skip-renders")
    if config.get("force", False):
        args.append("--force")

    with client_campaign_lock:
        CLIENT_CAMPAIGN_STATE.update({
            "running": True,
            "status": "running",
            "message": "Clientcampagne wordt gegenereerd...",
            "log": "",
            "output_root": str(_resolve_local_path(config["output_root"])),
            "public_base_url": str(config["public_base_url"]).rstrip("/"),
            "started_at": time.time(),
            "done_at": None,
            "error": "",
        })

    _campaign_append_log("$ " + " ".join(args) + "\n\n")
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(HERE),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            _campaign_append_log(line)
        return_code = proc.wait()
        with client_campaign_lock:
            CLIENT_CAMPAIGN_STATE["running"] = False
            CLIENT_CAMPAIGN_STATE["done_at"] = time.time()
            if return_code == 0:
                CLIENT_CAMPAIGN_STATE["status"] = "done"
                CLIENT_CAMPAIGN_STATE["message"] = "Clientcampagne klaar"
            else:
                CLIENT_CAMPAIGN_STATE["status"] = "error"
                CLIENT_CAMPAIGN_STATE["message"] = "Clientcampagne mislukt"
                CLIENT_CAMPAIGN_STATE["error"] = f"Exit code {return_code}"
    except Exception as e:
        _campaign_append_log(f"\nFOUT: {e}\n")
        with client_campaign_lock:
            CLIENT_CAMPAIGN_STATE["running"] = False
            CLIENT_CAMPAIGN_STATE["status"] = "error"
            CLIENT_CAMPAIGN_STATE["message"] = "Clientcampagne mislukt"
            CLIENT_CAMPAIGN_STATE["error"] = str(e)
            CLIENT_CAMPAIGN_STATE["done_at"] = time.time()


# ─── GEMEENTEN LIJST (voor autocomplete) ─────────────────────────────────────

# Import from adresselectie if available
try:
    from facadepilot_adresselectie import VOORBEELD_GEMEENTEN
except ImportError:
    VOORBEELD_GEMEENTEN = {}


# ─── CRM HELPERS (Supabase) ──────────────────────────────────────────────────

def _try_load_crm():
    """Probeer LeadStore te laden. Returns (store, error)."""
    try:
        from facadepilot_crm import LeadStore
        store = LeadStore()
        if not store._check_configured():
            return None, "SUPABASE_SERVICE_KEY ontbreekt in .env"
        return store, None
    except Exception as e:
        return None, f"CRM module fout: {e}"


def get_manual_geojson() -> dict:
    """Geef handmatig toegevoegde adressen als GeoJSON."""
    try:
        from facadepilot_manueel import list_manual_addresses
        rows = list_manual_addresses()
    except Exception as e:
        return {"type": "FeatureCollection", "features": [], "source": "manual:error", "error": str(e)}

    features = []
    for row in rows:
        lat = _safe_float(row.get("lat"))
        lon = _safe_float(row.get("lon"))
        if lat is None or lon is None:
            continue
        capakey = str(row.get("CAPAKEY", ""))
        props = _attach_review({
            "capakey": capakey,
            "adres": str(row.get("adres", "")),
            "klasse": "MAN",
            "score": 0,
            "huistype": "handmatig",
            "bebouwd_m2": _safe_float(row.get("bebouwd_m2"), 0) or 0,
            "status": "handmatig",
            "render_path": "",
            "streetview_path": "",
        }, capakey)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features, "source": "manual:manual_leads.csv"}


def get_leads_geojson(niscode: str | None = None, manual: bool = False) -> dict:
    """Geef alle leads als GeoJSON FeatureCollection.

    Probeert eerst Supabase. Valt terug op de meest recente lokale CSV
    als CRM niet geconfigureerd is.
    """
    if manual:
        return get_manual_geojson()

    features = []
    resolved_niscode = None
    if niscode:
        try:
            resolved_niscode, _ = resolve_gemeente(niscode)
        except ValueError:
            resolved_niscode = niscode

    # 1) Probeer Supabase
    store, err = _try_load_crm()
    if store:
        try:
            leads = store.list_leads(niscode=resolved_niscode, limit=5000)
            for l in leads:
                lat, lon = l.get("lat"), l.get("lon")
                if lat is None or lon is None:
                    continue
                capakey = l.get("capakey")
                props = _attach_review({
                    "capakey": capakey,
                    "adres": l.get("adres", ""),
                    "klasse": l.get("lead_klasse", ""),
                    "score": l.get("lead_score", 0),
                    "huistype": l.get("huistype", ""),
                    "bebouwd_m2": l.get("bebouwd_m2", 0),
                    "status": l.get("status", "gegenereerd"),
                    "render_path": l.get("render_path") or "",
                    "streetview_path": l.get("streetview_path") or "",
                }, capakey)
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": props
                })
            return {"type": "FeatureCollection", "features": features, "source": "supabase"}
        except Exception as e:
            log(f"GeoJSON Supabase fout, fallback naar CSV: {e}")

    # 2) Fallback: meest recente _scored.csv lezen; als die er nog niet is,
    # toon dan de ruwe leadlijst zodat Leads/Map only ook zonder scoring bruikbaar blijft.
    if resolved_niscode:
        scored_files = sorted(HERE.glob(f"facadepilot_leads_{resolved_niscode}_scored*.csv"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        raw_files = sorted(HERE.glob(f"facadepilot_leads_{resolved_niscode}.csv"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        scored_files = sorted(HERE.glob("facadepilot_leads_*_scored*.csv"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        raw_files = sorted(
            [p for p in HERE.glob("facadepilot_leads_*.csv") if "_scored" not in p.stem and "_with_renders" not in p.stem],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    csv_files = scored_files or raw_files
    if not csv_files:
        return {"type": "FeatureCollection", "features": [], "source": "none",
                "error": err or "Geen leads gevonden"}

    try:
        df = pd.read_csv(csv_files[0], encoding="utf-8-sig")
        has_score = "lead_score" in df.columns
        has_klasse = "lead_klasse" in df.columns
        for _, row in df.iterrows():
            lat = row.get("lat")
            lon = row.get("lon")
            if pd.isna(lat) or pd.isna(lon):
                continue
            capakey = str(row.get("CAPAKEY", ""))
            score_value = row.get("lead_score", 0)
            score = 0 if pd.isna(score_value) else (_safe_float(score_value, 0) or 0)
            bebouwd_value = row.get("bebouwd_m2", 0)
            bebouwd_m2 = 0 if pd.isna(bebouwd_value) else (_safe_float(bebouwd_value, 0) or 0)
            props = _attach_review({
                "capakey": capakey,
                "adres": str(row.get("adres", "")),
                "klasse": str(row.get("lead_klasse", "LEAD" if not has_klasse else "")),
                "score": score if has_score else 0,
                "huistype": str(row.get("huistype", "")),
                "bebouwd_m2": bebouwd_m2,
                "status": "gegenereerd",
                "render_path": str(row.get("render_path", "") or ""),
                "streetview_path": "",
            }, capakey)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": props
            })
        return {"type": "FeatureCollection", "features": features,
                "source": f"csv:{csv_files[0].name}"}
    except Exception as e:
        return {"type": "FeatureCollection", "features": [], "source": "error",
                "error": str(e)}


def get_crm_funnel(niscode: str | None = None) -> dict:
    """Geef conversion funnel terug uit Supabase."""
    store, err = _try_load_crm()
    if not store:
        return {"configured": False, "error": err, "total": 0, "funnel": {}}
    try:
        result = store.conversion_funnel(niscode)
        result["configured"] = True
        return result
    except Exception as e:
        return {"configured": False, "error": str(e), "total": 0, "funnel": {}}


def get_crm_leads(niscode=None, status=None, klasse=None, limit=100) -> list:
    """Lijst leads uit Supabase voor het CRM-tabblad."""
    store, err = _try_load_crm()
    if not store:
        return []
    try:
        return store.list_leads(niscode=niscode, status=status, klasse=klasse, limit=limit)
    except Exception:
        return []



# ─── DATABASE / INTELLIGENCE DASHBOARD V2 ────────────────────────────────────

INTELLIGENCE_PARTNERS = [
    "DAW / Kwadro Gent", "Aluvera", "Raamprof", "C-Systems", "BZpunt",
    "Isolblow", "Iso-Kurk", "Moeys", "Asset Avenue", "Renowall Construct",
]
INTELLIGENCE_STATUSES = ["wachtrij", "verstuurd", "gescand", "reactie", "afspraak", "no-response"]
INTELLIGENCE_CLASS_ORDER = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4, "LEAD": 5, "MAN": 6, "": 7}
_INTELLIGENCE_CACHE = {}


def _is_blank(value) -> bool:
    try:
        return value is None or value == "" or pd.isna(value)
    except Exception:
        return value is None or value == ""


def _clean_str(value, default: str = "") -> str:
    if _is_blank(value):
        return default
    text = str(value).strip()
    if text.lower() in ("nan", "none", "null"):
        return default
    return text


def _hash_bucket(value: str, modulo: int) -> int:
    raw = str(value or "")
    total = 0
    for ch in raw:
        total = (total * 131 + ord(ch)) % 1000003
    return total % max(1, modulo)


def _json_ready(value):
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    if isinstance(value, tuple):
        return [_json_ready(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _source_is_demo(path: Path | None, qs=None) -> bool:
    raw = " ".join([
        str(path or ""),
        (qs or {}).get("demo", [""])[0] if qs else "",
        (qs or {}).get("synthetic", [""])[0] if qs else "",
    ])
    return any(token in raw.lower() for token in ("demo", "synthetic", "synthet", "sample", "mock", "placeholder", "testdata"))


def _resolve_intelligence_source(qs) -> tuple[Path | None, str]:
    raw = (
        (qs.get("campaign", [""])[0] or "").strip()
        or (qs.get("leads", [""])[0] or "").strip()
        or (qs.get("csv", [""])[0] or "").strip()
    )
    if raw:
        path = _resolve_local_path(raw)
        try:
            path.resolve().relative_to(HERE.resolve())
        except Exception:
            raise ValueError("Alleen campagnebestanden binnen de FacadePilot-map kunnen in het dashboard geladen worden.")
        if not path.exists():
            raise FileNotFoundError(f"Campagnebestand niet gevonden: {raw}")
        return path, _path_for_ui(path)

    with state_lock:
        active = pipeline_state.get("active_csv") or ""
    if active:
        path = (HERE / active).resolve()
        if path.exists():
            return path, _path_for_ui(path)

    candidates = sorted(
        list(HERE.glob("facadepilot_leads_*_scored_with_renders.csv"))
        + list(HERE.glob("facadepilot_leads_*_scored*.csv"))
        + list(HERE.glob("manual_leads_with_renders.csv"))
        + list(HERE.glob("manual_leads.csv")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return (candidates[0], candidates[0].name) if candidates else (None, "none")


def _load_intelligence_raw(path: Path | None) -> tuple[list[dict], dict]:
    if not path or not path.exists():
        return [], {"source": "none", "source_path": "", "source_type": "none"}
    mtime = path.stat().st_mtime
    cache_key = (str(path.resolve()), mtime)
    if cache_key in _INTELLIGENCE_CACHE:
        return _INTELLIGENCE_CACHE[cache_key]

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            rows = data.get("leads") or data.get("rows") or data.get("items") or []
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        rows = [r for r in rows if isinstance(r, dict)]
        meta = {"source": f"json:{path.name}", "source_path": _path_for_ui(path), "source_type": "json"}
    else:
        df = pd.read_csv(path, encoding="utf-8-sig")
        rows = df.to_dict("records")
        meta = {"source": f"csv:{path.name}", "source_path": _path_for_ui(path), "source_type": "csv"}

    value = (rows, meta)
    _INTELLIGENCE_CACHE.clear()
    _INTELLIGENCE_CACHE[cache_key] = value
    return value


def _class_from_score(score: float) -> str:
    if score >= 80:
        return "A+"
    if score >= 60:
        return "A"
    if score >= 40:
        return "B"
    if score >= 20:
        return "C"
    return "D"


def _partner_for_row(row: dict, idx: int) -> str:
    raw = _clean_str(row.get("partner") or row.get("renovator") or row.get("aannemer"))
    if raw:
        return raw
    key = _clean_str(row.get("sector_naam") or row.get("CAPAKEY") or row.get("capakey") or row.get("adres") or idx)
    return INTELLIGENCE_PARTNERS[_hash_bucket(key, len(INTELLIGENCE_PARTNERS))]


def _status_for_row(row: dict, idx: int, score: float) -> tuple[str, bool]:
    raw = _clean_str(row.get("status") or row.get("crm_status") or row.get("campaign_status"))
    if raw:
        return raw, False
    key = _clean_str(row.get("CAPAKEY") or row.get("capakey") or row.get("adres") or idx)
    bucket = _hash_bucket(key, 100)
    if score < 28:
        return "wachtrij", True
    if bucket < 12:
        return "afspraak", True
    if bucket < 28:
        return "reactie", True
    if bucket < 44:
        return "gescand", True
    if bucket < 76:
        return "verstuurd", True
    return "no-response", True


def _value_for_row(row: dict, m2: float, score: float) -> int:
    raw = _safe_float(row.get("waarde") or row.get("estimated_value") or row.get("pipeline_value"))
    if raw is not None:
        return int(raw)
    return int(max(0, m2) * 420 + max(0, score) * 340)


def _source_registry_for_row(row: dict) -> list[dict]:
    today = time.strftime("%Y-%m-%d", time.gmtime())
    def item(field, source, date_key):
        retrieved = _clean_str(row.get(date_key), today)
        return {"field": field, "source": _clean_str(row.get(source), ""), "retrieved_at": retrieved}
    defaults = [
        {"field": "Adres en perceel", "source": "Digitaal Vlaanderen GRB/Capakey + adresregister", "retrieved_at": _clean_str(row.get("retrieved_at_grb"), today)},
        {"field": "Geometrie en bebouwde oppervlakte", "source": "GRB gebouwen/percelen", "retrieved_at": _clean_str(row.get("retrieved_at_grb"), today)},
        {"field": "Buurt- en inkomenssignaal", "source": "Statbel sectorstatistiek indien beschikbaar", "retrieved_at": _clean_str(row.get("retrieved_at_statbel"), today)},
        {"field": "Street View/render", "source": "Google Street View alleen wanneer render/review is gebruikt", "retrieved_at": _clean_str(row.get("retrieved_at_streetview"), "")},
    ]
    explicit = []
    for col in ("source_grb", "source_crab", "source_statbel", "source_streetview"):
        if _clean_str(row.get(col)):
            explicit.append(item(col.replace("source_", ""), col, "retrieved_at_" + col.replace("source_", "")))
    return explicit or defaults


def _normalise_intelligence_row(row: dict, idx: int, source_path: Path | None) -> dict:
    score = _safe_float(row.get("lead_score") or row.get("score") or row.get("opportunity_score"), 0) or 0
    klasse = _clean_str(row.get("lead_klasse") or row.get("klasse"), _class_from_score(score))
    capakey = _clean_str(row.get("CAPAKEY") or row.get("capakey") or row.get("lead_id") or row.get("id"), f"row-{idx}")
    adres = _clean_str(row.get("adres") or row.get("address"), f"Adres {idx + 1}")
    lat = _safe_float(row.get("lat") or row.get("latitude"))
    lon = _safe_float(row.get("lon") or row.get("lng") or row.get("longitude"))
    m2 = _safe_float(row.get("bebouwd_m2") or row.get("gevel_m2") or row.get("m2") or row.get("building_m2"), 0) or 0
    perceel = _safe_float(row.get("perceel_m2") or row.get("parcel_m2"), 0) or 0
    ratio = _safe_float(row.get("bebouwd_ratio") or row.get("building_ratio"), 0) or 0
    inkomen = _safe_float(row.get("mediaan_inkomen") or row.get("income") or row.get("sector_income"))
    status, simulated_status = _status_for_row(row, idx, score)
    partner = _partner_for_row(row, idx)
    waarde = _value_for_row(row, m2, score)
    metrics = {
        "Woning": _safe_float(row.get("score_woning"), min(100, max(0, m2 / 3))) or 0,
        "Perceel": _safe_float(row.get("score_perceel"), min(100, max(0, perceel / 14))) or 0,
        "Ratio": _safe_float(row.get("score_ratio"), max(0, min(100, (1 - min(ratio, 1)) * 100))) or 0,
        "Type": _safe_float(row.get("score_huistype") or row.get("huistype_score"), 50) or 0,
        "Inkomen": _safe_float(row.get("score_inkomen"), 50 if inkomen is None else min(100, max(0, inkomen / 700))) or 0,
    }
    render = _clean_str(row.get("render_path") or row.get("after_file") or row.get("render_path_window_antraciet"))
    if render and Path(render).is_absolute():
        try:
            render = Path(render).resolve().relative_to(HERE.resolve()).as_posix()
        except Exception:
            render = ""
    return {
        "id": capakey,
        "index": idx,
        "capakey": capakey,
        "adres": adres,
        "lat": lat,
        "lon": lon,
        "score": round(float(score), 1),
        "klasse": klasse,
        "m2": round(float(m2), 1),
        "perceel_m2": round(float(perceel), 1),
        "bebouwd_ratio": round(float(ratio), 3),
        "waarde": waarde,
        "partner": partner,
        "status": status,
        "status_source": "gesimuleerd voor demo/CSV" if simulated_status else "campagne/CRM",
        "simulated_status": simulated_status,
        "huistype": _clean_str(row.get("huistype") or row.get("house_type"), "onbekend"),
        "sector": _clean_str(row.get("sector_naam") or row.get("wijk") or row.get("cluster"), "onbekende sector"),
        "inkomen": inkomen,
        "bouwperiode": "pre-1990" if (_safe_float(row.get("pct_pre_1990"), 0) or 0) >= 40 else "gemengd/onbekend",
        "label": _clean_str(row.get("lead_label") or row.get("label"), "Opportunity-signaal op gebouwniveau"),
        "render_path": render,
        "metrics": {k: round(float(v), 1) for k, v in metrics.items()},
        "sources": _source_registry_for_row(row),
        "source_path": _path_for_ui(source_path) if source_path else "",
    }


def _campaign_rows(qs) -> tuple[list[dict], dict]:
    source_path, source_label = _resolve_intelligence_source(qs)
    raw_rows, meta = _load_intelligence_raw(source_path)
    rows = [_normalise_intelligence_row(row, idx, source_path) for idx, row in enumerate(raw_rows)]
    synthetic = _source_is_demo(source_path, qs) or any(r.get("simulated_status") for r in rows)
    meta.update({
        "source_label": source_label,
        "total_rows": len(rows),
        "synthetic": synthetic,
        "simulated_outcomes": any(r.get("simulated_status") for r in rows),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    return rows, meta


def _filter_rows(rows: list[dict], qs) -> list[dict]:
    q = (qs.get("q", [""])[0] or "").strip().lower()
    status = (qs.get("status", [""])[0] or "").strip()
    klassen = [k for k in (qs.get("klasse", [""])[0] or "").split(",") if k]
    bbox = (qs.get("bbox", [""])[0] or "").strip()
    out = rows
    if q:
        out = [r for r in out if q in (r["adres"] + " " + r["capakey"] + " " + r["sector"] + " " + r["partner"]).lower()]
    if status:
        out = [r for r in out if r.get("status") == status]
    if klassen:
        out = [r for r in out if r.get("klasse") in klassen]
    if bbox:
        try:
            south, west, north, east = [float(x) for x in bbox.split(",")]
            out = [r for r in out if r.get("lat") is not None and r.get("lon") is not None and south <= r["lat"] <= north and west <= r["lon"] <= east]
        except Exception:
            pass
    return out


def _sort_rows(rows: list[dict], qs) -> list[dict]:
    key = (qs.get("sort", ["score"])[0] or "score").strip()
    reverse = (qs.get("dir", ["desc"])[0] or "desc").lower() != "asc"
    allowed = {"adres", "score", "klasse", "m2", "waarde", "partner", "status", "sector"}
    if key not in allowed:
        key = "score"
    def sort_key(row):
        if key == "klasse":
            return INTELLIGENCE_CLASS_ORDER.get(row.get("klasse", ""), 99)
        return row.get(key) if row.get(key) is not None else ""
    return sorted(rows, key=sort_key, reverse=reverse)


def _status_timeline(row: dict) -> list[dict]:
    base = int(time.time()) - 86400 * (10 + row.get("index", 0) % 18)
    steps = [("gegenereerd", "Lead opgenomen in campagne", 0)]
    status = row.get("status", "wachtrij")
    if status in ("verstuurd", "gescand", "reactie", "afspraak", "no-response"):
        steps.append(("verstuurd", "Flyer/outreach gemarkeerd als verzonden", 2))
    if status in ("gescand", "reactie", "afspraak"):
        steps.append(("gescand", "QR- of pagina-interactie geregistreerd", 5))
    if status in ("reactie", "afspraak"):
        steps.append(("reactie", "Reactie/opvolging aanwezig", 7))
    if status == "afspraak":
        steps.append(("afspraak", "Afspraak of warme opvolging", 9))
    if status == "no-response":
        steps.append(("no-response", "Geen reactie binnen opvolgvenster", 14))
    return [{
        "status": s,
        "label": label,
        "date": time.strftime("%Y-%m-%d", time.localtime(base + offset * 86400)),
        "source": row.get("status_source", "campagne"),
    } for s, label, offset in steps]


def get_intelligence_stats(qs) -> dict:
    rows, meta = _campaign_rows(qs)
    if not rows:
        return {"ok": True, "meta": meta, "kpis": {}, "funnel": [], "class_distribution": [], "partner_response": [], "weekly_response": []}
    total = len(rows)
    top = [r for r in rows if r["klasse"] in ("A+", "A")]
    contacted = [r for r in rows if r["status"] != "wachtrij"]
    responded = [r for r in rows if r["status"] in ("reactie", "afspraak")]
    appointments = [r for r in rows if r["status"] == "afspraak"]
    backlog = [r for r in rows if r["status"] in ("no-response", "verstuurd")]
    weights = {"A+": .55, "A": .38, "B": .22, "C": .10, "D": .05}
    weighted_pipeline = sum((r["waarde"] or 0) * weights.get(r["klasse"], .08) for r in rows)
    classes = [{"klasse": k, "count": sum(1 for r in rows if r["klasse"] == k)} for k in ("A+", "A", "B", "C", "D", "LEAD", "MAN")]
    funnel_keys = [("in_scope", "In scope", rows), ("contacted", "Gecontacteerd", contacted), ("scanned", "Gescand", [r for r in rows if r["status"] in ("gescand", "reactie", "afspraak")]), ("response", "Reactie", responded), ("appointment", "Afspraak", appointments)]
    funnel = [{"key": k, "label": label, "count": len(vals), "denominator": len(contacted) if k not in ("in_scope", "contacted") else total} for k, label, vals in funnel_keys]
    partners = sorted({r["partner"] for r in rows})
    partner_response = []
    for p in partners:
        p_contacted = [r for r in rows if r["partner"] == p and r["status"] != "wachtrij"]
        p_resp = [r for r in p_contacted if r["status"] in ("reactie", "afspraak")]
        partner_response.append({"partner": p, "contacted": len(p_contacted), "responses": len(p_resp), "rate": round(len(p_resp) / max(1, len(p_contacted)) * 100, 1)})
    partner_response = sorted(partner_response, key=lambda r: r["rate"], reverse=True)[:10]
    weekly_response = []
    for week in range(1, 7):
        scope = [r for r in rows if (r["index"] % 6) + 1 == week and r["status"] != "wachtrij"]
        resp = [r for r in scope if r["status"] in ("reactie", "afspraak")]
        weekly_response.append({"week": f"Week {week}", "contacted": len(scope), "responses": len(resp), "rate": round(len(resp) / max(1, len(scope)) * 100, 1)})
    return _json_ready({
        "ok": True,
        "meta": meta,
        "kpis": {
            "addresses": total,
            "top_count": len(top),
            "top_pct": round(len(top) / max(1, total) * 100, 1),
            "weighted_pipeline": round(weighted_pipeline),
            "facade_m2": round(sum(r["m2"] or 0 for r in rows)),
            "response_rate": round(len(responded) / max(1, len(contacted)) * 100, 1),
            "response_numerator": len(responded),
            "response_denominator": len(contacted),
            "appointments": len(appointments),
            "backlog": len(backlog),
        },
        "class_distribution": [c for c in classes if c["count"]],
        "funnel": funnel,
        "partner_response": partner_response,
        "weekly_response": weekly_response,
        "actions": [
            {"title": f"{len([r for r in top if r['status'] == 'wachtrij'])} A/A+ adressen nog niet toegewezen", "detail": "Plan partnerverdeling voor de volgende golf."},
            {"title": f"{len(backlog)} adressen in follow-up backlog", "detail": "Retarget op energie- of comfortboodschap, zonder koopintentie te claimen."},
            {"title": "Beste segmenten worden zichtbaar in Second brain", "detail": "Gebruik Focus beste cluster om de meest belovende groep te openen."},
        ],
    })


def get_intelligence_rows(qs) -> dict:
    rows, meta = _campaign_rows(qs)
    filtered = _sort_rows(_filter_rows(rows, qs), qs)
    total = len(filtered)
    limit = max(1, min(_safe_int((qs.get("limit", ["250"])[0] or "250"), 250), 5000))
    offset = max(0, _safe_int((qs.get("offset", ["0"])[0] or "0"), 0))
    page = filtered[offset:offset + limit]
    return _json_ready({
        "ok": True,
        "meta": meta,
        "total": total,
        "offset": offset,
        "limit": limit,
        "truncated": offset + limit < total,
        "rows": page,
        "performance": {
            "server_paged": total > limit,
            "bbox_filtered": bool((qs.get("bbox", [""])[0] or "").strip()),
            "brain_node_cap": 80,
            "map_row_cap": 5000,
        },
    })


def _find_intelligence_row(qs, lead_id: str) -> tuple[dict | None, dict]:
    rows, meta = _campaign_rows(qs)
    for row in rows:
        if row["id"] == lead_id or row["capakey"] == lead_id:
            return row, meta
    try:
        idx = int(lead_id)
        if 0 <= idx < len(rows):
            return rows[idx], meta
    except Exception:
        pass
    return None, meta


def get_lead_events(qs, lead_id: str) -> dict:
    row, meta = _find_intelligence_row(qs, lead_id)
    if not row:
        return {"ok": False, "error": "Lead niet gevonden", "meta": meta}
    return _json_ready({"ok": True, "lead_id": lead_id, "events": _status_timeline(row), "meta": meta})


def get_lead_dossier(qs, lead_id: str) -> dict:
    row, meta = _find_intelligence_row(qs, lead_id)
    if not row:
        return {"ok": False, "error": "Lead niet gevonden", "meta": meta}
    dossier = dict(row)
    dossier["timeline"] = _status_timeline(row)
    dossier["provenance_note"] = "Bronnen documenteren opportunity-signalen op gebouwniveau; dit is geen claim over interesse van bewoners."
    return _json_ready({"ok": True, "dossier": dossier, "meta": meta})


def get_brain_graph(qs) -> dict:
    rows, meta = _campaign_rows(qs)
    top_rows = sorted([r for r in rows if r["klasse"] in ("A+", "A")], key=lambda r: r["score"], reverse=True)[:25]
    nodes = [{"id": "campaign", "label": "Campagne", "type": "campaign", "size": 30, "score": 100, "detail": meta.get("source_label", "")}]
    edges = []
    partners = sorted({r["partner"] for r in top_rows})[:10]
    for partner in partners:
        pid = "partner:" + partner
        nodes.append({"id": pid, "label": partner, "type": "partner", "size": 18, "score": 70})
        edges.append({"source": "campaign", "target": pid, "type": "toewijzing"})
    signal_defs = [
        ("sig:m2", "Groot gevelvolume", lambda r: (r["m2"] or 0) >= 180),
        ("sig:vrijstaand", "Vrijstaand/halfopen", lambda r: "vrijstaand" in r["huistype"] or "half" in r["huistype"]),
        ("sig:ratio", "Lage bebouwingsgraad", lambda r: (r["bebouwd_ratio"] or 0) and r["bebouwd_ratio"] < .32),
        ("sig:score", "A/A+ scorecluster", lambda r: r["klasse"] in ("A+", "A")),
    ]
    for sid, label, _ in signal_defs:
        nodes.append({"id": sid, "label": label, "type": "signal", "size": 16, "score": 65})
        edges.append({"source": "campaign", "target": sid, "type": "signaal"})
    learnings = [
        ("learn:timing", "Learning: golf 2 retarget no-response"),
        ("learn:partners", "Learning: partnerfit per sector"),
        ("learn:message", "Learning: energie/comfortboodschap"),
    ]
    for lid, label in learnings:
        nodes.append({"id": lid, "label": label, "type": "learning", "size": 15, "score": 75})
        edges.append({"source": lid, "target": "campaign", "type": "learning"})
    for row in top_rows:
        rid = "lead:" + row["id"]
        nodes.append({"id": rid, "label": row["adres"], "type": "lead", "lead_id": row["id"], "size": 10 + min(14, row["score"] / 8), "score": row["score"], "klasse": row["klasse"], "detail": f"{row['klasse']} · {row['score']} · {row['partner']}"})
        edges.append({"source": "partner:" + row["partner"], "target": rid, "type": "toewijzing"})
        for sid, _, predicate in signal_defs:
            if predicate(row):
                edges.append({"source": sid, "target": rid, "type": "match"})
    if top_rows:
        best_signal = "sig:m2" if sum(1 for r in top_rows if r["m2"] >= 180) >= 3 else "sig:score"
        edges.append({"source": "learn:message", "target": best_signal, "type": "learning-match"})
        edges.append({"source": "learn:timing", "target": "sig:score", "type": "learning-match"})
    return _json_ready({
        "ok": True,
        "meta": meta,
        "nodes": nodes[:80],
        "edges": [e for e in edges if e.get("source") and e.get("target")][:160],
        "quality": {"node_cap": 80, "edge_cap": 160, "source": "campaign_csv_plus_simulated_outcomes" if meta.get("simulated_outcomes") else "campaign_data"},
    })


# ─── LEAD REVIEW + STREET VIEW PREVIEW ──────────────────────────────────────

def _review_for_capakey(capakey: str) -> dict:
    try:
        from facadepilot_lead_review import get_review
        return get_review(capakey)
    except Exception:
        return {
            "decision": "unreviewed",
            "heading": None,
            "pitch": None,
            "fov": None,
            "strafe_m": None,
            "target_box": None,
            "note": "",
        }


def _attach_review(props: dict, capakey: str) -> dict:
    review = _review_for_capakey(capakey)
    props.update({
        "review_decision": review.get("decision", "unreviewed"),
        "review_heading": review.get("heading"),
        "review_pitch": review.get("pitch"),
        "review_fov": review.get("fov"),
        "review_strafe_m": review.get("strafe_m"),
        "review_target_box": review.get("target_box"),
        "review_note": review.get("note", ""),
    })
    return props


def _safe_float(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_cache_key(value: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(value or "lead"))
    return safe[:80].strip("_") or "lead"


def get_streetview_camera(
    lat: float,
    lon: float,
    capakey: str = "",
    strafe_override=None,
    recenter: bool = False,
) -> dict:
    """Return the stored or auto-calculated Street View camera for a lead."""
    from facadepilot_streetview import (
        DEFAULT_FOV, DEFAULT_PITCH, calculate_heading, check_streetview,
        haversine_distance, MAX_PANO_DISTANCE,
    )

    review = _review_for_capakey(capakey)
    pitch = _safe_int(review.get("pitch"), DEFAULT_PITCH)
    fov = _safe_int(review.get("fov"), DEFAULT_FOV)
    if strafe_override not in (None, ""):
        strafe_m = _safe_float(strafe_override, 0) or 0
    else:
        strafe_m = _safe_float(review.get("strafe_m"), 0) or 0
    strafe_m = max(-60, min(60, strafe_m))
    stored_heading = _safe_float(review.get("heading"))
    heading = None if recenter else stored_heading

    meta_payload = {"available": False, "status": "UNKNOWN", "distance_m": None}
    if heading is None or strafe_m:
        meta = check_streetview(lat, lon)
        meta_payload.update({k: meta.get(k) for k in ("available", "status", "pano_id", "pano_lat", "pano_lon")})
        if meta.get("available") and meta.get("pano_lat") and meta.get("pano_lon"):
            dist = haversine_distance(meta["pano_lat"], meta["pano_lon"], lat, lon)
            meta_payload["distance_m"] = round(dist, 1)
            if dist <= MAX_PANO_DISTANCE:
                auto_heading = calculate_heading(meta["pano_lat"], meta["pano_lon"], lat, lon)
                if strafe_m:
                    from facadepilot_streetview import offset_coordinate
                    strafe_bearing = auto_heading + (90 if strafe_m > 0 else -90)
                    query_lat, query_lon = offset_coordinate(
                        meta["pano_lat"], meta["pano_lon"], strafe_bearing, abs(strafe_m)
                    )
                    shifted = check_streetview(query_lat, query_lon)
                    if shifted.get("available") and shifted.get("pano_lat") and shifted.get("pano_lon"):
                        shifted_dist = haversine_distance(shifted["pano_lat"], shifted["pano_lon"], lat, lon)
                        meta_payload.update({
                            "shifted_pano_id": shifted.get("pano_id"),
                            "shifted_pano_lat": shifted.get("pano_lat"),
                            "shifted_pano_lon": shifted.get("pano_lon"),
                            "shifted_distance_m": round(shifted_dist, 1),
                        })
                        if shifted_dist <= MAX_PANO_DISTANCE:
                            auto_heading = calculate_heading(shifted["pano_lat"], shifted["pano_lon"], lat, lon)
                if heading is None:
                    heading = auto_heading

    return {
        "heading": round(heading if heading is not None else 0, 1),
        "pitch": pitch,
        "fov": fov,
        "strafe_m": round(strafe_m, 1),
        "source": "auto" if recenter or stored_heading is None else "override",
        "meta": meta_payload,
    }


def save_lead_review(data: dict) -> dict:
    from facadepilot_lead_review import update_review

    capakey = (data.get("capakey", [""])[0] or "").strip()
    decision = (data.get("decision", [""])[0] or "").strip() or None
    note = (data.get("note", [""])[0] or "").strip()
    updates = {"note": note}
    if decision is not None:
        updates["decision"] = decision
    for key in ("heading", "pitch", "fov", "strafe_m"):
        if key in data:
            updates[key] = (data.get(key, [""])[0] or "").strip()
    if "target_box" in data:
        updates["target_box"] = (data.get("target_box", [""])[0] or "").strip()
    return update_review(capakey, **updates)


def get_lead_review_summary(niscode: str | None = None, manual: bool = False) -> dict:
    geo = get_leads_geojson(niscode, manual=manual)
    features = geo.get("features", [])
    counts = {"selected": 0, "reserve": 0, "removed": 0, "unreviewed": 0}
    items = {"selected": [], "reserve": [], "removed": []}

    for feature in features:
        props = feature.get("properties", {})
        decision = props.get("review_decision") or "unreviewed"
        counts[decision] = counts.get(decision, 0) + 1
        if decision in items:
            items[decision].append({
                "capakey": props.get("capakey", ""),
                "adres": props.get("adres", ""),
                "klasse": props.get("klasse", ""),
                "score": props.get("score", 0),
                "huistype": props.get("huistype", ""),
                "heading": props.get("review_heading"),
                "pitch": props.get("review_pitch"),
                "fov": props.get("review_fov"),
                "target_box": props.get("review_target_box"),
            })

    return {
        "source": geo.get("source", "none"),
        "total": len(features),
        "counts": counts,
        "items": items,
        "selected_count": counts.get("selected", 0),
    }


def field_photo_index_path() -> Path:
    return HERE / "field_photos" / "index.json"


def load_field_photo_index() -> dict:
    path = field_photo_index_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_field_photo_index(index: dict) -> None:
    path = field_photo_index_path()
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_photo_key(value: str) -> str:
    import re

    raw = (value or "").strip() or f"photo_{int(time.time())}"
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    return (key or f"photo_{int(time.time())}")[:96]


def list_field_photos() -> dict:
    return {"ok": True, "photos": load_field_photo_index()}


# ─── HTML DASHBOARD ──────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>FacadePilot Pipeline</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%);min-height:100vh;color:#e2e8f0;padding:24px}
.container{max-width:1200px;margin:0 auto}

header{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;padding-bottom:18px;border-bottom:1px solid rgba(255,255,255,0.1)}
.logo{display:flex;align-items:center;gap:14px}
.logo-icon{width:48px;height:48px;background:linear-gradient(135deg,#60a5fa,#3b82f6);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:700;color:#fff;letter-spacing:-1px;box-shadow:0 4px 16px rgba(59,130,246,0.4)}
h1{font-size:24px;font-weight:700;letter-spacing:-0.3px}
.subtitle{font-size:13px;color:#94a3b8;margin-top:2px}

.layout{display:grid;grid-template-columns:340px 1fr;gap:20px}
@media(max-width:900px){.layout{grid-template-columns:1fr}}

.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:22px;backdrop-filter:blur(10px)}
.card h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:#94a3b8;margin-bottom:16px}

.field{margin-bottom:14px}
.field label{display:block;font-size:12px;color:#94a3b8;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.5px}
input,select,textarea{width:100%;padding:9px 12px;background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.12);border-radius:8px;color:#e2e8f0;font-size:14px;font-family:inherit}
textarea{min-height:68px;resize:vertical;line-height:1.35}
.json-editor{min-height:180px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:11px;line-height:1.45;white-space:pre}
input:focus,select:focus,textarea:focus{outline:none;border-color:#60a5fa;box-shadow:0 0 0 3px rgba(96,165,250,0.15)}

.mode-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.mode-option{display:block}
.mode-option input{display:none}
.mode-option span{display:block;min-height:76px;padding:11px 12px;background:rgba(15,23,42,0.72);border:1px solid rgba(148,163,184,0.2);border-radius:10px;cursor:pointer;transition:all .16s}
.mode-option strong{display:block;font-size:12px;color:#e2e8f0;margin-bottom:5px;line-height:1.2;text-transform:none;letter-spacing:0}
.mode-option small{display:block;font-size:10.5px;line-height:1.35;color:#94a3b8;text-transform:none;letter-spacing:0}
.mode-option input:checked+span{border-color:rgba(96,165,250,0.62);background:rgba(96,165,250,0.13);box-shadow:0 0 0 3px rgba(96,165,250,0.09)}
.mode-note{font-size:11px;line-height:1.35;color:#94a3b8;margin-top:7px}
.help-panel{background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.18);border-radius:11px;padding:11px 12px;margin:10px 0 14px}
.help-panel strong{display:block;color:#dbeafe;font-size:12px;line-height:1.25;margin-bottom:5px}
.help-panel p{font-size:11px;line-height:1.45;color:#a8b7cc;margin:0}
.path-grid{display:grid;gap:8px;margin:10px 0 12px}
.path-row{background:rgba(15,23,42,.62);border:1px solid rgba(148,163,184,.16);border-radius:9px;padding:9px 10px;overflow:hidden}
.path-row span{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#7fa7d8;font-weight:800;margin-bottom:4px}
.path-row code{display:block;font-size:11px;line-height:1.35;color:#e2e8f0;white-space:normal;overflow-wrap:anywhere}
.workflow-step{display:grid;gap:8px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);border-radius:11px;padding:12px;margin-bottom:10px}
.workflow-step-title{display:flex;gap:8px;align-items:center;font-size:12px;font-weight:800;color:#e2e8f0}
.workflow-step-title b{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:999px;background:rgba(96,165,250,.18);color:#93c5fd;font-size:11px}
.field-help{font-size:11px;line-height:1.4;color:#94a3b8;margin-top:6px}
.button-row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}

.toggle-row{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.toggle-row:last-child{border:none}
.toggle-label{font-size:13px}
.toggle-hint{font-size:11px;color:#94a3b8;margin-top:2px}
.toggle{position:relative;width:40px;height:22px;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;inset:0;background:rgba(255,255,255,0.12);border-radius:11px;cursor:pointer;transition:.2s}
.toggle .slider::before{content:"";position:absolute;width:16px;height:16px;left:3px;top:3px;background:#94a3b8;border-radius:50%;transition:.2s}
.toggle input:checked+.slider{background:#3b82f6}
.toggle input:checked+.slider::before{transform:translateX(18px);background:#fff}
.toggle input:disabled+.slider{opacity:.45;cursor:not-allowed}

.badge{display:inline-block;background:rgba(96,165,250,0.15);color:#60a5fa;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600;margin-left:4px}
.badge.warn{background:rgba(255,200,50,0.15);color:#fbbf24}
.badge.ok{background:rgba(34,197,94,0.12);color:#4ade80}

.btn{width:100%;padding:14px;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;transition:all .15s;font-family:inherit;margin-top:8px}
.btn-primary{background:linear-gradient(135deg,#60a5fa,#3b82f6);color:#fff;box-shadow:0 4px 12px rgba(59,130,246,0.3)}
.btn-primary:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 6px 16px rgba(59,130,246,0.5)}
.btn-primary:disabled{opacity:.4;cursor:not-allowed}
.btn-danger{background:rgba(220,53,69,0.15);color:#fca5a5;border:1px solid rgba(220,53,69,0.3)}
.btn-danger:hover{background:rgba(220,53,69,0.25)}

/* Steps tracker */
.steps{display:flex;flex-direction:column;gap:10px;margin-bottom:18px}
.step{background:rgba(0,0,0,0.2);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:14px 16px;transition:border-color .3s}
.step.running{border-color:rgba(96,165,250,0.5);background:rgba(96,165,250,0.06)}
.step.done{border-color:rgba(34,197,94,0.3)}
.step.skipped{opacity:.45}
.step-header{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.step-icon{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
.step-icon.pending{background:rgba(255,255,255,0.06)}
.step-icon.running{background:rgba(96,165,250,0.2)}
.step-icon.done{background:rgba(34,197,94,0.15)}
.step-icon.skipped{background:rgba(255,255,255,0.04)}
.step-title{font-size:14px;font-weight:600}
.step-msg{font-size:12px;color:#94a3b8;margin-left:38px}
.step-bar{height:4px;background:rgba(0,0,0,0.3);border-radius:2px;margin:6px 0 0 38px;overflow:hidden}
.step-bar-fill{height:100%;background:linear-gradient(90deg,#60a5fa,#4ade80);width:0%;transition:width .3s;border-radius:2px}

.spinner-sm{width:14px;height:14px;border:2px solid rgba(96,165,250,0.3);border-top-color:#60a5fa;border-radius:50%;animation:spin .8s linear infinite;flex-shrink:0}
@keyframes spin{to{transform:rotate(360deg)}}

/* Pulsing glow for active step */
.step.running{animation:pulse-glow 2s ease-in-out infinite}
@keyframes pulse-glow{0%,100%{border-color:rgba(96,165,250,0.3);box-shadow:0 0 0 rgba(96,165,250,0)}50%{border-color:rgba(96,165,250,0.7);box-shadow:0 0 16px rgba(96,165,250,0.15)}}

/* Elapsed timer bar */
.elapsed-bar{display:flex;align-items:center;justify-content:space-between;background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:12px 16px;margin-bottom:14px}
.elapsed-bar.hidden{display:none}
.elapsed-label{font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px}
.elapsed-value{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums;color:#60a5fa}
.elapsed-gemeente{font-size:13px;color:#e2e8f0;font-weight:500}
.elapsed-dots{display:inline-block;width:20px;text-align:left}

/* Step bar shimmer when running */
.step.running .step-bar-fill{background:linear-gradient(90deg,#60a5fa,#4ade80,#60a5fa);background-size:200% 100%;animation:shimmer 1.5s linear infinite}
@keyframes shimmer{to{background-position:-200% 0}}

/* Log */
.log{background:#0a0f1a;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:14px;font-family:"SF Mono",Menlo,Monaco,Consolas,monospace;font-size:12px;max-height:240px;overflow-y:auto;white-space:pre-wrap;color:#94a3b8;line-height:1.6}
.log:empty::before{content:"Pipeline nog niet gestart.";color:#475569;font-style:italic}

/* Output files */
.file-list{list-style:none}
.file-list li{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:rgba(0,0,0,0.15);border-radius:8px;margin-bottom:6px;font-size:13px;cursor:pointer;transition:background .15s}
.file-list li:hover{background:rgba(96,165,250,0.12)}
.file-list li.active{background:rgba(96,165,250,0.2);border:1px solid rgba(96,165,250,0.3)}
.file-label{color:#94a3b8;font-size:11px}
.file-icon{margin-right:8px}

/* Preview panel */
.preview-panel{background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:20px;margin-top:16px;display:none}
.preview-panel.active{display:block}
.preview-panel h3{font-size:14px;margin-bottom:12px;color:#60a5fa}
.preview-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.preview-item{position:relative;border-radius:10px;overflow:hidden;background:rgba(0,0,0,0.2);border:1px solid rgba(255,255,255,0.06)}
.preview-item img{width:100%;display:block;border-radius:10px}
.preview-item .label{position:absolute;top:8px;left:8px;background:rgba(0,0,0,0.7);color:#fff;font-size:11px;padding:3px 8px;border-radius:6px;font-weight:600}
.preview-item.bad{border-color:rgba(220,53,69,0.4)}
.landing-preview-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin-top:12px}
.landing-preview-card{display:flex;flex-direction:column;gap:8px;padding:12px;background:rgba(15,23,42,.7);border:1px solid rgba(255,255,255,.08);border-radius:10px}
.landing-preview-card strong{font-size:13px;color:#e2e8f0;line-height:1.25}
.landing-preview-card span{font-size:11px;color:#94a3b8}
.landing-preview-card a{display:inline-flex;align-items:center;justify-content:center;padding:8px 10px;border-radius:8px;background:rgba(96,165,250,.14);border:1px solid rgba(96,165,250,.32);color:#bfdbfe;font-size:12px;font-weight:700;text-decoration:none}
.landing-preview-card a:hover{background:rgba(96,165,250,.22);color:#fff}

/* Render gallery */
.render-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:12px}
.render-thumb{position:relative;border-radius:10px;overflow:hidden;cursor:pointer;border:2px solid transparent;transition:all .15s;aspect-ratio:1}
.render-thumb:hover{border-color:rgba(96,165,250,0.5);transform:scale(1.02)}
.render-thumb.selected{border-color:#60a5fa;box-shadow:0 0 12px rgba(96,165,250,0.3)}
.render-thumb img{width:100%;height:100%;object-fit:cover}
.render-thumb .overlay{position:absolute;inset:0;background:linear-gradient(transparent 50%,rgba(0,0,0,0.7));display:flex;align-items:flex-end;padding:6px 8px}
.render-thumb .overlay span{font-size:10px;color:#fff;font-weight:500}
.variant-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.variant-item{position:relative;border-radius:10px;overflow:hidden;background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.08)}
.variant-item img{width:100%;display:block;aspect-ratio:4/3;object-fit:cover}
.variant-item .label{position:absolute;top:8px;left:8px;background:rgba(0,0,0,0.72);color:#fff;font-size:11px;padding:4px 8px;border-radius:6px;font-weight:700}
.variant-count{position:absolute;top:8px;right:8px;background:rgba(45,138,126,0.9);color:#fff;font-size:10px;font-weight:700;border-radius:999px;padding:3px 7px}

/* Replace render */
.replace-section{margin-top:16px;padding:16px;background:rgba(251,191,36,0.06);border:1px dashed rgba(251,191,36,0.3);border-radius:12px}
.replace-section h4{font-size:13px;color:#fbbf24;margin-bottom:8px}
.replace-section p{font-size:12px;color:#94a3b8;margin-bottom:10px}
.drop-zone{border:2px dashed rgba(255,255,255,0.15);border-radius:10px;padding:24px;text-align:center;color:#94a3b8;font-size:13px;transition:all .2s;cursor:pointer}
.drop-zone:hover,.drop-zone.dragover{border-color:#60a5fa;background:rgba(96,165,250,0.06);color:#60a5fa}
.drop-zone input{display:none}
.btn-sm{padding:8px 16px;font-size:12px;border-radius:8px;border:none;cursor:pointer;font-family:inherit;font-weight:600}
.btn-copy{background:rgba(96,165,250,0.15);color:#60a5fa;border:1px solid rgba(96,165,250,0.3)}
.btn-copy:hover{background:rgba(96,165,250,0.25)}

/* Tabs */
.tab-bar{display:flex;gap:4px;margin-bottom:14px}
.tab{padding:8px 16px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;color:#94a3b8;background:rgba(0,0,0,0.2);border:1px solid transparent;transition:all .15s}
.tab:hover{color:#e2e8f0}
.tab.active{color:#60a5fa;background:rgba(96,165,250,0.1);border-color:rgba(96,165,250,0.3)}

/* Done banner */
.done-banner{background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(96,165,250,0.12));border:1px solid rgba(34,197,94,0.25);border-radius:12px;padding:18px;margin-bottom:16px;display:none}
.done-banner.active{display:block}
.done-banner h3{font-size:16px;color:#4ade80;margin-bottom:8px}
.done-banner p{font-size:13px;color:#cbd5e1;margin-bottom:4px}

.section{margin-top:16px}

/* Kaart-tab */
.map-review-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;align-items:stretch}
@media(max-width:1000px){.map-review-layout{grid-template-columns:1fr}}
#mapContainer{height:560px;border-radius:10px;overflow:hidden;border:1px solid rgba(255,255,255,0.06);background:#1a2236}
.lead-review-panel{min-height:560px;background:#0a0f1a;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:12px}
.lead-review-empty{height:100%;display:flex;align-items:center;justify-content:center;text-align:center;color:#64748b;font-size:13px;line-height:1.45;padding:20px}
.lead-review-title{font-size:15px;font-weight:700;line-height:1.25}
.lead-review-meta{font-size:11px;color:#94a3b8;line-height:1.5}
.streetview-frame{position:relative;background:#111827;border:1px solid rgba(255,255,255,0.06);border-radius:8px;overflow:hidden;aspect-ratio:4/3;cursor:grab;touch-action:none;user-select:none}
.streetview-frame.dragging{cursor:grabbing}
.streetview-frame.box-mode{cursor:crosshair}
.streetview-frame img{width:100%;height:100%;object-fit:cover;display:block;pointer-events:none;-webkit-user-drag:none}
.streetview-frame iframe{width:100%;height:100%;border:0;display:block;background:#0a0f16}
.streetview-frame.loading::after{content:"Street View laden...";position:absolute;inset:0;display:grid;place-items:center;background:rgba(10,15,26,0.7);color:#cbd5e1;font-size:12px}
.target-box-overlay{position:absolute;border:2px solid #fbbf24;background:rgba(251,191,36,.13);box-shadow:0 0 0 9999px rgba(0,0,0,.18);display:none;pointer-events:none}
.target-box-help{position:absolute;left:8px;bottom:8px;background:rgba(15,23,42,.82);border:1px solid rgba(255,255,255,.1);border-radius:7px;padding:5px 7px;color:#e2e8f0;font-size:10px;line-height:1.25;pointer-events:none}
.review-actions{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}
.review-action{padding:9px 7px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);color:#cbd5e1;font-size:11px;font-weight:700;cursor:pointer}
.review-action:hover{background:rgba(255,255,255,0.08)}
.review-action.active[data-decision="selected"]{background:rgba(34,197,94,0.18);border-color:rgba(34,197,94,0.5);color:#86efac}
.review-action.active[data-decision="reserve"]{background:rgba(251,191,36,0.16);border-color:rgba(251,191,36,0.45);color:#fde68a}
.review-action.active[data-decision="removed"]{background:rgba(248,113,113,0.15);border-color:rgba(248,113,113,0.45);color:#fecaca}
.camera-grid{display:grid;gap:8px}
.camera-row{display:grid;grid-template-columns:64px 1fr 42px;gap:8px;align-items:center;font-size:11px;color:#94a3b8}
.camera-row input[type=range]{width:100%;accent-color:#60a5fa}
.camera-value{text-align:right;color:#e2e8f0;font-variant-numeric:tabular-nums}
.camera-nudges{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.camera-nudges button,.camera-save{padding:8px;border-radius:8px;border:1px solid rgba(96,165,250,0.25);background:rgba(96,165,250,0.11);color:#bfdbfe;font-size:11px;font-weight:700;cursor:pointer}
.camera-nudges button.active{border-color:rgba(251,191,36,.5);background:rgba(251,191,36,.16);color:#fde68a}
.camera-save{width:100%;margin-top:2px}
.review-summary{margin-top:12px;background:rgba(0,0,0,0.2);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:12px}
.review-summary-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
.review-counts{display:flex;gap:8px;flex-wrap:wrap;font-size:11px;color:#cbd5e1}
.review-list{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
@media(max-width:1000px){.review-list{grid-template-columns:1fr}}
.review-list-col h4{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;margin-bottom:6px}
.review-list-col ul{list-style:none;display:grid;gap:5px;max-height:170px;overflow:auto}
.review-list-col li{font-size:11px;line-height:1.35;background:rgba(255,255,255,0.035);border-radius:7px;padding:7px;color:#cbd5e1}
.review-start{padding:9px 13px;border-radius:8px;border:1px solid rgba(34,197,94,.35);background:rgba(34,197,94,.14);color:#86efac;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}
.review-start:disabled{opacity:.45;cursor:not-allowed}
.manual-list{display:grid;gap:6px;margin-bottom:10px}
.manual-item{display:grid;grid-template-columns:1fr auto auto;gap:6px;align-items:center;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:8px}
.manual-item-title{font-size:12px;color:#e2e8f0;line-height:1.3}
.manual-item-meta{font-size:10px;color:#94a3b8;margin-top:2px}
.manual-icon-btn{width:30px;height:30px;border-radius:7px;border:1px solid rgba(96,165,250,.25);background:rgba(96,165,250,.11);color:#bfdbfe;font-size:14px;font-weight:800;cursor:pointer}
.manual-icon-btn.danger{border-color:rgba(248,113,113,.35);background:rgba(248,113,113,.12);color:#fecaca}
.preset-options{display:grid;gap:7px}
.preset-option{display:grid;grid-template-columns:auto 1fr;gap:9px;align-items:start;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:9px;cursor:pointer;transition:border-color .15s,background .15s}
.preset-option:hover{background:rgba(96,165,250,.08);border-color:rgba(96,165,250,.25)}
.preset-option input{width:16px;height:16px;margin-top:1px;accent-color:#2d8a7e}
.preset-title{font-size:12px;color:#e2e8f0;font-weight:700;line-height:1.25}
.preset-meta{font-size:10px;color:#94a3b8;margin-top:2px;line-height:1.35}
.preset-cost{font-size:11px;color:#fbbf24;margin-top:7px;min-height:14px}
.copy-details{margin-top:12px;border:1px solid rgba(255,255,255,.08);border-radius:10px;background:rgba(0,0,0,.14);overflow:hidden}
.copy-details summary{cursor:pointer;list-style:none;padding:10px 12px;font-size:12px;font-weight:800;color:#bfdbfe;display:flex;align-items:center;justify-content:space-between}
.copy-details summary::-webkit-details-marker{display:none}
.copy-details summary::after{content:'bewerken';font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em}
.copy-details[open] summary{border-bottom:1px solid rgba(255,255,255,.06)}
.copy-inner{padding:12px}
.copy-inner .field label{text-transform:none;letter-spacing:0;color:#cbd5e1;font-size:11px}
.copy-help{font-size:11px;color:#94a3b8;line-height:1.45;margin:-4px 0 12px}
.review-pill{display:inline-block;border-radius:999px;padding:2px 7px;font-size:10px;font-weight:700;text-transform:uppercase}
.review-pill.selected{background:rgba(34,197,94,0.18);color:#86efac}
.review-pill.reserve{background:rgba(251,191,36,0.16);color:#fde68a}
.review-pill.removed{background:rgba(248,113,113,0.15);color:#fecaca}
.review-pill.unreviewed{background:rgba(148,163,184,0.14);color:#cbd5e1}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 4px}
.legend-item{display:flex;align-items:center;gap:6px;font-size:12px;color:#cbd5e1}
.legend-dot{width:14px;height:14px;border-radius:50%;border:2px solid rgba(255,255,255,0.5)}
.leaflet-container{font-family:inherit;background:#1a2236}
.leaflet-popup-content-wrapper{background:#1e293b;color:#e2e8f0;border-radius:10px}
.leaflet-popup-tip{background:#1e293b}
.leaflet-popup-content{margin:12px 14px;font-size:13px;line-height:1.5}
.leaflet-popup-content .pop-adres{font-weight:600;margin-bottom:4px}
.leaflet-popup-content .pop-meta{font-size:11px;color:#94a3b8}
.leaflet-popup-content img{margin-top:8px;width:100%;border-radius:6px}

/* CRM-funnel */
.funnel-row{display:flex;align-items:center;gap:10px;padding:6px 0;font-size:13px}
.funnel-label{width:130px;color:#94a3b8;font-size:12px}
.funnel-bar-bg{flex:1;height:14px;background:rgba(0,0,0,0.3);border-radius:4px;overflow:hidden;position:relative}
.funnel-bar-fill{height:100%;background:linear-gradient(90deg,#60a5fa,#4ade80);border-radius:4px;transition:width .3s}
.funnel-count{width:40px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.funnel-pct{width:50px;text-align:right;font-size:11px;color:#94a3b8}

/* CRM-lead lijst */
.crm-table{width:100%;font-size:12px;border-collapse:collapse}
.crm-table th{text-align:left;padding:8px 6px;color:#94a3b8;text-transform:uppercase;font-size:10px;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.08)}
.crm-table td{padding:8px 6px;border-bottom:1px solid rgba(255,255,255,0.04)}
.crm-table tr:hover{background:rgba(96,165,250,0.06)}
.crm-status{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;text-transform:uppercase}
.crm-status.gegenereerd{background:rgba(148,163,184,0.15);color:#cbd5e1}
.crm-status.geflyerd{background:rgba(96,165,250,0.15);color:#60a5fa}
.crm-status.gescand{background:rgba(168,85,247,0.15);color:#c084fc}
.crm-status.contact{background:rgba(251,191,36,0.15);color:#fbbf24}
.crm-status.afspraak{background:rgba(34,197,94,0.15);color:#4ade80}
.crm-status.klant{background:rgba(34,197,94,0.3);color:#4ade80;font-weight:700}
.crm-status.afgewezen{background:rgba(220,53,69,0.15);color:#fca5a5}

/* ─── Review-poorten (HITL stap 3) ─── */
.review-stats{font-size:12px;color:#c8dff5;margin:10px 0;display:grid;gap:4px}
.review-chip{display:inline-block;background:rgba(255,255,255,.07);border-radius:7px;padding:2px 7px;font-size:11px;color:#fbbf24;margin-right:4px}
.review-muted{color:#94a3b8;font-size:11px}
.review-bulk{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,.08);padding-bottom:10px}
.review-bulk-status{font-size:11px;color:#8faed6}
.review-queue{display:grid;gap:12px}
.review-item{background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:12px}
.review-item-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px;color:#e2e8f0;margin-bottom:8px}
.review-item .preview-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0}
.review-item .preview-item img{width:100%;border-radius:8px;display:block}
.review-item .preview-item .label{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.review-noimg{display:flex;align-items:center;justify-content:center;min-height:120px;color:#fca5a5;font-size:12px;background:rgba(0,0,0,.2);border-radius:8px}
.review-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px}
.review-item-status{font-size:11px;color:#8faed6}
.review-reason-panel{margin-top:8px;border-top:1px dashed rgba(255,255,255,.12);padding-top:8px}
.review-reason-chips{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.review-note{width:100%;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.12);border-radius:7px;color:#e2e8f0;font-size:12px;padding:6px 8px}
.review-empty{font-size:12px;color:#5a7a9c;padding:10px 0}
.review-truthfail{font-size:11px;color:#fca5a5}
.review-flyerinfo{font-size:12px;color:#c8dff5;margin:6px 0}
.review-flyerinfo a{color:#60a5fa}
.review-go-card{background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:14px;margin-top:10px}
.review-go-card h3{font-size:13px;margin:0 0 10px;color:#e2e8f0}
.review-go-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.review-go-num{font-size:20px;font-weight:800;color:#e2e8f0}
.review-go-ok{color:#4ade80;font-size:12px;font-weight:700}

/* HomePilot Campaign OS v2 */
:root{
  --hp-paper:#f7fafc;
  --hp-panel:#ffffff;
  --hp-panel-soft:#eef4f8;
  --hp-ink:#172033;
  --hp-muted:#64748b;
  --hp-line:#d8e2ea;
  --hp-blue:#12304f;
  --hp-blue-2:#1f5f8b;
  --hp-teal:#0f766e;
  --hp-copper:#b86b3d;
  --hp-amber:#b7791f;
  --hp-danger:#b42318;
  --hp-shadow:0 18px 40px rgba(21,38,56,.08);
}
body.hp-ui-v2{
  background:var(--hp-paper);
  color:var(--hp-ink);
  padding:0;
  min-height:100vh;
}
body.hp-ui-v2 .container{
  max-width:none;
  margin:0;
  padding:0;
}
body.hp-ui-v2 .legacy-header{
  display:none;
}
.hp-shell{
  position:fixed;
  inset:0 auto 0 0;
  width:92px;
  z-index:50;
  display:flex;
  flex-direction:column;
  background:#102033;
  color:#eef6fb;
  border-right:1px solid rgba(255,255,255,.12);
}
.hp-brand{
  padding:22px 20px 18px;
  border-bottom:1px solid rgba(255,255,255,.11);
}
.hp-brand-row{
  display:flex;
  gap:12px;
  align-items:center;
}
.hp-mark{
  width:42px;
  height:42px;
  border-radius:8px;
  display:grid;
  place-items:center;
  background:linear-gradient(135deg,#f5f7fb,#cfe0ed);
  color:#102033;
  font-weight:900;
  letter-spacing:0;
}
.hp-brand h1{
  font-size:17px;
  line-height:1.15;
  letter-spacing:0;
  margin:0;
}
.hp-brand p{
  margin:3px 0 0;
  font-size:12px;
  color:#a9bac8;
}
.hp-nav{
  display:grid;
  gap:5px;
  padding:16px 12px 10px;
}
.hp-nav-btn{
  display:grid;
  grid-template-columns:30px 1fr auto;
  align-items:center;
  gap:8px;
  min-height:42px;
  border:0;
  border-radius:8px;
  background:transparent;
  color:#c7d5e2;
  text-align:left;
  font:inherit;
  cursor:pointer;
  padding:7px 9px;
}
.hp-nav-btn:hover{
  background:rgba(255,255,255,.08);
  color:#fff;
}
.hp-nav-btn.active{
  background:#eef6fb;
  color:#102033;
  box-shadow:0 8px 20px rgba(0,0,0,.16);
}
.hp-nav-ico{
  width:28px;
  height:28px;
  border-radius:7px;
  display:grid;
  place-items:center;
  background:rgba(255,255,255,.1);
  font-size:11px;
  font-weight:900;
  letter-spacing:0;
}
.hp-nav-btn.active .hp-nav-ico{
  background:#d7e8f2;
  color:#102033;
}
.hp-nav-label{
  font-size:13px;
  font-weight:760;
}
.hp-nav-count{
  min-width:20px;
  height:20px;
  border-radius:999px;
  display:grid;
  place-items:center;
  background:rgba(255,255,255,.1);
  color:#dbe8f1;
  font-size:10px;
  font-weight:800;
}
.hp-nav-btn.active .hp-nav-count{
  background:#c46f3f;
  color:#fff;
}
.hp-side-footer{
  margin-top:auto;
  padding:14px 16px 18px;
  display:grid;
  gap:9px;
  border-top:1px solid rgba(255,255,255,.11);
}
.hp-side-metric{
  display:flex;
  justify-content:space-between;
  gap:12px;
  font-size:12px;
  color:#a9bac8;
}
.hp-side-metric strong{
  color:#fff;
  font-variant-numeric:tabular-nums;
}
.hp-topbar{
  margin-left:272px;
  min-height:78px;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:center;
  gap:16px;
  padding:16px 28px;
  background:rgba(247,250,252,.94);
  border-bottom:1px solid var(--hp-line);
  position:sticky;
  top:0;
  z-index:40;
  backdrop-filter:blur(14px);
}
.hp-title-kicker{
  font-size:11px;
  font-weight:900;
  letter-spacing:.1em;
  text-transform:uppercase;
  color:var(--hp-copper);
  margin-bottom:4px;
}
.hp-title-main{
  font-size:22px;
  font-weight:860;
  line-height:1.15;
  letter-spacing:0;
  color:var(--hp-ink);
}
.hp-title-sub{
  margin-top:4px;
  font-size:13px;
  color:var(--hp-muted);
}
.hp-actions{
  display:flex;
  align-items:center;
  justify-content:flex-end;
  gap:8px;
  flex-wrap:wrap;
}
.hp-chip{
  display:inline-flex;
  align-items:center;
  gap:6px;
  height:34px;
  border-radius:999px;
  border:1px solid var(--hp-line);
  background:#fff;
  color:var(--hp-ink);
  padding:0 11px;
  font-size:12px;
  font-weight:750;
  white-space:nowrap;
}
.hp-chip b{
  color:var(--hp-teal);
}
.hp-primary-action,.hp-secondary-action{
  height:38px;
  border-radius:8px;
  border:1px solid transparent;
  padding:0 14px;
  font:inherit;
  font-size:13px;
  font-weight:820;
  cursor:pointer;
}
.hp-primary-action{
  background:var(--hp-teal);
  color:#fff;
  box-shadow:0 10px 18px rgba(15,118,110,.18);
}
.hp-primary-action:hover{
  background:#0b665f;
}
.hp-secondary-action{
  background:#fff;
  border-color:var(--hp-line);
  color:var(--hp-ink);
}
.hp-secondary-action:hover{
  background:#eef4f8;
}
.hp-step-rail{
  margin-left:272px;
  padding:16px 28px 0;
  display:grid;
  grid-template-columns:repeat(6,minmax(112px,1fr));
  gap:8px;
}
.hp-step-chip{
  border:1px solid var(--hp-line);
  border-left:4px solid var(--hp-blue-2);
  background:#fff;
  min-height:66px;
  border-radius:8px;
  padding:9px 10px;
  cursor:pointer;
  text-align:left;
  color:var(--hp-ink);
  box-shadow:0 8px 16px rgba(21,38,56,.05);
}
.hp-step-chip:hover{
  border-color:#adc4d6;
  transform:translateY(-1px);
}
.hp-step-chip.is-active{
  border-left-color:var(--hp-copper);
  background:#fff8f2;
}
.hp-step-chip span{
  display:block;
  font-size:10px;
  color:var(--hp-muted);
  text-transform:uppercase;
  letter-spacing:.08em;
  font-weight:900;
  margin-bottom:5px;
}
.hp-step-chip strong{
  display:block;
  font-size:13px;
  line-height:1.2;
  letter-spacing:0;
}
.hp-overview{
  margin-left:272px;
  padding:22px 28px 36px;
}
.hp-overview-grid{
  display:grid;
  grid-template-columns:1.15fr .85fr;
  gap:16px;
  align-items:start;
}
.hp-command-panel,.hp-board-panel,.hp-overview-card{
  background:#fff;
  border:1px solid var(--hp-line);
  border-radius:8px;
  box-shadow:var(--hp-shadow);
}
.hp-command-panel{
  padding:20px;
}
.hp-command-head{
  display:flex;
  justify-content:space-between;
  gap:18px;
  align-items:flex-start;
  margin-bottom:16px;
}
.hp-command-head h2{
  font-size:19px;
  line-height:1.2;
  letter-spacing:0;
  color:var(--hp-ink);
  margin:0;
}
.hp-command-head p{
  font-size:13px;
  color:var(--hp-muted);
  line-height:1.45;
  max-width:650px;
  margin-top:6px;
}
.hp-status-pill{
  display:inline-flex;
  align-items:center;
  min-height:30px;
  border-radius:999px;
  padding:0 10px;
  background:#eff8f6;
  color:var(--hp-teal);
  font-size:12px;
  font-weight:850;
  white-space:nowrap;
}
.hp-card-grid{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:10px;
}
.hp-overview-card{
  padding:15px;
  display:grid;
  gap:10px;
  min-height:150px;
}
.hp-overview-card h3{
  font-size:14px;
  line-height:1.25;
  margin:0;
  color:var(--hp-ink);
}
.hp-overview-card p{
  margin:0;
  font-size:12px;
  line-height:1.45;
  color:var(--hp-muted);
}
.hp-card-stat{
  display:flex;
  align-items:baseline;
  gap:8px;
  margin-top:auto;
}
.hp-card-stat strong{
  font-size:24px;
  line-height:1;
  color:var(--hp-blue);
  font-variant-numeric:tabular-nums;
}
.hp-card-stat span{
  font-size:11px;
  color:var(--hp-muted);
  font-weight:760;
  text-transform:uppercase;
  letter-spacing:.06em;
}
.hp-board-panel{
  padding:18px;
}
.hp-board-panel h2{
  font-size:15px;
  margin:0 0 12px;
  color:var(--hp-ink);
}
.hp-kanban{
  display:grid;
  gap:8px;
}
.hp-kanban-row{
  display:grid;
  grid-template-columns:94px 1fr 38px;
  align-items:center;
  gap:10px;
  font-size:12px;
}
.hp-kanban-row span:first-child{
  color:var(--hp-muted);
  font-weight:780;
}
.hp-progress-track{
  height:9px;
  border-radius:999px;
  background:#e8eef3;
  overflow:hidden;
}
.hp-progress-fill{
  height:100%;
  border-radius:999px;
  background:linear-gradient(90deg,var(--hp-blue-2),var(--hp-teal));
}
.hp-kanban-row strong{
  color:var(--hp-ink);
  text-align:right;
  font-variant-numeric:tabular-nums;
}
body.hp-ui-v2 .layout{
  margin-left:272px;
  padding:18px 28px 40px;
  display:grid;
  grid-template-columns:minmax(320px,420px) minmax(0,1fr);
  gap:18px;
}
body.hp-ui-v2.hp-view-campaigns .layout{
  display:none;
}
body.hp-ui-v2:not(.hp-view-campaigns) #hpCampaignOverview{
  display:none;
}
body.hp-ui-v2:not(.hp-view-campaigns) .hp-redesign-root [data-hp-view]{
  display:none !important;
}
body.hp-ui-v2.hp-view-wizard .hp-redesign-root [data-hp-view~="wizard"],
body.hp-ui-v2.hp-view-leads .hp-redesign-root [data-hp-view~="leads"],
body.hp-ui-v2.hp-view-route .hp-redesign-root [data-hp-view~="route"],
body.hp-ui-v2.hp-view-photos .hp-redesign-root [data-hp-view~="photos"],
body.hp-ui-v2.hp-view-review .hp-redesign-root [data-hp-view~="review"],
body.hp-ui-v2.hp-view-renderreview .hp-redesign-root [data-hp-view~="renderreview"],
body.hp-ui-v2.hp-view-output .hp-redesign-root [data-hp-view~="output"],
body.hp-ui-v2.hp-view-settings .hp-redesign-root [data-hp-view~="settings"]{
  display:block !important;
}
body.hp-ui-v2 .card,
body.hp-ui-v2 .preview-panel,
body.hp-ui-v2 .done-banner,
body.hp-ui-v2 .elapsed-bar,
body.hp-ui-v2 .lead-review-panel,
body.hp-ui-v2 .review-summary{
  background:#fff;
  color:var(--hp-ink);
  border:1px solid var(--hp-line);
  border-radius:8px;
  box-shadow:none;
  backdrop-filter:none;
}
body.hp-ui-v2 .card{
  padding:16px;
}
body.hp-ui-v2 .card h2{
  color:#41556b;
  font-size:12px;
  letter-spacing:.08em;
}
body.hp-ui-v2 .section{
  margin-top:0;
}
body.hp-ui-v2 input,
body.hp-ui-v2 select,
body.hp-ui-v2 textarea{
  background:#fff;
  border:1px solid #cfdbe5;
  color:var(--hp-ink);
  border-radius:8px;
}
body.hp-ui-v2 input:focus,
body.hp-ui-v2 select:focus,
body.hp-ui-v2 textarea:focus{
  border-color:var(--hp-blue-2);
  box-shadow:0 0 0 3px rgba(31,95,139,.14);
}
body.hp-ui-v2 .mode-option span,
body.hp-ui-v2 .workflow-step,
body.hp-ui-v2 .path-row,
body.hp-ui-v2 .manual-item,
body.hp-ui-v2 .preset-option,
body.hp-ui-v2 .review-item,
body.hp-ui-v2 .review-go-card,
body.hp-ui-v2 .landing-preview-card,
body.hp-ui-v2 .copy-details{
  background:#f8fbfd;
  border-color:#d8e2ea;
  border-radius:8px;
}
body.hp-ui-v2 .mode-option strong,
body.hp-ui-v2 .preset-title,
body.hp-ui-v2 .workflow-step-title,
body.hp-ui-v2 .manual-item-title,
body.hp-ui-v2 .review-go-num,
body.hp-ui-v2 .crm-table td,
body.hp-ui-v2 .landing-preview-card strong,
body.hp-ui-v2 .step-title{
  color:var(--hp-ink);
}
body.hp-ui-v2 .mode-option small,
body.hp-ui-v2 .mode-note,
body.hp-ui-v2 .field-help,
body.hp-ui-v2 .toggle-hint,
body.hp-ui-v2 .path-row code,
body.hp-ui-v2 .crm-table th,
body.hp-ui-v2 .review-muted,
body.hp-ui-v2 .step-msg,
body.hp-ui-v2 .file-label{
  color:var(--hp-muted);
}
body.hp-ui-v2 .help-panel{
  background:#fff8f2;
  border-color:#f0d6c3;
  border-radius:8px;
}
body.hp-ui-v2 .help-panel strong{
  color:#8b4b24;
}
body.hp-ui-v2 .help-panel p{
  color:#6d5b50;
}
body.hp-ui-v2 .btn,
body.hp-ui-v2 .btn-sm,
body.hp-ui-v2 .review-start,
body.hp-ui-v2 .camera-save,
body.hp-ui-v2 .camera-nudges button,
body.hp-ui-v2 .review-action,
body.hp-ui-v2 .tab{
  border-radius:8px;
}
body.hp-ui-v2 .btn-primary{
  background:var(--hp-teal);
  box-shadow:0 10px 18px rgba(15,118,110,.16);
}
body.hp-ui-v2 .btn-primary:hover:not(:disabled){
  transform:none;
  background:#0b665f;
  box-shadow:0 12px 20px rgba(15,118,110,.2);
}
body.hp-ui-v2 .btn-copy,
body.hp-ui-v2 .camera-save,
body.hp-ui-v2 .camera-nudges button,
body.hp-ui-v2 .review-start{
  background:#edf7f6;
  color:var(--hp-teal);
  border-color:#b8d8d4;
}
body.hp-ui-v2 .badge{
  background:#e7f0f6;
  color:var(--hp-blue-2);
}
body.hp-ui-v2 .badge.ok{
  background:#e7f6f3;
  color:var(--hp-teal);
}
body.hp-ui-v2 .badge.warn,
body.hp-ui-v2 .preset-cost{
  color:var(--hp-amber);
}
body.hp-ui-v2 .log{
  background:#0f1b2a;
  color:#c4d2df;
  border-color:#21344b;
  border-radius:8px;
}
body.hp-ui-v2 #mapContainer,
body.hp-ui-v2 .leaflet-container{
  background:#dbe7ef;
}
body.hp-ui-v2 .leaflet-popup-content-wrapper,
body.hp-ui-v2 .leaflet-popup-tip{
  background:#fff;
  color:var(--hp-ink);
}
body.hp-ui-v2 .lead-review-empty{
  color:var(--hp-muted);
}
body.hp-ui-v2 .streetview-frame,
body.hp-ui-v2 .preview-item,
body.hp-ui-v2 .drop-zone{
  background:#eff4f8;
  border-color:#d8e2ea;
  border-radius:8px;
}
body.hp-ui-v2 .tab{
  background:#f1f6f9;
  color:#52677d;
  border-color:#d8e2ea;
}
body.hp-ui-v2 .tab.active{
  background:#eef8f6;
  color:var(--hp-teal);
  border-color:#b8d8d4;
}
body.hp-ui-v2 .step{
  background:#fff;
  border-color:#d8e2ea;
  border-radius:8px;
}
body.hp-ui-v2 .step.running{
  background:#eef8f6;
  border-color:#9dccca;
  animation:none;
}
body.hp-ui-v2 .step.done{
  border-color:#9dccca;
}
body.hp-ui-v2 .step-bar{
  background:#dfe9f0;
}
body.hp-ui-v2 .elapsed-value,
body.hp-ui-v2 .subtitle,
body.hp-ui-v2 .landing-preview-card a,
body.hp-ui-v2 .review-flyerinfo a{
  color:var(--hp-blue-2);
}
body.hp-ui-v2 .hp-hidden{
  display:none !important;
}
@media(max-width:1100px){
  .hp-step-rail{
    grid-template-columns:repeat(3,minmax(0,1fr));
  }
  .hp-overview-grid{
    grid-template-columns:1fr;
  }
  .hp-card-grid{
    grid-template-columns:1fr;
  }
  body.hp-ui-v2 .layout{
    grid-template-columns:1fr;
  }
}
@media(max-width:820px){
  .hp-shell{
    position:static;
    width:auto;
  }
  .hp-nav{
    grid-template-columns:repeat(3,minmax(0,1fr));
  }
  .hp-nav-btn{
    grid-template-columns:1fr;
    justify-items:center;
    text-align:center;
  }
  .hp-nav-count{
    display:none;
  }
  .hp-topbar,
  .hp-step-rail,
  .hp-overview,
  body.hp-ui-v2 .layout{
    margin-left:0;
  }
  .hp-topbar{
    position:static;
    grid-template-columns:1fr;
    padding:16px;
  }
  .hp-actions{
    justify-content:flex-start;
  }
  .hp-step-rail{
    grid-template-columns:1fr 1fr;
    padding:12px 16px 0;
  }
  .hp-overview,
  body.hp-ui-v2 .layout{
    padding:14px 16px 26px;
  }
}


/* Database Intelligence Dashboard v2 - design foundation */
:root{
  --db-bg:#0c1118;
  --db-panel:#121a26;
  --db-panel2:#0f1620;
  --db-line:rgba(255,255,255,.07);
  --db-ink:#e9eef5;
  --db-muted:#8b9bb0;
  --db-dim:#5c6b80;
  --db-accent:#e2a35c;
  --db-accent2:#d97a45;
  --db-blue:#5aa2e0;
  --db-green:#5fbe8f;
  --db-purple:#a98fe8;
  --db-red:#e07a6a;
  --db-glow:0 0 40px rgba(226,163,92,.14);
}
body.hp-ui-v2.hp-intelligence-theme{
  background:var(--db-bg);
  color:var(--db-ink);
  -webkit-font-smoothing:antialiased;
}
body.hp-ui-v2.hp-intelligence-theme .hp-shell{
  background:#0a0f16;
  border-right:1px solid var(--db-line);
  box-shadow:18px 0 50px rgba(0,0,0,.22);
}
body.hp-ui-v2.hp-intelligence-theme .hp-brand{
  border-bottom:1px solid var(--db-line);
}
body.hp-ui-v2.hp-intelligence-theme .hp-mark,
body.hp-ui-v2.hp-intelligence-theme .hp-brand .mark{
  background:linear-gradient(135deg,var(--db-accent),var(--db-accent2));
  color:#12100c;
}
body.hp-ui-v2.hp-intelligence-theme .hp-brand p,
body.hp-ui-v2.hp-intelligence-theme .hp-side-metric,
body.hp-ui-v2.hp-intelligence-theme .hp-title-sub{
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .hp-nav-btn{
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .hp-nav-btn:hover{
  color:var(--db-ink);
  background:rgba(255,255,255,.045);
}
body.hp-ui-v2.hp-intelligence-theme .hp-nav-btn.active{
  background:rgba(255,255,255,.075);
  color:var(--db-ink);
  box-shadow:inset 0 -2px 0 var(--db-accent), var(--db-glow);
}
body.hp-ui-v2.hp-intelligence-theme .hp-nav-ico,
body.hp-ui-v2.hp-intelligence-theme .hp-nav-btn.active .hp-nav-ico{
  background:rgba(226,163,92,.13);
  color:var(--db-accent);
}
body.hp-ui-v2.hp-intelligence-theme .hp-nav-count,
body.hp-ui-v2.hp-intelligence-theme .hp-nav-btn.active .hp-nav-count{
  background:rgba(226,163,92,.18);
  color:var(--db-accent);
}
body.hp-ui-v2.hp-intelligence-theme .hp-side-footer{
  border-top:1px solid var(--db-line);
}
body.hp-ui-v2.hp-intelligence-theme .hp-side-metric strong{
  color:var(--db-ink);
}
body.hp-ui-v2.hp-intelligence-theme .hp-topbar{
  background:rgba(12,17,24,.88);
  border-bottom:1px solid var(--db-line);
  backdrop-filter:blur(12px);
}
body.hp-ui-v2.hp-intelligence-theme .hp-title-kicker{
  color:var(--db-accent);
}
body.hp-ui-v2.hp-intelligence-theme .hp-title-main{
  color:var(--db-ink);
}
body.hp-ui-v2.hp-intelligence-theme .hp-chip{
  background:var(--db-panel);
  border:1px solid var(--db-line);
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .hp-chip b{
  color:var(--db-ink);
}
body.hp-ui-v2.hp-intelligence-theme .hp-primary-action,
body.hp-ui-v2.hp-intelligence-theme .btn-primary{
  background:linear-gradient(135deg,var(--db-accent),var(--db-accent2));
  color:#161006;
  border:0;
  box-shadow:var(--db-glow);
}
body.hp-ui-v2.hp-intelligence-theme .hp-primary-action:hover,
body.hp-ui-v2.hp-intelligence-theme .btn-primary:hover:not(:disabled){
  background:linear-gradient(135deg,#efb873,var(--db-accent2));
  color:#161006;
  box-shadow:0 0 48px rgba(226,163,92,.18);
}
body.hp-ui-v2.hp-intelligence-theme .hp-secondary-action,
body.hp-ui-v2.hp-intelligence-theme .btn,
body.hp-ui-v2.hp-intelligence-theme .btn-sm,
body.hp-ui-v2.hp-intelligence-theme .review-start{
  background:var(--db-panel);
  border:1px solid var(--db-line);
  color:var(--db-ink);
}
body.hp-ui-v2.hp-intelligence-theme .hp-secondary-action:hover,
body.hp-ui-v2.hp-intelligence-theme .btn:hover,
body.hp-ui-v2.hp-intelligence-theme .btn-sm:hover{
  background:rgba(255,255,255,.055);
}
.hp-demo-badge{
  display:flex;
  flex-direction:column;
  align-items:flex-end;
  gap:1px;
  min-width:168px;
}
.hp-demo-badge .b1{
  font-size:10.5px;
  font-weight:900;
  letter-spacing:.08em;
  color:#0c1118;
  background:var(--db-accent);
  border-radius:5px;
  padding:3px 9px;
}
.hp-demo-badge .b2{
  font-size:10px;
  color:var(--db-dim);
}
.hp-demo-guardrail{
  margin-left:272px;
  padding:8px 28px;
  background:rgba(226,163,92,.10);
  border-bottom:1px solid rgba(226,163,92,.22);
  color:#ffdcae;
  font-size:11.5px;
  letter-spacing:.01em;
}
body.hp-ui-v2.hp-intelligence-theme:not(.hp-demo-data) .hp-demo-guardrail,
body.hp-ui-v2.hp-intelligence-theme:not(.hp-demo-data) .hp-demo-badge{
  display:none !important;
}
body.hp-ui-v2.hp-intelligence-theme .hp-step-chip{
  background:var(--db-panel);
  border:1px solid var(--db-line);
  border-left:4px solid var(--db-blue);
  color:var(--db-ink);
  box-shadow:none;
}
body.hp-ui-v2.hp-intelligence-theme .hp-step-chip:hover{
  border-color:rgba(226,163,92,.35);
  box-shadow:var(--db-glow);
}
body.hp-ui-v2.hp-intelligence-theme .hp-step-chip.is-active{
  border-left-color:var(--db-accent);
  background:rgba(226,163,92,.08);
}
body.hp-ui-v2.hp-intelligence-theme .hp-step-chip span{
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .hp-command-panel,
body.hp-ui-v2.hp-intelligence-theme .hp-board-panel,
body.hp-ui-v2.hp-intelligence-theme .hp-overview-card,
body.hp-ui-v2.hp-intelligence-theme .card,
body.hp-ui-v2.hp-intelligence-theme .preview-panel,
body.hp-ui-v2.hp-intelligence-theme .done-banner,
body.hp-ui-v2.hp-intelligence-theme .elapsed-bar,
body.hp-ui-v2.hp-intelligence-theme .lead-review-panel,
body.hp-ui-v2.hp-intelligence-theme .review-summary{
  background:var(--db-panel);
  color:var(--db-ink);
  border:1px solid var(--db-line);
  border-radius:12px;
  box-shadow:none;
}
body.hp-ui-v2.hp-intelligence-theme .hp-command-head h2,
body.hp-ui-v2.hp-intelligence-theme .hp-overview-card h3,
body.hp-ui-v2.hp-intelligence-theme .hp-board-panel h2,
body.hp-ui-v2.hp-intelligence-theme .card h2{
  color:var(--db-ink);
}
body.hp-ui-v2.hp-intelligence-theme .hp-command-head p,
body.hp-ui-v2.hp-intelligence-theme .hp-overview-card p,
body.hp-ui-v2.hp-intelligence-theme .mode-note,
body.hp-ui-v2.hp-intelligence-theme .field-help,
body.hp-ui-v2.hp-intelligence-theme .toggle-hint,
body.hp-ui-v2.hp-intelligence-theme .path-row code,
body.hp-ui-v2.hp-intelligence-theme .lead-review-empty,
body.hp-ui-v2.hp-intelligence-theme .step-msg{
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .hp-status-pill{
  background:rgba(226,163,92,.14);
  color:var(--db-accent);
}
body.hp-ui-v2.hp-intelligence-theme .hp-overview-card{
  position:relative;
  overflow:hidden;
}
body.hp-ui-v2.hp-intelligence-theme .hp-overview-card::after,
body.hp-ui-v2.hp-intelligence-theme .kpi::after{
  content:"";
  position:absolute;
  right:-30px;
  top:-30px;
  width:110px;
  height:110px;
  border-radius:99px;
  background:radial-gradient(circle,rgba(226,163,92,.10),transparent 70%);
  pointer-events:none;
}
body.hp-ui-v2.hp-intelligence-theme .hp-card-stat strong,
body.hp-ui-v2.hp-intelligence-theme .kpi .v{
  color:var(--db-ink);
  font-size:30px;
  font-weight:800;
  letter-spacing:-.02em;
}
body.hp-ui-v2.hp-intelligence-theme .hp-card-stat span,
body.hp-ui-v2.hp-intelligence-theme .kpi label{
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .hp-progress-track,
body.hp-ui-v2.hp-intelligence-theme .funnel-bar-bg,
body.hp-ui-v2.hp-intelligence-theme .step-bar,
body.hp-ui-v2.hp-intelligence-theme .scorebar{
  background:rgba(255,255,255,.08);
}
body.hp-ui-v2.hp-intelligence-theme .hp-progress-fill,
body.hp-ui-v2.hp-intelligence-theme .funnel-bar-fill,
body.hp-ui-v2.hp-intelligence-theme .step-bar-fill,
body.hp-ui-v2.hp-intelligence-theme .scorebar i{
  background:linear-gradient(90deg,var(--db-accent2),var(--db-accent));
}
body.hp-ui-v2.hp-intelligence-theme input,
body.hp-ui-v2.hp-intelligence-theme select,
body.hp-ui-v2.hp-intelligence-theme textarea{
  background:var(--db-panel2);
  color:var(--db-ink);
  border:1px solid var(--db-line);
}
body.hp-ui-v2.hp-intelligence-theme input:focus,
body.hp-ui-v2.hp-intelligence-theme select:focus,
body.hp-ui-v2.hp-intelligence-theme textarea:focus{
  border-color:rgba(226,163,92,.58);
  box-shadow:0 0 0 3px rgba(226,163,92,.12);
}
body.hp-ui-v2.hp-intelligence-theme .mode-option span,
body.hp-ui-v2.hp-intelligence-theme .workflow-step,
body.hp-ui-v2.hp-intelligence-theme .path-row,
body.hp-ui-v2.hp-intelligence-theme .manual-item,
body.hp-ui-v2.hp-intelligence-theme .preset-option,
body.hp-ui-v2.hp-intelligence-theme .review-item,
body.hp-ui-v2.hp-intelligence-theme .review-go-card,
body.hp-ui-v2.hp-intelligence-theme .landing-preview-card,
body.hp-ui-v2.hp-intelligence-theme .copy-details,
body.hp-ui-v2.hp-intelligence-theme .file-list li,
body.hp-ui-v2.hp-intelligence-theme .review-list-col li{
  background:var(--db-panel2);
  border-color:var(--db-line);
  border-radius:9px;
}
body.hp-ui-v2.hp-intelligence-theme .mode-option input:checked+span,
body.hp-ui-v2.hp-intelligence-theme .preset-option:hover{
  background:rgba(226,163,92,.10);
  border-color:rgba(226,163,92,.46);
  box-shadow:0 0 0 3px rgba(226,163,92,.08);
}
body.hp-ui-v2.hp-intelligence-theme .mode-option strong,
body.hp-ui-v2.hp-intelligence-theme .preset-title,
body.hp-ui-v2.hp-intelligence-theme .workflow-step-title,
body.hp-ui-v2.hp-intelligence-theme .manual-item-title,
body.hp-ui-v2.hp-intelligence-theme .review-go-num,
body.hp-ui-v2.hp-intelligence-theme .crm-table td,
body.hp-ui-v2.hp-intelligence-theme .landing-preview-card strong,
body.hp-ui-v2.hp-intelligence-theme .step-title,
body.hp-ui-v2.hp-intelligence-theme .toggle-label{
  color:var(--db-ink);
}
body.hp-ui-v2.hp-intelligence-theme .help-panel{
  background:rgba(226,163,92,.08);
  border-color:rgba(226,163,92,.22);
}
body.hp-ui-v2.hp-intelligence-theme .help-panel strong,
body.hp-ui-v2.hp-intelligence-theme .badge.warn,
body.hp-ui-v2.hp-intelligence-theme .preset-cost{
  color:var(--db-accent);
}
body.hp-ui-v2.hp-intelligence-theme .help-panel p{
  color:#bba995;
}
body.hp-ui-v2.hp-intelligence-theme .badge,
body.hp-ui-v2.hp-intelligence-theme .review-chip{
  background:rgba(226,163,92,.14);
  color:var(--db-accent);
  border-radius:6px;
}
body.hp-ui-v2.hp-intelligence-theme .badge.ok{
  background:rgba(95,190,143,.16);
  color:var(--db-green);
}
body.hp-ui-v2.hp-intelligence-theme .btn-copy,
body.hp-ui-v2.hp-intelligence-theme .camera-save,
body.hp-ui-v2.hp-intelligence-theme .camera-nudges button{
  background:rgba(226,163,92,.10);
  color:var(--db-accent);
  border-color:rgba(226,163,92,.30);
}
body.hp-ui-v2.hp-intelligence-theme .log{
  background:#0a0f16;
  color:#b8c6d4;
  border-color:var(--db-line);
}
body.hp-ui-v2.hp-intelligence-theme .crm-table{
  width:100%;
  border-collapse:collapse;
  font-size:12.5px;
}
body.hp-ui-v2.hp-intelligence-theme .crm-table th{
  position:sticky;
  top:0;
  background:var(--db-panel2);
  color:var(--db-muted);
  font-size:10.5px;
  text-transform:uppercase;
  letter-spacing:.07em;
  padding:11px 13px;
  border-bottom:1px solid var(--db-line);
  white-space:nowrap;
}
body.hp-ui-v2.hp-intelligence-theme .crm-table td{
  padding:10px 13px;
  border-bottom:1px solid var(--db-line);
  white-space:nowrap;
}
body.hp-ui-v2.hp-intelligence-theme .crm-table tr:hover{
  background:rgba(255,255,255,.035);
}
body.hp-ui-v2.hp-intelligence-theme .crm-status,
body.hp-ui-v2.hp-intelligence-theme .kbadge{
  display:inline-block;
  min-width:30px;
  text-align:center;
  font-size:10.5px;
  font-weight:900;
  border-radius:6px;
  padding:3px 7px;
}
body.hp-ui-v2.hp-intelligence-theme .crm-status.gegenereerd,
body.hp-ui-v2.hp-intelligence-theme .crm-status.geflyerd,
body.hp-ui-v2.hp-intelligence-theme .kA{
  background:rgba(90,162,224,.16);
  color:var(--db-blue);
}
body.hp-ui-v2.hp-intelligence-theme .crm-status.gescand,
body.hp-ui-v2.hp-intelligence-theme .kB{
  background:rgba(226,163,92,.14);
  color:var(--db-accent);
}
body.hp-ui-v2.hp-intelligence-theme .crm-status.contact,
body.hp-ui-v2.hp-intelligence-theme .kAp{
  background:rgba(95,190,143,.16);
  color:var(--db-green);
}
body.hp-ui-v2.hp-intelligence-theme .crm-status.afspraak,
body.hp-ui-v2.hp-intelligence-theme .crm-status.klant{
  background:rgba(95,190,143,.22);
  color:var(--db-green);
}
body.hp-ui-v2.hp-intelligence-theme .crm-status.afgewezen,
body.hp-ui-v2.hp-intelligence-theme .kC,
body.hp-ui-v2.hp-intelligence-theme .kD{
  background:rgba(139,155,176,.13);
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .sdot{
  display:inline-flex;
  align-items:center;
  gap:6px;
  font-size:11.5px;
  color:var(--db-muted);
}
body.hp-ui-v2.hp-intelligence-theme .sdot i{
  width:7px;
  height:7px;
  border-radius:99px;
  display:inline-block;
}
body.hp-ui-v2.hp-intelligence-theme #mapContainer,
body.hp-ui-v2.hp-intelligence-theme .streetview-frame,
body.hp-ui-v2.hp-intelligence-theme .preview-item,
body.hp-ui-v2.hp-intelligence-theme .drop-zone{
  background:#0a0f16;
  border-color:var(--db-line);
}
body.hp-ui-v2.hp-intelligence-theme .leaflet-popup-content-wrapper,
body.hp-ui-v2.hp-intelligence-theme .leaflet-popup-tip{
  background:#141c28;
  color:var(--db-ink);
  border:1px solid var(--db-line);
}
body.hp-ui-v2.hp-intelligence-theme .tab{
  background:var(--db-panel2);
  color:var(--db-muted);
  border-color:var(--db-line);
}
body.hp-ui-v2.hp-intelligence-theme .tab:hover,
body.hp-ui-v2.hp-intelligence-theme .tab.active{
  background:rgba(226,163,92,.12);
  color:var(--db-accent);
  border-color:rgba(226,163,92,.38);
}
@media(max-width:820px){
  .hp-demo-guardrail{
    margin-left:0;
    padding:8px 16px;
  }
  .hp-demo-badge{
    align-items:flex-start;
  }
}


/* Database-dashboard v2 complete intelligence workspace */
body.hp-ui-v2.hp-view-intelligence .layout,
body.hp-ui-v2.hp-view-intelligence #hpStepRail{
  display:none !important;
}
body.hp-ui-v2.hp-view-intelligence .hp-redesign-root [data-hp-view~="intelligence"]{
  display:block !important;
}
body.hp-ui-v2.hp-view-intelligence .hp-topbar{
  border-bottom-color:rgba(226,163,92,.22);
}
.hp-intel-wrap{
  margin-left:272px;
  padding:22px 28px 48px;
}
.intel-head{
  display:flex;
  justify-content:space-between;
  align-items:flex-end;
  gap:18px;
  margin-bottom:16px;
}
.intel-head h2{
  font-size:22px;
  letter-spacing:-.015em;
  margin:0;
  color:var(--db-ink);
}
.intel-head p{
  color:var(--db-muted);
  margin-top:4px;
  font-size:13px;
}
.intel-actions{
  display:flex;
  gap:8px;
  align-items:center;
  flex-wrap:wrap;
  justify-content:flex-end;
}
.intel-toggle{
  display:inline-flex;
  align-items:center;
  gap:8px;
  min-height:36px;
  padding:0 10px;
  border:1px solid var(--db-line);
  border-radius:9px;
  background:var(--db-panel);
  color:var(--db-muted);
  font-size:12px;
  font-weight:800;
}
.intel-toggle input{
  width:16px;
  height:16px;
  accent-color:var(--db-accent);
}
.intel-tabs{
  display:flex;
  gap:5px;
  margin-bottom:14px;
  flex-wrap:wrap;
}
.intel-tabs button{
  border:0;
  background:transparent;
  color:var(--db-muted);
  font:inherit;
  font-weight:800;
  font-size:13px;
  padding:8px 14px;
  border-radius:8px;
  cursor:pointer;
}
.intel-tabs button:hover{
  color:var(--db-ink);
  background:rgba(255,255,255,.04);
}
.intel-tabs button.active{
  color:var(--db-ink);
  background:rgba(255,255,255,.075);
  box-shadow:inset 0 -2px 0 var(--db-accent);
}
.intel-view{display:none}
.intel-view.active{display:block}
.intel-grid{display:grid;gap:14px}
.intel-g4{grid-template-columns:repeat(4,1fr)}
.intel-g3{grid-template-columns:repeat(3,1fr)}
.intel-g2-1{grid-template-columns:2fr 1fr}
.intel-card{
  background:var(--db-panel);
  border:1px solid var(--db-line);
  border-radius:12px;
  color:var(--db-ink);
}
.intel-pad{padding:18px}
.intel-kpi{
  position:relative;
  overflow:hidden;
  padding:16px 18px;
}
.intel-kpi::after{
  content:"";
  position:absolute;
  right:-30px;
  top:-30px;
  width:110px;
  height:110px;
  border-radius:99px;
  background:radial-gradient(circle,rgba(226,163,92,.10),transparent 70%);
}
.intel-kpi label{
  font-size:10.5px;
  font-weight:900;
  letter-spacing:.09em;
  text-transform:uppercase;
  color:var(--db-muted);
}
.intel-kpi .v{
  font-size:30px;
  font-weight:850;
  letter-spacing:-.02em;
  margin:4px 0 2px;
  font-variant-numeric:tabular-nums;
}
.intel-kpi .d{
  font-size:11.5px;
  color:var(--db-muted);
}
.intel-kpi .d em{color:var(--db-green);font-style:normal;font-weight:800}
.intel-cardhead{
  display:flex;
  align-items:baseline;
  justify-content:space-between;
  gap:12px;
  padding:16px 18px 0;
}
.intel-cardhead h3{font-size:13.5px;margin:0;color:var(--db-ink)}
.intel-cardhead span{font-size:11px;color:var(--db-dim)}
.intel-chartbox{position:relative;height:230px;padding:12px 14px 14px}
.intel-footnote{padding:0 18px 14px;font-size:10.5px;color:var(--db-dim)}
.intel-toolrow{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
.intel-search{
  flex:1;
  min-width:220px;
  display:flex;
  align-items:center;
  gap:8px;
  background:var(--db-panel);
  border:1px solid var(--db-line);
  border-radius:9px;
  padding:9px 12px;
}
.intel-search input{
  flex:1;
  border:0 !important;
  background:none !important;
  color:var(--db-ink) !important;
  font:inherit;
  outline:none;
  padding:0;
}
.intel-fchip{
  border:1px solid var(--db-line);
  background:var(--db-panel);
  color:var(--db-muted);
  font:inherit;
  font-size:12px;
  font-weight:800;
  border-radius:99px;
  padding:7px 13px;
  cursor:pointer;
}
.intel-fchip.on{
  background:rgba(226,163,92,.14);
  border-color:rgba(226,163,92,.50);
  color:var(--db-accent);
}
.intel-select{
  border:1px solid var(--db-line);
  background:var(--db-panel);
  color:var(--db-ink);
  font:inherit;
  font-size:12.5px;
  border-radius:9px;
  padding:8px 10px;
  width:auto;
}
.intel-dbgrid{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:14px;align-items:start}
.intel-tablewrap{overflow:auto;max-height:600px;border-radius:12px}
.intel-table{width:100%;border-collapse:collapse;font-size:12.5px}
.intel-table th{
  position:sticky;
  top:0;
  background:var(--db-panel2);
  color:var(--db-muted);
  font-size:10.5px;
  text-transform:uppercase;
  letter-spacing:.07em;
  text-align:left;
  padding:11px 13px;
  border-bottom:1px solid var(--db-line);
  cursor:pointer;
  white-space:nowrap;
}
.intel-table td{padding:10px 13px;border-bottom:1px solid var(--db-line);white-space:nowrap}
.intel-table tr{cursor:pointer}
.intel-table tr:hover{background:rgba(255,255,255,.035)}
.intel-table tr.sel{background:rgba(226,163,92,.08);box-shadow:inset 3px 0 0 var(--db-accent)}
.intel-pager{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 14px;border-top:1px solid var(--db-line);color:var(--db-muted);font-size:12px}
.kbadge{display:inline-block;min-width:30px;text-align:center;font-size:10.5px;font-weight:900;border-radius:6px;padding:3px 7px}
.kAp{background:rgba(95,190,143,.16);color:var(--db-green)}
.kA{background:rgba(90,162,224,.16);color:var(--db-blue)}
.kB{background:rgba(226,163,92,.14);color:var(--db-accent)}
.kC,.kD,.kLEAD,.kMAN{background:rgba(139,155,176,.13);color:var(--db-muted)}
.scorebar{display:inline-block;width:54px;height:5px;border-radius:99px;background:rgba(255,255,255,.08);vertical-align:2px;margin-right:7px;overflow:hidden}
.scorebar i{display:block;height:100%;background:linear-gradient(90deg,var(--db-accent2),var(--db-accent))}
.sdot{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;color:var(--db-muted)}
.sdot i{width:7px;height:7px;border-radius:99px;display:inline-block}
.drawer{position:sticky;top:90px}
.drawer .intel-card{max-height:calc(100vh - 120px);overflow:auto}
.dr-empty{padding:44px 20px;text-align:center;color:var(--db-dim);font-size:12.5px}
.dr-hero{padding:16px 18px 14px;border-bottom:1px solid var(--db-line);background:linear-gradient(180deg,rgba(226,163,92,.07),transparent)}
.dr-hero h3{font-size:15px;letter-spacing:-.01em;margin:0;color:var(--db-ink)}
.dr-hero .meta{font-size:11.5px;color:var(--db-muted);margin-top:3px}
.dr-render{margin:14px 18px 0;height:120px;border-radius:9px;background:linear-gradient(120deg,#c9b8a4 40%,#7d8b99);position:relative;overflow:hidden}
.dr-render img{width:100%;height:100%;object-fit:cover;display:block}
.dr-render::after{content:"render";position:absolute;right:8px;bottom:6px;font-size:9px;font-weight:800;letter-spacing:.06em;color:rgba(255,255,255,.85);background:rgba(12,17,24,.55);padding:2px 7px;border-radius:5px}
.dr-sec{padding:14px 18px;border-bottom:1px solid var(--db-line)}
.dr-sec h4{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--db-muted);margin:0 0 10px}
.mrow{display:grid;grid-template-columns:110px 1fr 38px;gap:9px;align-items:center;margin-bottom:8px;font-size:11.5px;color:var(--db-muted)}
.mrow .bar{height:6px;border-radius:99px;background:rgba(255,255,255,.07);overflow:hidden}
.mrow .bar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--db-blue),var(--db-green))}
.mrow b{color:var(--db-ink);text-align:right;font-size:11.5px}
.prov{display:flex;justify-content:space-between;gap:10px;font-size:11.5px;padding:7px 0;border-bottom:1px dashed rgba(255,255,255,.06)}
.prov b{font-weight:750;color:var(--db-ink)}
.prov span{color:var(--db-dim);font-size:10.5px;text-align:right}
.tl{position:relative;padding-left:16px}
.tl::before{content:"";position:absolute;left:4px;top:4px;bottom:4px;width:1.5px;background:rgba(255,255,255,.09)}
.tlitem{position:relative;margin-bottom:10px;font-size:11.5px;color:var(--db-muted)}
.tlitem::before{content:"";position:absolute;left:-15.5px;top:4px;width:8px;height:8px;border-radius:99px;background:var(--db-accent);box-shadow:0 0 8px rgba(226,163,92,.6)}
.tlitem b{display:block;color:var(--db-ink)}
.dr-cta{display:flex;gap:8px;padding:14px 18px}
.mapshell{position:relative;height:640px;border-radius:12px;overflow:hidden;border:1px solid var(--db-line);background:#0a0f16}
#intelMap{position:absolute;inset:0;background:#0a0f16}
.maplegend{position:absolute;left:14px;bottom:14px;z-index:800;background:rgba(12,17,24,.88);backdrop-filter:blur(8px);border:1px solid var(--db-line);border-radius:10px;padding:12px 14px;font-size:11.5px;color:var(--db-muted)}
.maplegend b{display:block;color:var(--db-ink);font-size:11px;text-transform:uppercase;letter-spacing:.07em;margin-bottom:7px}
.maplegend .row{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.maplegend i{width:10px;height:10px;border-radius:99px;display:inline-block}
.mapstats{position:absolute;right:14px;top:14px;z-index:800;display:grid;gap:8px}
.mapstat{background:rgba(12,17,24,.88);backdrop-filter:blur(8px);border:1px solid var(--db-line);border-radius:10px;padding:10px 14px;min-width:150px}
.mapstat label{font-size:9.5px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:var(--db-muted)}
.mapstat .v{font-size:19px;font-weight:850;color:var(--db-ink)}
.mcluster{background:rgba(226,163,92,.22);border:2px solid var(--db-accent);color:#ffdcae;border-radius:99px;display:grid;place-items:center;font-weight:900;font-size:12px;box-shadow:0 0 18px rgba(226,163,92,.35)}
.brainshell{position:relative;height:660px;border-radius:12px;overflow:hidden;border:1px solid var(--db-line);background:radial-gradient(1200px 600px at 60% 40%,#101a29 0%,#0a0f16 70%)}
#intelBrain{position:absolute;inset:0;cursor:grab;width:100%;height:100%}
#intelBrain.grabbing{cursor:grabbing}
.brainui{position:absolute;left:14px;top:14px;z-index:5;display:flex;gap:8px}
.brainui .hp-secondary-action{background:rgba(12,17,24,.85);backdrop-filter:blur(8px)}
.brainlegend{position:absolute;left:14px;bottom:14px;z-index:5;background:rgba(12,17,24,.85);backdrop-filter:blur(8px);border:1px solid var(--db-line);border-radius:10px;padding:12px 14px;font-size:11.5px;color:var(--db-muted)}
.brainlegend .row{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.brainlegend i{width:9px;height:9px;border-radius:99px}
.braininfo{position:absolute;right:14px;top:14px;z-index:5;width:270px;background:rgba(12,17,24,.9);backdrop-filter:blur(10px);border:1px solid var(--db-line);border-radius:12px;padding:15px;font-size:12px;color:var(--db-muted);display:none}
.braininfo.show{display:block}
.braininfo h4{color:var(--db-ink);font-size:13px;margin-bottom:5px}
.braininfo .tag{display:inline-block;font-size:9.5px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;border-radius:5px;padding:2px 7px;margin-bottom:8px;background:rgba(226,163,92,.14);color:var(--db-accent)}
.intel-footer{margin-top:24px;font-size:10.5px;color:var(--db-dim);display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap}
body.hp-presentation-mode #costCard,
body.hp-presentation-mode #startBtn,
body.hp-presentation-mode #cancelBtn,
body.hp-presentation-mode #clientGenerateBtn,
body.hp-presentation-mode #manualRunBtn,
body.hp-presentation-mode .review-start,
body.hp-presentation-mode [onclick^="generateClientCampaign"],
body.hp-presentation-mode [onclick^="manualRun"],
body.hp-presentation-mode [onclick^="startPipeline"]{
  display:none !important;
}
@media(max-width:1100px){
  .intel-g4{grid-template-columns:1fr 1fr}
  .intel-g3,.intel-g2-1,.intel-dbgrid{grid-template-columns:1fr}
  .drawer{position:static}
}
@media(max-width:820px){
  .hp-intel-wrap{margin-left:0;padding:14px 16px 28px}
  .intel-head{display:grid}
  .intel-actions{justify-content:flex-start}
  .intel-g4{grid-template-columns:1fr}
}

/* FacadePilot field-capture workflow upgrade */
:root{
  --hp-rail-collapsed:92px;
  --hp-rail-open:232px;
}
body.hp-ui-v2 .hp-shell{
  width:var(--hp-rail-collapsed);
  transition:width .18s ease, box-shadow .18s ease;
  overflow:hidden;
}
body.hp-ui-v2 .hp-shell:hover,
body.hp-ui-v2 .hp-shell:focus-within{
  width:var(--hp-rail-open);
  box-shadow:28px 0 70px rgba(0,0,0,.38);
}
body.hp-ui-v2 .hp-brand{
  padding:14px 12px 12px;
}
body.hp-ui-v2 .hp-brand-row{
  justify-content:flex-start;
}
body.hp-ui-v2 .hp-mark{
  width:48px;
  height:48px;
  flex:0 0 48px;
}
body.hp-ui-v2 .hp-brand h1,
body.hp-ui-v2 .hp-brand p,
body.hp-ui-v2 .hp-nav-label,
body.hp-ui-v2 .hp-side-footer{
  opacity:0;
  pointer-events:none;
  transition:opacity .14s ease;
}
body.hp-ui-v2 .hp-shell:hover .hp-brand h1,
body.hp-ui-v2 .hp-shell:hover .hp-brand p,
body.hp-ui-v2 .hp-shell:hover .hp-nav-label,
body.hp-ui-v2 .hp-shell:hover .hp-side-footer,
body.hp-ui-v2 .hp-shell:focus-within .hp-brand h1,
body.hp-ui-v2 .hp-shell:focus-within .hp-brand p,
body.hp-ui-v2 .hp-shell:focus-within .hp-nav-label,
body.hp-ui-v2 .hp-shell:focus-within .hp-side-footer{
  opacity:1;
  pointer-events:auto;
}
body.hp-ui-v2 .hp-nav{
  padding:14px 10px 10px;
}
body.hp-ui-v2 .hp-nav-btn{
  position:relative;
  grid-template-columns:34px;
  justify-content:center;
  padding:8px 7px;
  min-height:48px;
}
body.hp-ui-v2 .hp-shell:hover .hp-nav-btn,
body.hp-ui-v2 .hp-shell:focus-within .hp-nav-btn{
  grid-template-columns:34px 1fr auto;
  justify-content:stretch;
}
body.hp-ui-v2 .hp-nav-ico{
  width:34px;
  height:34px;
}
body.hp-ui-v2 .hp-nav-count{
  position:absolute;
  right:8px;
}
body.hp-ui-v2 .hp-shell:hover .hp-nav-count,
body.hp-ui-v2 .hp-shell:focus-within .hp-nav-count{
  position:static;
}
body.hp-ui-v2 .hp-topbar,
body.hp-ui-v2 .hp-step-rail,
body.hp-ui-v2 .hp-overview,
body.hp-ui-v2 .layout,
body.hp-ui-v2 .hp-intel-wrap,
body.hp-ui-v2 .hp-demo-guardrail{
  margin-left:var(--hp-rail-collapsed);
}
body.hp-ui-v2 .layout{
  grid-template-columns:minmax(300px,360px) minmax(0,1fr);
}
body.hp-ui-v2.hp-view-leads .layout{
  grid-template-columns:minmax(300px,360px) minmax(0,1fr);
}
body.hp-ui-v2.hp-view-leads.hp-target-collapsed .layout{
  grid-template-columns:0 minmax(0,1fr);
  gap:0;
}
body.hp-ui-v2.hp-view-route .layout,
body.hp-ui-v2.hp-view-photos .layout,
body.hp-ui-v2.hp-view-renderreview .layout{
  grid-template-columns:0 minmax(0,1fr);
  gap:0;
}
#hpTargetDrawer{
  min-width:0;
  transition:opacity .16s ease, transform .16s ease;
}
body.hp-ui-v2.hp-view-leads.hp-target-collapsed #hpTargetDrawer{
  opacity:0;
  overflow:hidden;
  pointer-events:none;
  transform:translateX(-12px);
}
body.hp-ui-v2.hp-view-route #hpTargetDrawer,
body.hp-ui-v2.hp-view-photos #hpTargetDrawer,
body.hp-ui-v2.hp-view-renderreview #hpTargetDrawer{
  display:none;
}
.hp-map-tools{
  display:flex;
  align-items:center;
  gap:8px;
  flex-wrap:wrap;
}
.map-review-layout{
  grid-template-columns:minmax(540px,1fr) minmax(360px,430px);
}
body.hp-ui-v2.hp-view-leads.hp-target-collapsed .map-review-layout{
  grid-template-columns:minmax(620px,1fr) minmax(390px,480px);
}
.address-workbench,
.field-route-card,
.photo-intake-card{
  margin-top:14px;
  border:1px solid var(--db-line);
  border-radius:12px;
  background:var(--db-panel2);
  padding:14px;
}
.address-workbench-head,
.field-route-head,
.photo-intake-head{
  display:flex;
  justify-content:space-between;
  gap:14px;
  align-items:flex-start;
  margin-bottom:12px;
}
.address-workbench-head h3,
.field-route-head h3,
.photo-intake-head h3{
  margin:0 0 4px;
  color:var(--db-ink);
  font-size:15px;
}
.address-workbench-head p,
.field-route-head p,
.photo-intake-head p{
  margin:0;
  color:var(--db-muted);
  font-size:12px;
  line-height:1.45;
}
.address-actions,
.field-route-actions{
  display:flex;
  gap:8px;
  align-items:center;
  flex-wrap:wrap;
}
.address-list{
  display:grid;
  gap:10px;
  max-height:640px;
  overflow:auto;
  padding-right:4px;
}
.lead-address-row{
  display:grid;
  grid-template-columns:210px minmax(0,1fr) auto;
  gap:12px;
  align-items:stretch;
  border:1px solid var(--db-line);
  border-radius:10px;
  background:#0a0f16;
  padding:10px;
}
.lead-address-row.is-selected{
  border-color:rgba(95,190,143,.55);
  box-shadow:0 0 0 3px rgba(95,190,143,.08);
}
.streetview-mini{
  min-height:118px;
  border:1px solid var(--db-line);
  border-radius:8px;
  overflow:hidden;
  background:#060a10;
  display:grid;
  place-items:center;
}
.streetview-mini iframe{
  width:100%;
  height:100%;
  min-height:118px;
  border:0;
  display:block;
}
.streetview-mini button{
  border:1px solid rgba(226,163,92,.28);
  background:rgba(226,163,92,.10);
  color:var(--db-accent);
  border-radius:8px;
  min-height:36px;
  padding:0 12px;
  font:inherit;
  font-weight:850;
  cursor:pointer;
}
.lead-address-main strong,
.route-stop strong,
.photo-row strong{
  display:block;
  color:var(--db-ink);
  font-size:14px;
  line-height:1.25;
}
.lead-address-main span,
.route-stop span,
.photo-row span{
  display:block;
  color:var(--db-muted);
  font-size:11.5px;
  line-height:1.45;
  margin-top:3px;
}
.lead-address-badges{
  display:flex;
  gap:6px;
  flex-wrap:wrap;
  margin-top:8px;
}
.lead-address-badges b{
  border-radius:999px;
  padding:3px 8px;
  background:rgba(255,255,255,.06);
  color:var(--db-muted);
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.04em;
}
.lead-address-buttons{
  display:grid;
  gap:7px;
  align-content:center;
}
.lead-address-buttons button,
.photo-row button,
.field-route-actions button,
.address-actions button{
  min-height:34px;
  border-radius:8px;
  border:1px solid var(--db-line);
  background:var(--db-panel);
  color:var(--db-ink);
  font:inherit;
  font-size:12px;
  font-weight:850;
  padding:0 10px;
  cursor:pointer;
}
.lead-address-buttons button.primary,
.field-route-actions button.primary,
.address-actions button.primary{
  background:linear-gradient(135deg,var(--db-accent),var(--db-accent2));
  color:#161006;
  border:0;
}
.address-list-more{
  width:100%;
  margin-top:10px;
}
.route-summary{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:10px;
  margin:12px 0;
}
.route-summary div{
  border:1px solid var(--db-line);
  border-radius:10px;
  background:#0a0f16;
  padding:11px;
}
.route-summary span{
  display:block;
  color:var(--db-muted);
  font-size:10.5px;
  text-transform:uppercase;
  letter-spacing:.06em;
}
.route-summary strong{
  display:block;
  margin-top:5px;
  color:var(--db-ink);
  font-size:18px;
}
.route-list,
.photo-list{
  display:grid;
  gap:8px;
}
.route-stop,
.photo-row{
  display:grid;
  grid-template-columns:44px minmax(0,1fr) auto;
  gap:10px;
  align-items:center;
  border:1px solid var(--db-line);
  border-radius:10px;
  background:#0a0f16;
  padding:10px;
}
.route-stop i,
.photo-row i{
  width:34px;
  height:34px;
  border-radius:99px;
  display:grid;
  place-items:center;
  background:rgba(226,163,92,.14);
  color:var(--db-accent);
  font-style:normal;
  font-weight:900;
}
.photo-drop{
  border:1px dashed rgba(226,163,92,.34);
  background:rgba(226,163,92,.07);
  color:var(--db-accent);
  border-radius:8px;
  padding:8px 10px;
  font-size:12px;
  font-weight:850;
}
.photo-drop input{
  max-width:190px;
  font-size:11px;
}
.photo-ready{
  color:var(--db-green) !important;
}
.pipeline-gate-note{
  margin-top:12px;
  border:1px solid rgba(95,190,143,.24);
  border-radius:10px;
  background:rgba(95,190,143,.08);
  color:#bfe5cf;
  padding:11px 12px;
  font-size:12px;
  line-height:1.45;
}
@media(max-width:1180px){
  .map-review-layout,
  body.hp-ui-v2.hp-view-leads.hp-target-collapsed .map-review-layout,
  .lead-address-row{
    grid-template-columns:1fr;
  }
  .route-summary{
    grid-template-columns:1fr 1fr;
  }
}
@media(max-width:820px){
  body.hp-ui-v2 .hp-shell{
    width:auto;
    overflow:visible;
  }
  body.hp-ui-v2 .hp-brand h1,
  body.hp-ui-v2 .hp-brand p,
  body.hp-ui-v2 .hp-nav-label,
  body.hp-ui-v2 .hp-side-footer{
    opacity:1;
    pointer-events:auto;
  }
  body.hp-ui-v2 .hp-topbar,
  body.hp-ui-v2 .hp-step-rail,
  body.hp-ui-v2 .hp-overview,
  body.hp-ui-v2 .layout,
  body.hp-ui-v2 .hp-intel-wrap,
  body.hp-ui-v2 .hp-demo-guardrail{
    margin-left:0;
  }
}

</style>
</head>
<body>
<div class="container hp-redesign-root">


<section id="hpShell" class="hp-shell" aria-label="HomePilot campagne-navigatie">
  <div class="hp-brand">
    <div class="hp-brand-row">
      <div class="hp-mark">HP</div>
      <div>
        <h1>HomePilot</h1>
        <p>Campaign cockpit</p>
      </div>
    </div>
  </div>
  <nav class="hp-nav" aria-label="Werkruimtes">
    <button class="hp-nav-btn active" type="button" data-hp-view-button="campaigns"><span class="hp-nav-ico">OV</span><span class="hp-nav-label">Campagnes</span><span class="hp-nav-count" id="hpCampaignCount">1</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="wizard"><span class="hp-nav-ico">WZ</span><span class="hp-nav-label">Wizard</span><span class="hp-nav-count">6</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="leads"><span class="hp-nav-ico">LD</span><span class="hp-nav-label">Leads & kaart</span><span class="hp-nav-count" id="hpLeadCount">0</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="route"><span class="hp-nav-ico">RT</span><span class="hp-nav-label">Routefoto's</span><span class="hp-nav-count" id="hpRouteCount">0</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="photos"><span class="hp-nav-ico">FO</span><span class="hp-nav-label">Foto's koppelen</span><span class="hp-nav-count" id="hpPhotoCount">0</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="review"><span class="hp-nav-ico">RV</span><span class="hp-nav-label">Review-inbox</span><span class="hp-nav-count" id="hpReviewCount">0</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="renderreview"><span class="hp-nav-ico">RR</span><span class="hp-nav-label">Render review</span><span class="hp-nav-count" id="hpRenderReviewCount">0</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="output"><span class="hp-nav-ico">OP</span><span class="hp-nav-label">Output</span><span class="hp-nav-count" id="hpOutputCount">0</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="intelligence"><span class="hp-nav-ico">DB</span><span class="hp-nav-label">Intelligence</span><span class="hp-nav-count" id="hpIntelCount">0</span></button>
    <button class="hp-nav-btn" type="button" data-hp-view-button="settings"><span class="hp-nav-ico">IN</span><span class="hp-nav-label">Instellingen</span><span class="hp-nav-count">OK</span></button>
  </nav>
  <div class="hp-side-footer">
    <div class="hp-side-metric"><span>Klant</span><strong id="hpSideClient">Nog kiezen</strong></div>
    <div class="hp-side-metric"><span>Brand</span><strong id="hpSideBrand">FacadePilot</strong></div>
    <div class="hp-side-metric"><span>Poort</span><strong id="hpSidePort">9303</strong></div>
  </div>
</section>

<section id="hpTopbar" class="hp-topbar">
  <div>
    <div class="hp-title-kicker" id="hpWorkspaceKicker">Campagnes</div>
    <div class="hp-title-main" id="hpWorkspaceTitle">DAW-ready campagneoverzicht</div>
    <div class="hp-title-sub" id="hpWorkspaceSubtitle">Kies klant, regio en workflow. Daarna werk je per stap verder.</div>
  </div>
  <div class="hp-actions">
    <div id="hpDemoBadge" class="hp-demo-badge" hidden>
      <span class="b1">DEMO · SYNTHETISCHE DATA</span>
      <span class="b2">Opportunity-signalen, geen koopintentie</span>
    </div>
    <span class="hp-chip">Klant <b id="hpTopClient">Nog kiezen</b></span>
    <span class="hp-chip">Leadset <b id="hpTopLeadset">Nog kiezen</b></span>
    <span class="hp-chip">Kosten <b id="hpTopCost">controle</b></span>
    <button class="hp-secondary-action" type="button" onclick="hpOpenFlyerEditor()">Flyer editor</button>
    <button class="hp-primary-action" type="button" onclick="hpPrimaryAction()">Start campagne</button>
  </div>
</section>

<div id="hpDemoGuardrail" class="hp-demo-guardrail" hidden>Scores zijn opportunity-signalen en geen koopintentie. Demo-data is synthetisch en mag niet als echte klant- of woningclaim worden gepresenteerd.</div>

<section id="hpStepRail" class="hp-step-rail" aria-label="Campagne stappen">
  <button class="hp-step-chip is-active" type="button" data-hp-step="1"><span>Stap 1</span><strong>Regio & selectie</strong></button>
  <button class="hp-step-chip" type="button" data-hp-step="2"><span>Stap 2</span><strong>Scoring & review</strong></button>
  <button class="hp-step-chip" type="button" data-hp-step="3"><span>Stap 3</span><strong>Renders</strong></button>
  <button class="hp-step-chip" type="button" data-hp-step="4"><span>Stap 4</span><strong>Materiaal</strong></button>
  <button class="hp-step-chip" type="button" data-hp-step="5"><span>Stap 5</span><strong>Publicatie</strong></button>
  <button class="hp-step-chip" type="button" data-hp-step="6"><span>Stap 6</span><strong>Opvolging</strong></button>
</section>


<header class="legacy-header">
  <div class="logo">
    <div class="logo-icon">FP</div>
    <div>
      <h1>FacadePilot Pipeline</h1>
      <div class="subtitle">Gevelrenovatie lead-campagne in een klik</div>
    </div>
  </div>
  <div class="subtitle">Local / Port <span id="port"></span></div>
</header>


<section id="hpCampaignOverview" class="hp-overview">
  <div class="hp-overview-grid">
    <div class="hp-command-panel">
      <div class="hp-command-head">
        <div>
          <h2 id="hpCampaignHeadline">Nieuwe DAW-campagne voorbereiden</h2>
          <p id="hpCampaignBrief">Selecteer eerst de klant en leadset. Gebruik daarna de wizard voor selectie, materiaal en publicatie.</p>
        </div>
        <span class="hp-status-pill" id="hpCampaignStatusPill">Demo klaar</span>
      </div>
      <div class="hp-card-grid">
        <article class="hp-overview-card">
          <h3>Campagne-wizard</h3>
          <p>Regio, scoring, renders, folders en QR-sites in vaste volgorde.</p>
          <div class="hp-card-stat"><strong>6</strong><span>stappen</span></div>
          <button class="hp-secondary-action" type="button" onclick="hpSetView('wizard')">Open wizard</button>
        </article>
        <article class="hp-overview-card">
          <h3>Leadselectie</h3>
          <p>Kaart, Street View, handmatige adressen en start vanuit selectie.</p>
          <div class="hp-card-stat"><strong id="hpOverviewLeadCount">0</strong><span>leads</span></div>
          <button class="hp-secondary-action" type="button" onclick="hpSetView('leads')">Open kaart</button>
        </article>
        <article class="hp-overview-card">
          <h3>Review & materiaal</h3>
          <p>Goedkeuringspoorten, renders, flyerproeven en outputcontrole.</p>
          <div class="hp-card-stat"><strong id="hpOverviewReviewCount">0</strong><span>open</span></div>
          <button class="hp-secondary-action" type="button" onclick="hpSetView('review')">Open inbox</button>
        </article>
      </div>
    </div>
    <aside class="hp-board-panel">
      <h2>Campagneflow</h2>
      <div class="hp-kanban">
        <div class="hp-kanban-row"><span>Selectie</span><div class="hp-progress-track"><div class="hp-progress-fill" style="width:72%"></div></div><strong>72</strong></div>
        <div class="hp-kanban-row"><span>Scoring</span><div class="hp-progress-track"><div class="hp-progress-fill" style="width:58%"></div></div><strong>58</strong></div>
        <div class="hp-kanban-row"><span>Renders</span><div class="hp-progress-track"><div class="hp-progress-fill" style="width:34%"></div></div><strong>34</strong></div>
        <div class="hp-kanban-row"><span>Folders</span><div class="hp-progress-track"><div class="hp-progress-fill" style="width:22%"></div></div><strong>22</strong></div>
        <div class="hp-kanban-row"><span>Follow-up</span><div class="hp-progress-track"><div class="hp-progress-fill" style="width:12%"></div></div><strong>12</strong></div>
      </div>
    </aside>
  </div>
</section>




<section id="hpIntelligenceDashboard" class="hp-intel-wrap" data-hp-view="intelligence">
  <div class="intel-head">
    <div>
      <h2>FacadePilot Intelligence</h2>
      <p id="intelSub">Cijfers, kaart, database en second brain op dezelfde campagnedata.</p>
    </div>
    <div class="intel-actions">
      <label class="intel-toggle"><input type="checkbox" id="intelPresentationMode" onchange="intelligenceSetPresentationMode(this.checked)"> Presentatiemodus</label>
      <button class="hp-secondary-action" type="button" onclick="intelligenceRefresh()">Ververs data</button>
      <button class="hp-secondary-action" type="button" onclick="intelligenceExportVisible()">Export zichtbaar</button>
    </div>
  </div>

  <div class="intel-tabs">
    <button class="active" type="button" data-intel-tab="overview" onclick="intelligenceShow('overview')">Overzicht</button>
    <button type="button" data-intel-tab="map" onclick="intelligenceShow('map')">Kaart</button>
    <button type="button" data-intel-tab="database" onclick="intelligenceShow('database')">Database</button>
    <button type="button" data-intel-tab="brain" onclick="intelligenceShow('brain')">Second brain</button>
  </div>

  <section class="intel-view active" id="intelViewOverview">
    <div class="intel-grid intel-g4" style="margin-bottom:14px">
      <div class="intel-card intel-kpi"><label>Adressen in scope</label><div class="v num" id="intelKpiTotal">-</div><div class="d">waarvan <em id="intelKpiTop">-</em> A/A+</div></div>
      <div class="intel-card intel-kpi"><label>Gewogen pipeline</label><div class="v num" id="intelKpiPipeline">-</div><div class="d"><span id="intelKpiM2">-</span> m2 gevel · schatting</div></div>
      <div class="intel-card intel-kpi"><label>Respons</label><div class="v num" id="intelKpiResponse">-</div><div class="d" id="intelKpiResponseDenom">noemer: contacted</div></div>
      <div class="intel-card intel-kpi"><label>Afspraken</label><div class="v num" id="intelKpiAppointments">-</div><div class="d">backlog: <b id="intelKpiBacklog">-</b></div></div>
    </div>
    <div class="intel-grid intel-g3">
      <div class="intel-card"><div class="intel-cardhead"><h3>Funnel</h3><span>met expliciete noemers</span></div><div class="intel-chartbox"><canvas id="intelChartFunnel"></canvas></div></div>
      <div class="intel-card"><div class="intel-cardhead"><h3>Klasseverdeling</h3><span>territoriumkwaliteit</span></div><div class="intel-chartbox"><canvas id="intelChartClass"></canvas></div></div>
      <div class="intel-card"><div class="intel-cardhead"><h3>Respons per partner</h3><span>campagne/CRM of demo-simulatie</span></div><div class="intel-chartbox"><canvas id="intelChartPartner"></canvas></div></div>
    </div>
    <div class="intel-grid intel-g2-1" style="margin-top:14px">
      <div class="intel-card"><div class="intel-cardhead"><h3>Campagnegolven</h3><span>respons per week</span></div><div class="intel-chartbox" style="height:250px"><canvas id="intelChartTrend"></canvas></div><div class="intel-footnote" id="intelSourceNote">Bronnen laden...</div></div>
      <div class="intel-card intel-pad">
        <h3 style="font-size:13.5px;margin-bottom:12px">Aanbevolen acties</h3>
        <div class="tl" id="intelActions"></div>
      </div>
    </div>
  </section>

  <section class="intel-view" id="intelViewMap">
    <div class="mapshell">
      <div id="intelMap"></div>
      <div class="mapstats">
        <div class="mapstat"><label>In beeld</label><div class="v num" id="intelMapCount">-</div></div>
        <div class="mapstat"><label>A/A+ in beeld</label><div class="v num" id="intelMapTop" style="color:var(--db-green)">-</div></div>
      </div>
      <div class="maplegend"><b>Klasse</b>
        <div class="row"><i style="background:#5fbe8f"></i> A+ topkandidaat</div>
        <div class="row"><i style="background:#5aa2e0"></i> A sterk</div>
        <div class="row"><i style="background:#e2a35c"></i> B goed</div>
        <div class="row"><i style="background:#5c6b80"></i> C/D</div>
      </div>
    </div>
  </section>

  <section class="intel-view" id="intelViewDatabase">
    <div class="intel-toolrow">
      <div class="intel-search"><span>Zoek</span><input id="intelSearch" placeholder="Adres, capakey, sector of partner" oninput="intelligenceDebouncedRows()"></div>
      <button class="intel-fchip on" data-k="A+" onclick="intelligenceToggleClass(this)">A+</button>
      <button class="intel-fchip on" data-k="A" onclick="intelligenceToggleClass(this)">A</button>
      <button class="intel-fchip on" data-k="B" onclick="intelligenceToggleClass(this)">B</button>
      <button class="intel-fchip" data-k="C" onclick="intelligenceToggleClass(this)">C</button>
      <button class="intel-fchip" data-k="D" onclick="intelligenceToggleClass(this)">D</button>
      <select class="intel-select" id="intelStatusFilter" onchange="intelligenceLoadRows()">
        <option value="">Alle statussen</option>
        <option value="wachtrij">Wachtrij</option>
        <option value="verstuurd">Verstuurd</option>
        <option value="gescand">Gescand</option>
        <option value="reactie">Reactie</option>
        <option value="afspraak">Afspraak</option>
        <option value="no-response">No-response</option>
      </select>
    </div>
    <div class="intel-dbgrid">
      <div class="intel-card">
        <div class="intel-tablewrap">
          <table class="intel-table">
            <thead><tr>
              <th onclick="intelligenceSort('adres')">Adres</th>
              <th onclick="intelligenceSort('score')">Score</th>
              <th onclick="intelligenceSort('klasse')">Klasse</th>
              <th onclick="intelligenceSort('m2')">Gevel m2</th>
              <th onclick="intelligenceSort('waarde')">Waarde</th>
              <th onclick="intelligenceSort('partner')">Partner</th>
              <th onclick="intelligenceSort('status')">Status</th>
            </tr></thead>
            <tbody id="intelTableBody"></tbody>
          </table>
        </div>
        <div class="intel-pager">
          <span id="intelPageInfo">Nog geen data</span>
          <span><button class="hp-secondary-action" onclick="intelligencePrevPage()">Vorige</button> <button class="hp-secondary-action" onclick="intelligenceNextPage()">Volgende</button></span>
        </div>
      </div>
      <aside class="drawer"><div class="intel-card" id="intelDrawer"><div class="dr-empty">Selecteer een rij om het dossier te openen.</div></div></aside>
    </div>
  </section>

  <section class="intel-view" id="intelViewBrain">
    <div class="brainshell">
      <canvas id="intelBrain"></canvas>
      <div class="brainui">
        <button class="hp-secondary-action" onclick="IntelligenceBrain.fit()">Fit</button>
        <button class="hp-secondary-action" onclick="IntelligenceBrain.focusBest()">Focus beste cluster</button>
        <button class="hp-secondary-action" onclick="IntelligenceBrain.shake()">Herorden</button>
      </div>
      <div class="brainlegend">
        <div class="row"><i style="background:#e2a35c"></i> Adres A/A+</div>
        <div class="row"><i style="background:#5aa2e0"></i> Signaal</div>
        <div class="row"><i style="background:#5fbe8f"></i> Partner</div>
        <div class="row"><i style="background:#a98fe8"></i> Learning</div>
        <div class="row"><i style="background:#e9eef5"></i> Campagne</div>
      </div>
      <div class="braininfo" id="intelBrainInfo"></div>
    </div>
  </section>

  <footer class="intel-footer">
    <span id="intelFooterSource">Bronnen worden geladen.</span>
    <span>Scores zijn opportunity-signalen op gebouwniveau, geen persoonsgegevens of koopintentie.</span>
  </footer>
</section>


<div class="layout" id="hpLegacyLayout">
  <!-- LEFT: Config -->
  <aside id="hpTargetDrawer" class="hp-target-drawer">
    <div class="card" style="margin-bottom:16px">
      <h2>1. Klant & merk</h2>
      <div class="field">
        <label>Voor welke klant runnen we deze batch?</label>
        <select id="clientProfileSelect"></select>
      </div>
      <div class="field">
        <label>Branding</label>
        <div class="mode-options" id="clientBrandOptions">
          <label class="mode-option">
            <input type="radio" name="clientBrandMode" value="facadepilot">
            <span>
              <strong>FacadePilot</strong>
              <small>Gevelrenovatie, crepi, isolatie, voegwerk en gevelafwerking.</small>
            </span>
          </label>
          <label class="mode-option">
            <input type="radio" name="clientBrandMode" value="windowpilot" checked>
            <span>
              <strong>WindowPilot</strong>
              <small>Ramen, deuren, rolluiken, screens en buitenschrijnwerk.</small>
            </span>
          </label>
        </div>
      </div>
      <div class="field">
        <label>Leadsbestand voor flyers/QR</label>
        <select id="clientLeadsSelect"></select>
        <div class="mode-note">Hierin staan de adressen én de bestandsnamen van de voor/na-renders.</div>
      </div>
      <div class="field">
        <label>Publieke QR-base</label>
        <input type="text" id="clientPublicBaseUrl" placeholder="https://www.windowpilot.be/r/klant">
      </div>
      <div class="help-panel">
        <strong>Waar pas je wat aan?</strong>
        <p>Teksten, kleuren, logo en offerteflow staan in het klantprofiel. Adressen en fotobestanden staan in het leadsbestand. Nieuwe renders zet je in de beeldenmap hieronder en daarna verwijs je ernaar in het leadsbestand.</p>
      </div>
      <div class="path-grid" id="clientPathSummary">
        <div class="path-row"><span>Klantprofiel</span><code id="clientProfilePathText">Nog geen klant gekozen</code></div>
        <div class="path-row"><span>Leads + fotopaden</span><code id="clientLeadsPathText">Nog geen leadsbestand gekozen</code></div>
        <div class="path-row"><span>Beeldenmap</span><code id="clientSourcePathText">Nog niet ingesteld</code></div>
        <div class="path-row"><span>Outputmap</span><code id="clientOutputPathText">Nog niet ingesteld</code></div>
        <div class="path-row"><span>QR-url basis</span><code id="clientPublicBaseText">Nog niet ingesteld</code></div>
      </div>
      <details class="copy-details">
        <summary>Teksten en fotopaden aanpassen</summary>
        <div class="copy-inner">
          <div class="copy-help">Klik eerst op laden. In het klantprofiel wijzig je folderteksten, QR-pagina-copy, logo, kleuren en lettertype. In het leadsbestand wijzig je adressen, segmenten en bestandsnamen van renders.</div>
          <div class="button-row">
            <button class="btn-sm btn-copy" type="button" onclick="loadClientEditableFiles()">Laad teksten en fotopaden</button>
            <button class="btn-sm btn-copy" type="button" onclick="openClientPath('source')">Open beeldenmap</button>
          </div>
          <div class="field" style="margin-top:10px">
            <label>Klantprofiel <span class="badge">teksten logo kleuren offerteflow</span></label>
            <textarea id="clientProfileEditor" class="json-editor" placeholder="Laad eerst een klantprofiel."></textarea>
            <button class="btn-sm btn-copy" type="button" onclick="saveClientEditableFile('profile')">Klantprofiel opslaan</button>
          </div>
          <div class="field">
            <label>Leads en foto's <span class="badge">adressen renders bestandsnamen</span></label>
            <textarea id="clientLeadsEditor" class="json-editor" placeholder="Laad eerst een leadsbestand."></textarea>
            <button class="btn-sm btn-copy" type="button" onclick="saveClientEditableFile('leads')">Leadsbestand opslaan</button>
          </div>
          <div id="clientEditorStatus" class="mode-note">Nog niets geladen.</div>
        </div>
      </details>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2>2. Regio & targeting</h2>

      <div class="field">
        <label>Streek/gemeente <span class="badge">postcode of NIS-code</span></label>
        <input type="text" id="niscode" placeholder="bijv. 3300 of 24107" list="gemeenten-list">
        <datalist id="gemeenten-list"></datalist>
        <div style="font-size:11px;margin-top:4px" id="gemeenteHint"></div>
      </div>

      <div class="field">
        <label>Campagnestreek/gemeentes <span class="badge">notitie</span></label>
        <textarea id="targetRegions" placeholder="bv. Gent, Drongen, Sint-Amandsberg, Mariakerke"></textarea>
        <div class="mode-note">Handig voor klantbriefing en latere batchruns over meerdere gemeentes.</div>
      </div>

      <div class="field">
        <label>Of start vanaf bestaand CSV <span class="badge">optioneel</span></label>
        <select id="inputCsv">
          <option value="">-- Nieuw (via adresselectie) --</option>
        </select>
      </div>

      <div class="field">
        <label>Woningtypes voor deze campagne</label>
        <div class="preset-options target-options" id="targetHouseTypes">
          <label class="preset-option">
            <input type="checkbox" value="klein">
            <span><span class="preset-title">Kleine woningen</span><span class="preset-meta">Compacte rijhuizen en kleinere gezinswoningen met snelle besliskans.</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="groot">
            <span><span class="preset-title">Grote woningen</span><span class="preset-meta">Meer geveloppervlak of raamoppervlak, grotere commerciële waarde.</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="rijwoning" checked>
            <span><span class="preset-title">Rijhuizen</span><span class="preset-meta">Dense straten, duidelijke gevelrijen, veel adressen.</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="halfopen" checked>
            <span><span class="preset-title">Halfopen woningen</span><span class="preset-meta">Goede balans tussen volume, zichtbaarheid en budget.</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="open">
            <span><span class="preset-title">Open bebouwing</span><span class="preset-meta">Grotere woningen met hogere ticketwaarde.</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="villa">
            <span><span class="preset-title">Villa's</span><span class="preset-meta">Premium segment, minder adressen, sterkere personalisatie.</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="appartement">
            <span><span class="preset-title">Kleine appartementsblokken</span><span class="preset-meta">Meerdere huisnummers, vaak één gevelbeslissing.</span></span>
          </label>
        </div>
      </div>

      <div class="field">
        <label>Inkomensprofiel</label>
        <select id="incomeTarget">
          <option value="any">Breed, niet filteren</option>
          <option value="middle">Middenklasse</option>
          <option value="upper" selected>Comfortabel inkomen</option>
          <option value="premium">Premium / hoge koopkracht</option>
        </select>
        <div class="mode-note">Wordt meegenomen als campagneprofiel en later als scoringsfilter verder aangescherpt.</div>
      </div>

      <div class="field">
        <label>Min. woninggrootte (m2)</label>
        <input type="number" id="minWoning" value="60" min="0">
      </div>

      <div class="field">
        <label>Max. woninggrootte (m2) <span class="badge">filter loodsen</span></label>
        <input type="number" id="maxWoning" value="350" min="60">
      </div>

      <div class="field">
        <label>Max. bebouwingsgraad <span class="badge">filter industrie</span></label>
        <input type="number" id="maxBebouwdRatio" value="0.75" min="0.1" max="1.0" step="0.05">
      </div>

      <div class="field">
        <label>Max. renders <span class="badge">optioneel</span></label>
        <input type="number" id="renderTop" placeholder="Leeg = alles" value="10">
      </div>

      <div class="field">
        <label>Render klassen</label>
        <select id="renderKlassen">
          <option value="A+,A">A+ en A (top leads)</option>
          <option value="A+,A,B">A+, A en B</option>
          <option value="">Alle klassen</option>
        </select>
      </div>

      <div class="field">
        <label id="renderPresetLabel">3. Ramen en zonwering voor renders</label>
        <input type="hidden" id="facadePreset" value="window_antraciet">
        <div class="preset-options" id="presetOptions">
          <label class="preset-option">
            <input type="checkbox" value="window_antraciet" checked>
            <span><span class="preset-title">Antraciet ramen en deuren</span><span class="preset-meta">Slanke donkere profielen, moderne glaspartijen en coherent buitenschrijnwerk</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_wit">
            <span><span class="preset-title">Witte ramen en deuren</span><span class="preset-meta">Frisse witte profielen met realistische glasreflecties en afgewerkte dagkanten</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_houtlook">
            <span><span class="preset-title">Houtlook of warme tint</span><span class="preset-meta">Warmere premium uitstraling voor landelijke of klassieke woningen</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_screens">
            <span><span class="preset-title">Ramen met screens</span><span class="preset-meta">Nieuwe ramen met subtiele geïntegreerde zonwering waar logisch</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_rolluiken">
            <span><span class="preset-title">Ramen met rolluiken</span><span class="preset-meta">Nieuwe ramen met discrete rolluiken en realistische geleiders/kasten</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_totaal">
            <span><span class="preset-title">Ramen deuren screens rolluiken</span><span class="preset-meta">Volledige buitenschrijnwerkrenovatie in één samenhangende look</span></span>
          </label>
        </div>
        <div class="preset-cost" id="presetCost">1 schrijnwerkoptie per woning</div>
      </div>

      <div class="toggle-row" style="margin-top:8px">
        <div>
          <div class="toggle-label">Pre-render quality check <span class="badge ok">$0.001</span></div>
          <div class="toggle-hint">Filter slechte foto's met gpt-4o-mini</div>
        </div>
        <label class="toggle"><input type="checkbox" id="qualityCheck" checked><span class="slider"></span></label>
      </div>

      <div class="toggle-row">
        <div>
          <div class="toggle-label">🤖 Auto-preset per lead <span class="badge ok">slim</span></div>
          <div class="toggle-hint">Kies type per lead op basis van profiel</div>
        </div>
        <label class="toggle"><input type="checkbox" id="autoPreset"><span class="slider"></span></label>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2>4. Workflow</h2>
      <div class="field">
        <label>Runmodus</label>
        <div class="mode-options" id="pipelineModeOptions">
          <label class="mode-option">
            <input type="radio" name="pipelineMode" value="full" checked>
            <span>
              <strong>Volledige workflow</strong>
              <small>Leads, kaart, renders, flyers en QR-sites.</small>
            </span>
          </label>
          <label class="mode-option">
            <input type="radio" name="pipelineMode" value="map_only">
            <span>
              <strong>Alleen leads/maps</strong>
              <small>Maak alleen CSV + kaartselectie. Daarna klik je zelf rond.</small>
            </span>
          </label>
        </div>
        <div class="mode-note" id="pipelineModeNote">Gebruik Alleen leads/maps om eerst rustig woningen te selecteren zonder renders te starten.</div>
      </div>
      <div class="workflow-step">
        <div class="workflow-step-title"><b>1</b> Zet of vervang de renders</div>
        <div class="field" style="margin-bottom:0">
          <label>Beeldenmap</label>
          <input type="text" id="clientSourceDir" placeholder="Map waar before/after foto's staan">
          <div class="field-help">Zet nieuwe renders in deze map. De bestandsnamen moeten overeenkomen met het leadsbestand: <b>before_file</b> en <b>variant_files</b>.</div>
        </div>
        <div class="button-row">
          <button class="btn-sm btn-copy" type="button" onclick="openClientPath('source')">Open beeldenmap</button>
          <button class="btn-sm btn-copy" type="button" onclick="loadClientEditableFiles()">Bewerk fotopaden</button>
        </div>
      </div>
      <div class="workflow-step">
        <div class="workflow-step-title"><b>2</b> Kies waar de nieuwe output komt</div>
        <div class="field" style="margin-bottom:0">
          <label>Outputmap</label>
          <input type="text" id="clientOutputRoot" placeholder="client_campaigns/klant_output">
          <div class="field-help">Hier komen de nieuwe PDF's, previews en QR-landingspagina's. De bestaande renders blijven gewoon staan.</div>
        </div>
        <button class="btn-sm btn-copy" type="button" onclick="openClientPath('output')">Open outputmap</button>
      </div>
      <div class="workflow-step">
        <div class="workflow-step-title"><b>3</b> Maak folders en QR-sites</div>
        <div class="toggle-row" style="margin-bottom:0">
          <div>
            <div class="toggle-label">Bestaande renders gebruiken</div>
            <div class="toggle-hint">Aan laten wanneer jij de renders al in de beeldenmap hebt gezet.</div>
          </div>
          <label class="toggle"><input type="checkbox" id="clientSkipRenders" checked><span class="slider"></span></label>
        </div>
        <div class="button-row">
          <button class="btn-sm btn-copy" onclick="validateClientCampaign()">Controleer bestanden</button>
          <button class="btn-sm btn-copy" onclick="refreshClientCampaignOptions()">Ververs klanten</button>
        </div>
        <button class="btn btn-primary" id="clientGenerateBtn" onclick="generateClientCampaign()" style="margin-top:2px">
          Genereer folders + QR-sites
        </button>
      </div>
      <div id="clientCampaignStatus" class="mode-note" style="margin-top:10px">Kies een klantprofiel en leadsbestand.</div>
      <div class="log" id="clientCampaignLog" style="margin-top:10px;max-height:150px;display:none"></div>
    </div>

    <!-- Builder Profile Card -->
    <div class="card" style="margin-bottom:16px">
      <h2>Aannemer profiel</h2>

      <div class="field">
        <label>Bedrijfsnaam</label>
        <input type="text" id="builderNaam" placeholder="Uw Gevelrenoveerder">
      </div>

      <div class="field">
        <label>Telefoon</label>
        <input type="text" id="builderTel" placeholder="0800 00 000">
      </div>

      <div class="field">
        <label>Accent kleur</label>
        <div style="display:flex;gap:8px;align-items:center">
          <input type="color" id="accentColor" value="#3b5998" style="width:44px;height:34px;padding:2px;cursor:pointer">
          <input type="text" id="accentColorText" value="#3b5998" style="width:90px;font-family:monospace;font-size:12px" oninput="document.getElementById('accentColor').value=this.value">
        </div>
      </div>

      <div class="field">
        <label>Headline op flyer <span class="badge">optioneel</span></label>
        <input type="text" id="headline" placeholder="Wat als uw gevel er zo uitzag?">
      </div>

      <details class="copy-details">
        <summary>Flyer copy per klant</summary>
        <div class="copy-inner">
          <div class="copy-help">Gebruik enters om regels bewust af te breken. Die regeleindes worden exact zo meegenomen in de PDF.</div>
          <div class="field">
            <label>Voorkant · kleine header</label>
            <textarea data-copy-key="front_header_tag" placeholder="Persoonlijke visualisatie"></textarea>
          </div>
          <div class="field">
            <label>Voorkant · headline</label>
            <textarea data-copy-key="front_headline" placeholder="Wat als uw gevel er&#10;zo uitzag?"></textarea>
          </div>
          <div class="field">
            <label>Voorkant · tekst onder headline</label>
            <textarea data-copy-key="front_body" placeholder="Een realistische impressie van uw woning na renovatie."></textarea>
          </div>
          <div class="field">
            <label>Voorkant · draai om cue</label>
            <textarea data-copy-key="front_flip_hint" placeholder="Draai om voor meer info"></textarea>
          </div>
          <div class="field">
            <label>Achterkant · kleine header</label>
            <textarea data-copy-key="back_header_tag" placeholder="Persoonlijk renovatievoorstel"></textarea>
          </div>
          <div class="field">
            <label>Achterkant · hoofdkop</label>
            <textarea data-copy-key="back_headline" placeholder="Zie meteen wat gevelrenovatie&#10;voor uw woning doet"></textarea>
          </div>
          <div class="field">
            <label>Achterkant · bodytekst</label>
            <textarea data-copy-key="back_body" placeholder="Een helder voorstel met beeld, afwerking en vrijblijvend advies."></textarea>
          </div>
          <div class="field">
            <label>QR-blok · titel</label>
            <textarea data-copy-key="qr_title" placeholder="Meer renders,&#10;één woning"></textarea>
          </div>
          <div class="field">
            <label>QR-blok · tekst</label>
            <textarea data-copy-key="qr_body" placeholder="Scan en bekijk enkele van onze voorstellen"></textarea>
          </div>
          <div class="field">
            <label>Info blokje 1 · waarde</label>
            <textarea data-copy-key="facts_1_value" placeholder="±148 m²"></textarea>
          </div>
          <div class="field">
            <label>Info blokje 1 · label</label>
            <textarea data-copy-key="facts_1_label" placeholder="Geveloppervlak"></textarea>
          </div>
          <div class="field">
            <label>Info blokje 2 · waarde</label>
            <textarea data-copy-key="facts_2_value" placeholder="Op maat"></textarea>
          </div>
          <div class="field">
            <label>Info blokje 2 · label</label>
            <textarea data-copy-key="facts_2_label" placeholder="Na gevelcheck"></textarea>
          </div>
          <div class="field">
            <label>Info blokje 3 · waarde</label>
            <textarea data-copy-key="facts_3_value" placeholder="3-5 weken"></textarea>
          </div>
          <div class="field">
            <label>Info blokje 3 · label</label>
            <textarea data-copy-key="facts_3_label" placeholder="Typische uitvoering"></textarea>
          </div>
          <div class="field">
            <label>Stappen · titel</label>
            <textarea data-copy-key="steps_title" placeholder="Hoe werkt het?"></textarea>
          </div>
          <div class="field">
            <label>Stap 1 · titel</label>
            <textarea data-copy-key="step_1_title" placeholder="Scan de QR-code"></textarea>
          </div>
          <div class="field">
            <label>Stap 1 · tekst</label>
            <textarea data-copy-key="step_1_body" placeholder="Bekijk uw persoonlijke visualisatie online."></textarea>
          </div>
          <div class="field">
            <label>Stap 2 · titel</label>
            <textarea data-copy-key="step_2_title" placeholder="Gratis plaatsbezoek"></textarea>
          </div>
          <div class="field">
            <label>Stap 2 · tekst</label>
            <textarea data-copy-key="step_2_body" placeholder="Een specialist bekijkt uw gevel en bespreekt de mogelijkheden."></textarea>
          </div>
          <div class="field">
            <label>Stap 3 · titel</label>
            <textarea data-copy-key="step_3_title" placeholder="Offerte op maat"></textarea>
          </div>
          <div class="field">
            <label>Stap 3 · tekst</label>
            <textarea data-copy-key="step_3_body" placeholder="U ontvangt een duidelijk voorstel met materiaalkeuze en planning."></textarea>
          </div>
          <div class="field">
            <label>Mini-argument 1</label>
            <textarea data-copy-key="arg_1" placeholder="Lagere&#10;energiefactuur"></textarea>
          </div>
          <div class="field">
            <label>Mini-argument 2</label>
            <textarea data-copy-key="arg_2" placeholder="Meerwaarde&#10;woning"></textarea>
          </div>
          <div class="field">
            <label>Mini-argument 3</label>
            <textarea data-copy-key="arg_3" placeholder="Premies&#10;mogelijk"></textarea>
          </div>
          <div class="field">
            <label>Mini-argument 4</label>
            <textarea data-copy-key="arg_4" placeholder="Op maat&#10;van uw gevel"></textarea>
          </div>
          <div class="field">
            <label>CTA · titel</label>
            <textarea data-copy-key="cta_title" placeholder="Interesse gewekt?"></textarea>
          </div>
          <div class="field">
            <label>CTA · tekst</label>
            <textarea data-copy-key="cta_body" placeholder="Scan de QR-code voor een vrijblijvend voorstel."></textarea>
          </div>
          <div class="field">
            <label>Voor-label</label>
            <textarea data-copy-key="compare_before_label" placeholder="Nu"></textarea>
          </div>
          <div class="field">
            <label>Na-label</label>
            <textarea data-copy-key="compare_after_label" placeholder="Straks?"></textarea>
          </div>
          <div class="field">
            <label>Online stijlvergelijking · titel</label>
            <textarea data-copy-key="compare_title" placeholder="Online stijlvergelijking"></textarea>
          </div>
          <div class="field">
            <label>Online stijlvergelijking · tekst</label>
            <textarea data-copy-key="compare_body" placeholder="Bekijk meerdere renovatierichtingen voor uw woning en kies uw favoriet."></textarea>
          </div>
          <div class="field">
            <label>Footer · regel 1</label>
            <textarea data-copy-key="footer_line_1" placeholder="Aangeboden door uw gevelspecialist"></textarea>
          </div>
          <div class="field">
            <label>Footer · regel 2</label>
            <textarea data-copy-key="footer_line_2" placeholder="AI-gegenereerde impressie op basis van een straatfoto."></textarea>
          </div>
          <div class="field">
            <label>Footer · regel 3</label>
            <textarea data-copy-key="footer_line_3" placeholder="Niet meer ontvangen · Privacybeleid"></textarea>
          </div>
          <div class="field">
            <label>Powered-by tekst</label>
            <textarea data-copy-key="footer_powered" placeholder="Powered by FacadePilot"></textarea>
          </div>
        </div>
      </details>

      <div class="field">
        <label>Logo uploaden <span class="badge">optioneel</span></label>
        <div style="display:flex;gap:8px;align-items:center">
          <input type="file" id="logoFile" accept="image/*" style="font-size:11px;width:180px" onchange="uploadLogo(event)">
          <img id="logoPreview" src="" style="max-height:28px;display:none;border-radius:4px">
        </div>
        <div id="logoStatus" style="font-size:11px;margin-top:4px;color:#4ade80;display:none"></div>
      </div>

      <button class="btn btn-primary" style="background:rgba(34,197,94,0.15);color:#4ade80;border:1px solid rgba(34,197,94,0.3);box-shadow:none;font-size:12px;padding:10px" onclick="saveProfile()">
        Profiel opslaan
      </button>
      <div id="profileStatus" style="font-size:11px;margin-top:6px;color:#4ade80;display:none"></div>
    </div>

    <!-- Handmatig adres -->
    <div class="card" style="margin-bottom:16px">
      <h2>📍 Handmatig adres</h2>
      <div class="field">
        <label>Adres (bv. "Kerkstraat 1, 3300 Tienen")</label>
        <input type="text" id="manualAdres" placeholder="Straat huisnummer, postcode gemeente">
      </div>
      <div class="field">
        <label id="manualPresetLabel">Ramen en zonwering voor dit adres</label>
        <div class="preset-options" id="manualPresetOptions">
          <label class="preset-option">
            <input type="checkbox" value="window_antraciet" checked>
            <span><span class="preset-title">Antraciet ramen en deuren</span><span class="preset-meta">Slanke donkere profielen, moderne glaspartijen en coherent buitenschrijnwerk</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_wit">
            <span><span class="preset-title">Witte ramen en deuren</span><span class="preset-meta">Frisse witte profielen met realistische glasreflecties en afgewerkte dagkanten</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_houtlook">
            <span><span class="preset-title">Houtlook of warme tint</span><span class="preset-meta">Warmere premium uitstraling voor landelijke of klassieke woningen</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_screens">
            <span><span class="preset-title">Ramen met screens</span><span class="preset-meta">Nieuwe ramen met subtiele geïntegreerde zonwering waar logisch</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_rolluiken">
            <span><span class="preset-title">Ramen met rolluiken</span><span class="preset-meta">Nieuwe ramen met discrete rolluiken en realistische geleiders/kasten</span></span>
          </label>
          <label class="preset-option">
            <input type="checkbox" value="window_totaal">
            <span><span class="preset-title">Ramen deuren screens rolluiken</span><span class="preset-meta">Volledige buitenschrijnwerkrenovatie in één samenhangende look</span></span>
          </label>
        </div>
        <div class="preset-cost" id="manualPresetCost">1 schrijnwerkoptie voor handmatige adressen</div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <button class="btn-sm btn-copy" onclick="addManualAddress()" style="flex:1">+ Toevoegen</button>
        <button class="btn-sm" onclick="clearManual()" style="background:rgba(220,53,69,0.15);color:#fca5a5;border:1px solid rgba(220,53,69,0.3)">Wis</button>
      </div>
      <div id="manualList" style="font-size:11px;color:#94a3b8;margin-bottom:10px"></div>
      <button class="btn btn-primary" id="manualRunBtn" onclick="manualRun()" style="background:linear-gradient(135deg,#22c55e,#15803d);font-size:13px;padding:11px;display:none">
        🚀 Express-run (render + flyer + landing + online)
      </button>
    </div>

    <div class="card">
      <h2>Stappen aan/uit</h2>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">1. Adresselectie <span class="badge ok" id="modAdres">OK</span></div>
          <div class="toggle-hint">GIS data -> adressen CSV</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepAdres" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">2. Lead scoring <span class="badge ok" id="modScore">OK</span></div>
          <div class="toggle-hint">Rangschik op woninggrootte</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepScore" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">3. Renders <span class="badge" id="modRender">--</span></div>
          <div class="toggle-hint">Street View -> GPT Image renders</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepRender" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">4. Flyers <span class="badge" id="modFlyer">--</span></div>
          <div class="toggle-hint">PDF per lead</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepFlyer" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">5. QR-landingspagina's <span class="badge ok">multi-stijl</span></div>
          <div class="toggle-hint">HTML per adres met voor/na-slider, extra afwerkingen en scan-tracking</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepLanding" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">6. Meteen online publiceren <span class="badge ok">standaard aan</span></div>
          <div class="toggle-hint">Kopieert QR-websites naar /r/ en voert automatisch Vercel deploy uit</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepPublish" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">7. E-mail-flyers <span class="badge">optioneel</span></div>
          <div class="toggle-hint">HTML mail (alternatief voor papier)</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepEmail"><span class="slider"></span></label>
      </div>
      <div class="toggle-row" style="margin-top:6px;border-top:1px dashed rgba(255,255,255,0.06);padding-top:12px">
        <div>
          <div class="toggle-label">Vergunning pre-filter <span class="badge">CSV-cache</span></div>
          <div class="toggle-hint">Skip adressen met recente gevelvergunning</div>
        </div>
        <label class="toggle"><input type="checkbox" id="vergunningFilter" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">CRM-sync (Supabase) <span class="badge ok">aanbevolen</span></div>
          <div class="toggle-hint">Leads persistent + funnel-tracking</div>
        </div>
        <label class="toggle"><input type="checkbox" id="crmSync" checked><span class="slider"></span></label>
      </div>

      <button class="btn btn-primary" id="startBtn" onclick="startPipeline()">
        Start Pipeline
      </button>
      <button class="btn btn-danger" id="cancelBtn" onclick="cancelPipeline()" style="display:none">
        Annuleer
      </button>
    </div>
  </aside>

  <!-- RIGHT: Progress -->
  <div>
    <div class="done-banner" id="doneBanner">
      <h3 id="doneTitle">Pipeline voltooid!</h3>
      <p id="doneSummary"></p>
    </div>

    <div class="elapsed-bar hidden" id="elapsedBar">
      <div>
        <div class="elapsed-label">Verstreken tijd</div>
        <div class="elapsed-value" id="elapsedTime">00:00</div>
      </div>
      <div class="elapsed-gemeente" id="elapsedGemeente"></div>
      <div>
        <div class="elapsed-label">Status</div>
        <div class="elapsed-value" style="font-size:14px" id="elapsedStatus">Bezig<span class="elapsed-dots" id="elapsedDots">.</span></div>
      </div>
    </div>

    <!-- Cost tracker widget -->
    <div class="card hidden" id="costCard" style="margin-bottom:14px;display:none">
      <h2 style="display:flex;align-items:center;justify-content:space-between">
        <span>Live API-kosten</span>
        <span class="elapsed-value" id="costTotal" style="font-size:18px">$0.00</span>
      </h2>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px">
        <div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:10px">
          <div style="color:#94a3b8;text-transform:uppercase;font-size:10px;letter-spacing:0.5px;margin-bottom:4px">Street View</div>
          <div style="font-size:15px;font-weight:700" id="costSV">$0.00</div>
          <div style="color:#94a3b8;font-size:11px;margin-top:2px"><span id="costSVPhotos">0</span> foto's</div>
        </div>
        <div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:10px">
          <div style="color:#94a3b8;text-transform:uppercase;font-size:10px;letter-spacing:0.5px;margin-bottom:4px">Quality check</div>
          <div style="font-size:15px;font-weight:700" id="costQC">$0.00</div>
          <div style="color:#94a3b8;font-size:11px;margin-top:2px"><span id="costQCDone">0</span>, <span id="costQCFailed" style="color:#fbbf24">0</span> skip</div>
        </div>
        <div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:10px">
          <div style="color:#94a3b8;text-transform:uppercase;font-size:10px;letter-spacing:0.5px;margin-bottom:4px">GPT Image</div>
          <div style="font-size:15px;font-weight:700" id="costRender">$0.00</div>
          <div style="color:#94a3b8;font-size:11px;margin-top:2px"><span id="costRenderDone">0</span> renders</div>
        </div>
      </div>
      <div id="costSavings" style="margin-top:10px;font-size:12px;color:#4ade80;display:none">
        <span id="costSavedAmount"></span>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2>Voortgang</h2>
      <div class="steps" id="stepsContainer">
        <div class="step" id="step-adresselectie">
          <div class="step-header">
            <div class="step-icon pending" id="icon-adresselectie">1</div>
            <div class="step-title">Adresselectie</div>
          </div>
          <div class="step-msg" id="msg-adresselectie">Wacht op start</div>
          <div class="step-bar"><div class="step-bar-fill" id="bar-adresselectie"></div></div>
        </div>
        <div class="step" id="step-scoring">
          <div class="step-header">
            <div class="step-icon pending" id="icon-scoring">2</div>
            <div class="step-title">Lead scoring</div>
          </div>
          <div class="step-msg" id="msg-scoring">Wacht op start</div>
          <div class="step-bar"><div class="step-bar-fill" id="bar-scoring"></div></div>
        </div>
        <div class="step" id="step-render">
          <div class="step-header">
            <div class="step-icon pending" id="icon-render">3</div>
            <div class="step-title">Gevelrenovatie renders</div>
          </div>
          <div class="step-msg" id="msg-render">Wacht op start</div>
          <div class="step-bar"><div class="step-bar-fill" id="bar-render"></div></div>
        </div>
        <div class="step" id="step-flyer">
          <div class="step-header">
            <div class="step-icon pending" id="icon-flyer">4</div>
            <div class="step-title">Flyer generatie</div>
          </div>
          <div class="step-msg" id="msg-flyer">Wacht op start</div>
          <div class="step-bar"><div class="step-bar-fill" id="bar-flyer"></div></div>
        </div>
        <div class="step" id="step-landing">
          <div class="step-header">
            <div class="step-icon pending" id="icon-landing">5</div>
            <div class="step-title">Landingpagina's</div>
          </div>
          <div class="step-msg" id="msg-landing">Wacht op start</div>
          <div class="step-bar"><div class="step-bar-fill" id="bar-landing"></div></div>
        </div>
        <div class="step" id="step-publish">
          <div class="step-header">
            <div class="step-icon pending" id="icon-publish">6</div>
            <div class="step-title">Online publicatie</div>
          </div>
          <div class="step-msg" id="msg-publish">Wacht op start</div>
          <div class="step-bar"><div class="step-bar-fill" id="bar-publish"></div></div>
        </div>
        <div class="step" id="step-email">
          <div class="step-header">
            <div class="step-icon pending" id="icon-email">7</div>
            <div class="step-title">E-mail-flyers</div>
          </div>
          <div class="step-msg" id="msg-email">Wacht op start</div>
          <div class="step-bar"><div class="step-bar-fill" id="bar-email"></div></div>
        </div>
      </div>
    </div>

    <!-- Output Files -->
    <div class="card section" id="outputCard" style="display:none">
      <h2>Output bestanden</h2>
      <ul class="file-list" id="fileList"></ul>
    </div>

    <!-- Kaart + Clustering -->
    <div class="card section" id="mapCard" style="display:none">
      <h2 style="display:flex;align-items:center;justify-content:space-between">
        <span>Kaart & clusters</span>
        <span class="hp-map-tools">
          <button class="btn-sm btn-copy" id="hpTargetToggleBtn" onclick="hpToggleTargetDrawer()">Filters tonen</button>
          <button class="btn-sm btn-copy" onclick="reloadMap()">Verversen</button>
        </span>
      </h2>
      <div class="legend">
        <div class="legend-item"><span class="legend-dot" style="background:#22c55e"></span>A+</div>
        <div class="legend-item"><span class="legend-dot" style="background:#4ade80"></span>A</div>
        <div class="legend-item"><span class="legend-dot" style="background:#60a5fa"></span>B</div>
        <div class="legend-item"><span class="legend-dot" style="background:#fbbf24"></span>C</div>
        <div class="legend-item"><span class="legend-dot" style="background:#94a3b8"></span>D</div>
        <div class="legend-item" style="margin-left:auto"><span id="mapMeta" style="color:#94a3b8;font-size:11px"></span></div>
      </div>
      <div class="map-review-layout">
        <div id="mapContainer"></div>
        <aside class="lead-review-panel" id="leadReviewPanel">
          <div class="lead-review-empty">Klik op een lead op de kaart om Street View te bekijken, de camera bij te sturen en te kiezen wat er met deze lead gebeurt.</div>
        </aside>
      </div>
      <div id="clusterHint" style="margin-top:10px;font-size:12px;color:#94a3b8"></div>
      <section class="address-workbench" id="leadAddressWorkbench">
        <div class="address-workbench-head">
          <div>
            <h3>Adressen alfabetisch controleren</h3>
            <p>Selecteer adressen vanuit de lijst, laad Street View per rij en bewaar alleen wat later door eigen fotografie bevestigd wordt.</p>
          </div>
          <div class="address-actions">
            <button type="button" onclick="hpSetView('route')">Maak fotoroute</button>
            <button type="button" class="primary" onclick="hpSetView('photos')">Foto's koppelen</button>
          </div>
        </div>
        <div id="leadAddressList" class="address-list">
          <div class="lead-review-empty">Laad eerst kaartleads.</div>
        </div>
        <button id="leadAddressMoreBtn" class="address-list-more hp-secondary-action" type="button" onclick="showMoreLeadAddresses()" style="display:none">Toon meer adressen</button>
      </section>
      <div class="review-summary" id="reviewSummary">
        <div class="review-summary-head">
          <div>
            <h3 style="font-size:13px;margin:0 0 4px;color:#e2e8f0">Kaartselectie voor pipeline</h3>
            <div class="review-counts" id="reviewCounts">Nog geen kaartselectie geladen.</div>
          </div>
          <button class="review-start" id="reviewStartBtn" onclick="startPipelineFromMapSelection()" disabled>Start pipeline met selectie</button>
        </div>
        <div class="review-list" id="reviewList"></div>
      </div>
    </div>

    <div class="card section field-route-card" id="fieldRouteCard" data-hp-view="route">
      <div class="field-route-head">
        <div>
          <h3>Routeplanning voor eigen gevelbeelden</h3>
          <p>Gebruik de geselecteerde adressen als routebatch. De app ordent de stops lokaal; Google Maps opent daarna de route voor live navigatie.</p>
        </div>
        <div class="field-route-actions">
          <button type="button" onclick="buildFieldRoute('driving')" class="primary">Autoroute</button>
          <button type="button" onclick="buildFieldRoute('bicycling')">Fietsroute</button>
          <button type="button" onclick="openFieldRouteInGoogle()">Open in Google Maps</button>
        </div>
      </div>
      <div class="field">
        <label>Startpunt fotograaf <span class="badge">optioneel</span></label>
        <input type="text" id="fieldRouteOrigin" placeholder="bv. Tiensesteenweg 54A, 3380 Bunsbeek">
        <div class="mode-note">Leeg laten = vertrek bij eerste geselecteerde adres. Exacte live reistijd komt uit Google Maps; hieronder tonen we een werkinschatting.</div>
      </div>
      <div id="fieldRouteSummary" class="route-summary">
        <div><span>Stops</span><strong>-</strong></div>
        <div><span>Afstand</span><strong>-</strong></div>
        <div><span>Auto</span><strong>-</strong></div>
        <div><span>Fiets</span><strong>-</strong></div>
      </div>
      <div id="fieldRouteList" class="route-list">
        <div class="lead-review-empty">Selecteer eerst adressen op de kaart of in de alfabetische lijst.</div>
      </div>
      <div class="pipeline-gate-note">Praktisch: maak kleine batches van 10-20 adressen per rit. Zo blijft Google Maps bruikbaar en kan je onderweg foto’s rustig controleren.</div>
    </div>

    <div class="card section photo-intake-card" id="fieldPhotoCard" data-hp-view="photos">
      <div class="photo-intake-head">
        <div>
          <h3>Eigen foto’s koppelen vóór render</h3>
          <p>Een adres mag pas naar render wanneer er een eigen foto, partnerupload of andere toegelaten bron aan gekoppeld is.</p>
        </div>
        <div class="address-actions">
          <button type="button" onclick="renderFieldPhotoList()">Ververs lijst</button>
          <button type="button" class="primary" onclick="hpSetView('renderreview')">Naar render review</button>
        </div>
      </div>
      <div id="fieldPhotoList" class="photo-list">
        <div class="lead-review-empty">Nog geen route- of kaartselectie geladen.</div>
      </div>
      <div class="pipeline-gate-note">Nieuwe productieregel: Street View is alleen quick check. Renders starten pas na een eigen of aantoonbaar toegelaten bronbeeld.</div>
    </div>

    <div class="card section" id="renderApprovalCard" data-hp-view="renderreview">
      <h2>Render review — pas daarna flyers en landingspagina's</h2>
      <div class="pipeline-gate-note">Correcte volgorde: geselecteerd adres → eigen foto gekoppeld → render maken → render goedkeuren → flyerproef → landingpagina → campagne go/no-go.</div>
      <div class="address-actions" style="margin-top:12px">
        <button type="button" onclick="switchReviewGate('render');hpSetView('review');setTimeout(loadReview,80)" class="primary">Open renderwachtrij</button>
        <button type="button" onclick="switchReviewGate('flyer_proof');hpSetView('review');setTimeout(loadReview,80)">Open flyerproeven</button>
        <button type="button" onclick="switchReviewGate('campaign_go');hpSetView('review');setTimeout(loadReview,80)">Campagne go/no-go</button>
      </div>
    </div>

    <!-- CRM funnel + lijst -->
    <div class="card section" id="crmCard" style="display:none">
      <h2 style="display:flex;align-items:center;justify-content:space-between">
        <span>CRM — leads & follow-up</span>
        <button class="btn-sm btn-copy" onclick="reloadCrm()">Verversen</button>
      </h2>
      <div id="crmStatus" style="font-size:12px;color:#94a3b8;margin-bottom:10px"></div>
      <div id="crmFunnel" style="margin-bottom:14px"></div>
      <div style="overflow-x:auto">
        <table class="crm-table">
          <thead><tr>
            <th>Status</th><th>Klasse</th><th>Score</th><th>Adres</th><th>Acties</th>
          </tr></thead>
          <tbody id="crmTableBody"></tbody>
        </table>
      </div>
    </div>

    <!-- Render Gallery + Preview -->
    <div class="card section" id="renderCard" style="display:none">
      <h2>Gevelrenovatie renders</h2>
      <div class="tab-bar">
        <div class="tab active" onclick="switchRenderTab('gallery')">Galerij</div>
        <div class="tab" onclick="switchRenderTab('replace')">Vervangen</div>
      </div>

      <div id="renderGalleryTab">
        <div class="render-gallery" id="renderGallery"></div>
      </div>

      <div id="renderReplaceTab" style="display:none">
        <div class="replace-section">
          <h4>Render vervangen</h4>
          <p>Selecteer een render hierboven, gebruik de originele Street View foto om zelf een betere render te maken in ChatGPT, en upload het resultaat hier.</p>

          <div id="selectedRenderInfo" style="margin-bottom:12px;display:none">
            <div class="preview-grid" style="margin-bottom:12px">
              <div class="preview-item">
                <div class="label">Origineel (Street View)</div>
                <img id="replaceStreetview" src="">
              </div>
              <div class="preview-item">
                <div class="label">Huidige render</div>
                <img id="replaceCurrentRender" src="">
              </div>
            </div>
            <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
              <button class="btn-sm btn-copy" onclick="copyFacadePrompt()">Kopieer prompt voor ChatGPT</button>
              <button class="btn-sm btn-copy" onclick="downloadStreetview()">Download Street View foto</button>
            </div>
          </div>

          <div class="drop-zone" id="dropZone" onclick="document.getElementById('renderFileInput').click()">
            <input type="file" id="renderFileInput" accept="image/*" onchange="handleRenderUpload(event)">
            Sleep je nieuwe render hierheen of klik om te uploaden
          </div>
          <div id="uploadStatus" style="margin-top:8px;font-size:12px;color:#4ade80;display:none"></div>
        </div>
      </div>
    </div>

    <!-- Preview Panel -->
    <div class="preview-panel" id="previewPanel">
      <h3 id="previewTitle">Preview</h3>
      <div id="previewContent"></div>
    </div>

    <!-- Review-poorten (HITL stap 3) -->
    <div class="card section" id="reviewCard">
      <h2 style="display:flex;align-items:center;justify-content:space-between">
        <span>Review — goedkeuringspoorten</span>
        <button class="btn-sm btn-copy" onclick="loadReview()">Verversen</button>
      </h2>
      <div class="tab-bar" id="reviewTabBar">
        <div class="tab active" data-gate="voorfoto" onclick="switchReviewGate('voorfoto')">Voorfoto</div>
        <div class="tab" data-gate="render" onclick="switchReviewGate('render')">Render</div>
        <div class="tab" data-gate="flyer_proof" onclick="switchReviewGate('flyer_proof')">Flyer-proef</div>
        <div class="tab" data-gate="campaign_go" onclick="switchReviewGate('campaign_go')">Campagne go/no-go</div>
      </div>
      <div id="reviewStats" class="review-stats"></div>
      <div id="reviewBulkBar" class="review-bulk" style="display:none">
        <button class="btn-sm" onclick="reviewSelectAll(true)">Selecteer alles</button>
        <button class="btn-sm" onclick="reviewSelectAll(false)">Deselecteer alles</button>
        <button class="btn-sm btn-copy" onclick="reviewBulkApprove()">Keur geselecteerde goed</button>
        <span id="reviewBulkStatus" class="review-bulk-status"></span>
      </div>
      <div id="reviewQueue" class="review-queue"></div>
      <div id="campaignGoPanel" style="display:none"></div>
    </div>

    <!-- Log -->
    <div class="card section">
      <h2>Log</h2>
      <div class="log" id="log"></div>
    </div>
  </div>
</div>
</div>

<script>
document.getElementById('port').textContent = location.port || '80';


// HomePilot Campaign OS v2
const HP_VIEW_COPY = {
  campaigns: {
    kicker: 'Campagnes',
    title: 'DAW-ready campagneoverzicht',
    subtitle: 'Kies klant, regio en workflow. Daarna werk je per stap verder.'
  },
  wizard: {
    kicker: 'Campagne-wizard',
    title: 'Van selectie naar publicatie',
    subtitle: 'Alle operationele stappen blijven zichtbaar in de juiste volgorde.'
  },
  leads: {
    kicker: 'Leads & kaart',
    title: 'Selecteer woningen en stuur Street View bij',
    subtitle: 'Werk met regiofilters, handmatige adressen, kaartselectie en start vanuit review.'
  },
  route: {
    kicker: 'Routefoto’s',
    title: 'Plan de snelste fotobatch',
    subtitle: 'Maak routebatches voor auto of fiets langs de geselecteerde adressen.'
  },
  photos: {
    kicker: 'Foto’s koppelen',
    title: 'Eigen bronbeelden vóór render',
    subtitle: 'Koppel per adres een eigen foto of toegelaten bronbeeld voor de renderfase.'
  },
  review: {
    kicker: 'Review-inbox',
    title: 'Goedkeuren voor er geld of reputatie beweegt',
    subtitle: 'Voorfoto, render, flyerproef en campagne go/no-go zitten apart.'
  },
  renderreview: {
    kicker: 'Render review',
    title: 'Render eerst goedkeuren, dan pas campagnemateriaal',
    subtitle: 'Renders worden een expliciete poort vóór flyers, QR-sites en publicatie.'
  },
  output: {
    kicker: 'Output',
    title: 'Folders, QR-sites, renders en CRM',
    subtitle: 'Controleer wat klaarstaat voor publicatie en opvolging.'
  },
  intelligence: {
    kicker: 'Intelligence',
    title: 'Cijfers, kaart, database en second brain',
    subtitle: 'Managementoverzicht en dossierwerkblad op dezelfde campagnedata.'
  },
  settings: {
    kicker: 'Instellingen',
    title: 'Klantprofiel, brand en bestanden',
    subtitle: 'Beheer teksten, folders, basiskleuren, logo en outputlocaties.'
  }
};

function hpCardTitle(card) {
  const h = card ? card.querySelector('h2') : null;
  return (h ? h.textContent : '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function hpSetViews(el, views) {
  if (!el || el.dataset.hpView) return;
  el.dataset.hpView = views.join(' ');
}

function hpTagCards() {
  const cards = Array.from(document.querySelectorAll('.layout .card'));
  cards.forEach(card => {
    const title = hpCardTitle(card);
    if (title.includes('klant') || title.includes('merk')) hpSetViews(card, ['wizard','settings']);
    else if (title.includes('regio') || title.includes('targeting')) hpSetViews(card, ['wizard','leads']);
    else if (title.includes('workflow')) hpSetViews(card, ['wizard','output']);
    else if (title.includes('aannemer')) hpSetViews(card, ['settings']);
    else if (title.includes('handmatig')) hpSetViews(card, ['wizard','leads']);
    else if (title.includes('stappen')) hpSetViews(card, ['wizard','settings']);
    else if (title.includes('voortgang')) hpSetViews(card, ['wizard','output']);
    else if (title.includes('output')) hpSetViews(card, ['wizard','output']);
    else if (title.includes('kaart') || title.includes('selectie')) hpSetViews(card, ['leads']);
    else if (title.includes('crm')) hpSetViews(card, ['output']);
    else if (title.includes('renders')) hpSetViews(card, ['wizard','review','output']);
    else if (title.includes('review')) hpSetViews(card, ['wizard','review']);
    else if (title.includes('log')) hpSetViews(card, ['wizard','leads','review','output','settings']);
  });
  hpSetViews(document.getElementById('doneBanner'), ['wizard','output']);
  hpSetViews(document.getElementById('elapsedBar'), ['wizard','output']);
  hpSetViews(document.getElementById('costCard'), ['wizard','output']);
  hpSetViews(document.getElementById('previewPanel'), ['review','output']);
}

function hpCount(selector) {
  return document.querySelectorAll(selector).length;
}

function hpSelectedText(id, fallback) {
  const el = document.getElementById(id);
  if (!el) return fallback;
  if (el.tagName === 'SELECT') {
    const opt = el.options[el.selectedIndex];
    return (opt && opt.textContent ? opt.textContent : fallback).replace(/\s+\(.*/, '').trim() || fallback;
  }
  return (el.value || fallback || '').trim();
}

function updateTargetDrawerButton() {
  const btn = document.getElementById('hpTargetToggleBtn');
  if (!btn) return;
  const collapsed = document.body.classList.contains('hp-target-collapsed');
  btn.textContent = collapsed ? 'Filters tonen' : 'Filters verbergen';
}

function hpToggleTargetDrawer(force) {
  const collapsed = typeof force === 'boolean'
    ? force
    : !document.body.classList.contains('hp-target-collapsed');
  document.body.classList.toggle('hp-target-collapsed', collapsed);
  try { localStorage.setItem('homepilot.facadepilot.targetCollapsed', collapsed ? '1' : '0'); } catch (e) {}
  updateTargetDrawerButton();
  if (_map && typeof _map.invalidateSize === 'function') {
    setTimeout(() => _map.invalidateSize(), 180);
  }
}



function hpIsDemoDataset() {
  const params = new URLSearchParams(location.search || '');
  if (params.get('demo') === '1' || params.get('synthetic') === '1') return true;
  try {
    if (localStorage.getItem('homepilot.demoData') === '1') return true;
  } catch (e) {}
  const profile = document.getElementById('clientProfileSelect');
  const leads = document.getElementById('clientLeadsSelect');
  const output = document.getElementById('clientOutputRoot');
  const parts = [
    profile?.value || '',
    profile?.selectedOptions?.[0]?.textContent || '',
    profile?.selectedOptions?.[0]?.dataset?.key || '',
    leads?.value || '',
    leads?.selectedOptions?.[0]?.textContent || '',
    output?.value || ''
  ];
  return /(synthet|synthetic|demo|sample|mock|placeholder|testdata|homepilot_demo)/i.test(parts.join(' '));
}

function hpSyncTopbar() {
  const client = hpSelectedText('clientProfileSelect', 'Nog kiezen');
  const leadset = hpSelectedText('clientLeadsSelect', 'Nog kiezen');
  const brand = (document.querySelector('input[name="clientBrandMode"]:checked') || {}).value || 'facadepilot';
  const renderCount = hpCount('.render-thumb');
  const reviewCount = hpCount('#reviewQueue .review-item');
  const crmCount = hpCount('#crmTableBody tr');
  const manualCount = hpCount('#manualList .manual-item');
  const leadCount = Math.max(crmCount, manualCount, hpCount('.leaflet-marker-icon'));
  const selectedCount = _reviewSummary && _reviewSummary.counts ? Number(_reviewSummary.counts.selected || 0) : 0;
  const photoCount = _fieldPhotos ? Object.keys(_fieldPhotos).length : 0;
  const cost = document.getElementById('costCard') && getComputedStyle(document.getElementById('costCard')).display !== 'none' ? 'bekijk' : 'controle';
  const isDemo = hpIsDemoDataset();
  document.body.classList.toggle('hp-demo-data', isDemo);
  ['hpDemoBadge','hpDemoGuardrail'].forEach(id => { const el = document.getElementById(id); if (el) el.hidden = !isDemo; });
  const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  setText('hpTopClient', client);
  setText('hpSideClient', client.length > 16 ? client.slice(0, 15) + '...' : client);
  setText('hpTopLeadset', leadset);
  setText('hpTopCost', cost);
  setText('hpSideBrand', brand === 'windowpilot' ? 'WindowPilot' : 'FacadePilot');
  setText('hpSidePort', location.port || '80');
  setText('hpLeadCount', String(leadCount));
  setText('hpRouteCount', String(selectedCount || leadCount || 0));
  setText('hpPhotoCount', String(photoCount));
  setText('hpRenderReviewCount', String(reviewCount));
  setText('hpOverviewLeadCount', String(leadCount));
  setText('hpReviewCount', String(reviewCount));
  setText('hpOverviewReviewCount', String(reviewCount));
  setText('hpOutputCount', String(renderCount || crmCount || 0));
  setText('hpIntelCount', String(leadCount || crmCount || renderCount || 0));
  const headline = document.getElementById('hpCampaignHeadline');
  if (headline) headline.textContent = client && client !== 'Nog kiezen' ? `${client} campagne voorbereiden` : 'Nieuwe campagne voorbereiden';
}

function hpSetView(view) {
  if (!HP_VIEW_COPY[view]) view = 'campaigns';
  document.body.classList.remove('hp-view-campaigns','hp-view-wizard','hp-view-leads','hp-view-route','hp-view-photos','hp-view-review','hp-view-renderreview','hp-view-output','hp-view-intelligence','hp-view-settings');
  document.body.classList.add(`hp-view-${view}`);
  document.querySelectorAll('[data-hp-view-button]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.hpViewButton === view);
  });
  const copy = HP_VIEW_COPY[view];
  const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  setText('hpWorkspaceKicker', copy.kicker);
  setText('hpWorkspaceTitle', copy.title);
  setText('hpWorkspaceSubtitle', copy.subtitle);
  try { localStorage.setItem('homepilot.facadepilot.view', view); } catch (e) {}
  hpSyncTopbar();
  updateTargetDrawerButton();
  if (view === 'route') setTimeout(() => buildFieldRoute(_fieldRouteMode || 'driving'), 0);
  if (view === 'photos') setTimeout(renderFieldPhotoList, 0);
  if (view === 'intelligence' && typeof intelligenceRefresh === 'function') setTimeout(intelligenceRefresh, 0);
}

function hpSetStep(step) {
  document.querySelectorAll('[data-hp-step]').forEach(btn => {
    btn.classList.toggle('is-active', btn.dataset.hpStep === String(step));
  });
  hpSetView('wizard');
  const targetByStep = {
    1: 'niscode',
    2: 'reviewCard',
    3: 'renderCard',
    4: 'clientGenerateBtn',
    5: 'stepPublish',
    6: 'crmCard'
  };
  const target = document.getElementById(targetByStep[step]);
  if (target) setTimeout(() => target.scrollIntoView({behavior:'smooth', block:'center'}), 80);
}

function hpOpenFlyerEditor() {
  const client = document.getElementById('clientProfileSelect');
  const leads = document.getElementById('clientLeadsSelect');
  const profile = client && client.value ? client.value : '';
  const leadset = leads && leads.value ? leads.value : '';
  const url = `/flyer-editor?profile=${encodeURIComponent(profile)}&leads=${encodeURIComponent(leadset)}`;
  window.open(url, '_blank');
}

function hpPrimaryAction() {
  const current = Array.from(document.body.classList).find(c => c.startsWith('hp-view-')) || '';
  if (current === 'hp-view-campaigns') return hpSetView('wizard');
  if (current === 'hp-view-intelligence' && typeof intelligenceRefresh === 'function') return intelligenceRefresh();
  const start = document.getElementById('startBtn');
  if (start && !start.disabled) return start.click();
  hpSetView('wizard');
}

function hpInstallRedesign() {
  document.body.classList.add('hp-ui-v2','hp-intelligence-theme');
  const saved = (() => { try { return localStorage.getItem('homepilot.facadepilot.view'); } catch (e) { return null; } })();
  const savedDrawer = (() => { try { return localStorage.getItem('homepilot.facadepilot.targetCollapsed'); } catch (e) { return null; } })();
  document.body.classList.toggle('hp-target-collapsed', savedDrawer === null ? true : savedDrawer === '1');
  hpTagCards();
  document.querySelectorAll('[data-hp-view-button]').forEach(btn => {
    btn.addEventListener('click', () => hpSetView(btn.dataset.hpViewButton));
  });
  document.querySelectorAll('[data-hp-step]').forEach(btn => {
    btn.addEventListener('click', () => hpSetStep(btn.dataset.hpStep));
  });
  ['clientProfileSelect','clientLeadsSelect','clientPublicBaseUrl'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', hpSyncTopbar);
  });
  document.querySelectorAll('input[name="clientBrandMode"]').forEach(el => el.addEventListener('change', hpSyncTopbar));
  hpSetView(saved || 'campaigns');
  if (typeof loadFieldPhotos === 'function') setTimeout(loadFieldPhotos, 0);
  hpSyncTopbar();
  updateTargetDrawerButton();
  setInterval(hpSyncTopbar, 1500);
}
setTimeout(hpInstallRedesign, 0);


const STEP_ICONS = {
  pending: (n) => n,
  running: () => '<div class="spinner-sm"></div>',
  done: () => 'OK',
  skipped: () => '--',
};

// Load gemeenten list
async function loadGemeenten() {
  const r = await fetch('/api/gemeenten');
  const g = await r.json();
  const dl = document.getElementById('gemeenten-list');
  for (const [code, naam] of Object.entries(g)) {
    const opt = document.createElement('option');
    opt.value = code;
    opt.label = `${naam} (${code})`;
    dl.appendChild(opt);
  }
}

// Load CSV files
async function loadCSVs() {
  const r = await fetch('/api/files');
  const files = await r.json();
  const sel = document.getElementById('inputCsv');
  sel.innerHTML = '<option value="">-- Nieuw (via adresselectie) --</option>';
  for (const f of files) {
    const opt = document.createElement('option');
    opt.value = f.name;
    opt.textContent = `${f.name} (${f.rows} rijen)`;
    sel.appendChild(opt);
  }
  sel.value = '';
  document.getElementById('stepAdres').checked = true;
  document.getElementById('niscode').disabled = false;
  applyPipelineMode();
}

let _clientCampaignOptions = {profiles: [], leads: []};

const RENDER_PRESET_SETS = {
  facadepilot: [
    {value:'moderne_crepi', title:'Moderne crepi-afwerking', meta:'Strakke witte crepi, donkere ramen/deuren, moderne look'},
    {value:'baksteen_rejoint', title:'Baksteen reinigen + hervoegen', meta:'Originele baksteen behouden, opgefrist met nieuwe voeg'},
    {value:'isolatie_gevelbekleding', title:'Buitenisolatie + gevelbekleding', meta:'Isolatie met lichte crepi en donkere gevelpanelen'},
    {value:'totaalrenovatie', title:'Totale gevelrenovatie', meta:'Mix van crepi, natuursteen, houtaccenten en verlichting'},
  ],
  windowpilot: [
    {value:'window_antraciet', title:'Antraciet ramen en deuren', meta:'Slanke donkere profielen, moderne glaspartijen en coherent buitenschrijnwerk'},
    {value:'window_wit', title:'Witte ramen en deuren', meta:'Frisse witte profielen met realistische glasreflecties en afgewerkte dagkanten'},
    {value:'window_houtlook', title:'Houtlook of warme tint', meta:'Warmere premium uitstraling voor landelijke of klassieke woningen'},
    {value:'window_screens', title:'Ramen met screens', meta:'Nieuwe ramen met subtiele geïntegreerde zonwering waar logisch'},
    {value:'window_rolluiken', title:'Ramen met rolluiken', meta:'Nieuwe ramen met discrete rolluiken en realistische geleiders/kasten'},
    {value:'window_totaal', title:'Ramen deuren screens rolluiken', meta:'Volledige buitenschrijnwerkrenovatie in één samenhangende look'},
  ],
};

function currentRenderPresetSet() {
  return RENDER_PRESET_SETS[getClientBrandMode()] || RENDER_PRESET_SETS.facadepilot;
}

function defaultRenderPresetKey() {
  return currentRenderPresetSet()[0].value;
}

function renderPresetOptionsForBrand() {
  const isWindowPilot = getClientBrandMode() === 'windowpilot';
  const renderLabel = document.getElementById('renderPresetLabel');
  const manualLabel = document.getElementById('manualPresetLabel');
  if (renderLabel) renderLabel.textContent = isWindowPilot
    ? '3. Ramen en zonwering voor renders'
    : '3. Gevelafwerkingen voor renders';
  if (manualLabel) manualLabel.textContent = isWindowPilot
    ? 'Ramen en zonwering voor dit adres'
    : 'Afwerkingen voor dit adres';
  const presets = currentRenderPresetSet();
  const html = presets.map((preset, index) => `
    <label class="preset-option">
      <input type="checkbox" value="${escapeHtml(preset.value)}" ${index === 0 ? 'checked' : ''}>
      <span><span class="preset-title">${escapeHtml(preset.title)}</span><span class="preset-meta">${escapeHtml(preset.meta)}</span></span>
    </label>
  `).join('');
  ['presetOptions', 'manualPresetOptions'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  });
  const hiddenPreset = document.getElementById('facadePreset');
  if (hiddenPreset) hiddenPreset.value = defaultRenderPresetKey();
  document.querySelectorAll('#presetOptions input, #manualPresetOptions input').forEach(input => {
    input.addEventListener('change', syncPresetSummary);
  });
  syncPresetSummary();
}

function selectedClientProfileOption() {
  const profileSel = document.getElementById('clientProfileSelect');
  return profileSel ? profileSel.selectedOptions[0] : null;
}

function getClientBrandMode() {
  return (document.querySelector('input[name="clientBrandMode"]:checked') || {}).value || 'windowpilot';
}

function setClientBrandMode(mode) {
  const safe = mode === 'facadepilot' ? 'facadepilot' : 'windowpilot';
  const input = document.querySelector(`input[name="clientBrandMode"][value="${safe}"]`);
  if (input) input.checked = true;
  renderPresetOptionsForBrand();
}

function updateClientPublicBaseUrl(force=false) {
  const selected = selectedClientProfileOption();
  const input = document.getElementById('clientPublicBaseUrl');
  if (!selected || !input) return;
  const current = input.value.trim();
  const autoManaged = !current || current.includes('windowpilot.be/r') || current.includes('facadepilot.be/r');
  if (!force && !autoManaged) return;
  const base = getClientBrandMode() === 'facadepilot'
    ? 'https://www.facadepilot.be/r'
    : 'https://www.windowpilot.be/r';
  input.value = `${base}/${selected.dataset.key || 'klant'}`;
}

async function refreshClientCampaignOptions() {
  const r = await fetch('/api/client_campaign_options');
  _clientCampaignOptions = await r.json();
  const profileSel = document.getElementById('clientProfileSelect');
  const leadsSel = document.getElementById('clientLeadsSelect');
  profileSel.innerHTML = '';
  leadsSel.innerHTML = '';

  for (const profile of _clientCampaignOptions.profiles || []) {
    const opt = document.createElement('option');
    opt.value = profile.path;
    opt.textContent = profile.name;
    opt.dataset.key = profile.key;
    opt.dataset.brandName = profile.brand_name || profile.name || '';
    opt.dataset.defaultBrand = profile.default_brand || 'windowpilot';
    opt.dataset.phone = profile.phone || '';
    opt.dataset.email = profile.email || '';
    opt.dataset.websiteUrl = profile.website_url || '';
    opt.dataset.accentColor = profile.accent_color || '';
    opt.dataset.suggestedLeads = profile.suggested_leads || '';
    opt.dataset.suggestedOutputRoot = profile.suggested_output_root || '';
    opt.dataset.suggestedPublicBaseUrl = profile.suggested_public_base_url || '';
    profileSel.appendChild(opt);
  }
  for (const leads of _clientCampaignOptions.leads || []) {
    const opt = document.createElement('option');
    opt.value = leads.path;
    opt.textContent = `${leads.name} (${leads.count} leads)`;
    leadsSel.appendChild(opt);
  }
  applyClientProfileDefaults();
  updateClientCampaignStatus('Klantprofielen en leads geladen.', 'ok');
}

function applyClientProfileDefaults() {
  const profileSel = document.getElementById('clientProfileSelect');
  const leadsSel = document.getElementById('clientLeadsSelect');
  const selected = profileSel.selectedOptions[0];
  if (!selected) {
    updateClientPathSummary();
    return;
  }
  setClientBrandMode(selected.dataset.defaultBrand || 'windowpilot');
  const suggestedLeads = selected.dataset.suggestedLeads || '';
  if (suggestedLeads) {
    const match = Array.from(leadsSel.options).find(opt => opt.value === suggestedLeads);
    if (match) leadsSel.value = suggestedLeads;
  }
  document.getElementById('clientOutputRoot').value = selected.dataset.suggestedOutputRoot || '';
  document.getElementById('clientPublicBaseUrl').value = selected.dataset.suggestedPublicBaseUrl || '';
  updateClientPublicBaseUrl(true);
  if (selected.dataset.brandName) {
    document.getElementById('builderNaam').value = selected.dataset.brandName;
  }
  if (selected.dataset.phone) {
    document.getElementById('builderTel').value = selected.dataset.phone;
  }
  if (selected.dataset.accentColor) {
    const color = selected.dataset.accentColor;
    if (/^#[0-9a-fA-F]{6}$/.test(color)) {
      document.getElementById('accentColor').value = color;
      document.getElementById('accentColorText').value = color;
    }
  }
  const leadValue = leadsSel.value || suggestedLeads;
  if (leadValue) {
    const parts = leadValue.split('/');
    parts.pop();
    document.getElementById('clientSourceDir').value = parts.join('/') || '';
  }
  const profileEditor = document.getElementById('clientProfileEditor');
  const leadsEditor = document.getElementById('clientLeadsEditor');
  if (profileEditor) profileEditor.value = '';
  if (leadsEditor) leadsEditor.value = '';
  updateClientPathSummary();
  setClientEditorStatus('Klant gekozen. Laad de bestanden om copy of fotopaden te bewerken.');
}

function clientSelectedLeadPath() {
  const leadsSel = document.getElementById('clientLeadsSelect');
  return leadsSel ? (leadsSel.value || '') : '';
}

function clientSourcePathFromLead() {
  const source = document.getElementById('clientSourceDir')?.value || '';
  if (source) return source;
  const lead = clientSelectedLeadPath();
  if (!lead) return '';
  const parts = lead.split('/');
  parts.pop();
  return parts.join('/') || '';
}

function updateClientPathSummary() {
  const profilePath = document.getElementById('clientProfileSelect')?.value || '';
  const leadsPath = clientSelectedLeadPath();
  const sourcePath = clientSourcePathFromLead();
  const outputPath = document.getElementById('clientOutputRoot')?.value || '';
  const publicBase = document.getElementById('clientPublicBaseUrl')?.value || '';

  const setText = (id, value, fallback) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value || fallback;
  };
  setText('clientProfilePathText', profilePath, 'Nog geen klant gekozen');
  setText('clientLeadsPathText', leadsPath, 'Nog geen leadsbestand gekozen');
  setText('clientSourcePathText', sourcePath, 'Nog geen beeldenmap ingesteld');
  setText('clientOutputPathText', outputPath, 'Nog geen outputmap ingesteld');
  setText('clientPublicBaseText', publicBase, 'Nog geen QR-base ingesteld');
}

async function openClientPath(kind) {
  const path =
    kind === 'profile' ? (document.getElementById('clientProfileSelect')?.value || '') :
    kind === 'leads' ? clientSelectedLeadPath() :
    kind === 'output' ? (document.getElementById('clientOutputRoot')?.value || '') :
    clientSourcePathFromLead();
  if (!path) {
    setClientEditorStatus('Geen pad om te openen.', 'error');
    return;
  }
  const params = new URLSearchParams();
  params.set('path', path);
  if (kind === 'output') params.set('create', '1');
  try {
    const r = await fetch('/api/open_local_path?' + params.toString());
    const data = await r.json();
    if (!data.ok) throw new Error(data.error || 'openen mislukt');
    setClientEditorStatus('Geopend in Finder: ' + data.path, 'ok');
  } catch (e) {
    setClientEditorStatus('Openen mislukt: ' + e.message, 'error');
  }
}

function clientCampaignBody() {
  const body = new URLSearchParams();
  body.set('profile', document.getElementById('clientProfileSelect').value || '');
  body.set('leads', document.getElementById('clientLeadsSelect').value || '');
  body.set('source_dir', document.getElementById('clientSourceDir').value || '');
  body.set('output_root', document.getElementById('clientOutputRoot').value || '');
  body.set('public_base_url', document.getElementById('clientPublicBaseUrl').value || '');
  body.set('brand_mode', getClientBrandMode());
  body.set('skip_renders', document.getElementById('clientSkipRenders').checked ? '1' : '0');
  return body;
}

function setClientEditorStatus(text, tone='') {
  const el = document.getElementById('clientEditorStatus');
  if (!el) return;
  el.textContent = text;
  el.style.color = tone === 'ok' ? '#4ade80' : (tone === 'error' ? '#fca5a5' : '#94a3b8');
}

async function loadEditableJson(path, editorId) {
  if (!path) return false;
  const r = await fetch('/api/client_campaign_file?path=' + encodeURIComponent(path));
  const data = await r.json();
  if (!data.ok) throw new Error(data.error || 'laden mislukt');
  document.getElementById(editorId).value = data.content || '';
  return true;
}

async function loadClientEditableFiles() {
  try {
    const profilePath = document.getElementById('clientProfileSelect').value || '';
    const leadsPath = document.getElementById('clientLeadsSelect').value || '';
    await loadEditableJson(profilePath, 'clientProfileEditor');
    if (leadsPath) await loadEditableJson(leadsPath, 'clientLeadsEditor');
    setClientEditorStatus('Klantprofiel en leads geladen. Je kunt nu copy of fotopaden aanpassen.', 'ok');
  } catch (e) {
    setClientEditorStatus('Laden mislukt: ' + e.message, 'error');
  }
}

async function saveClientEditableFile(kind) {
  const path = kind === 'profile'
    ? document.getElementById('clientProfileSelect').value
    : document.getElementById('clientLeadsSelect').value;
  const editorId = kind === 'profile' ? 'clientProfileEditor' : 'clientLeadsEditor';
  const content = document.getElementById(editorId).value || '';
  if (!path || !content.trim()) {
    setClientEditorStatus('Niets om op te slaan.', 'error');
    return;
  }
  const body = new URLSearchParams();
  body.set('path', path);
  body.set('content', content);
  try {
    const r = await fetch('/api/client_campaign_file_save', {method: 'POST', body});
    const data = await r.json();
    if (!data.ok) throw new Error(data.error || 'opslaan mislukt');
    document.getElementById(editorId).value = data.content || content;
    setClientEditorStatus((kind === 'profile' ? 'Klantprofiel' : 'Leadsbestand') + ' opgeslagen.', 'ok');
    if (kind === 'profile') refreshClientCampaignOptions();
  } catch (e) {
    setClientEditorStatus('Opslaan mislukt: ' + e.message, 'error');
  }
}

function updateClientCampaignStatus(text, tone='') {
  const status = document.getElementById('clientCampaignStatus');
  status.textContent = text;
  status.style.color = tone === 'ok' ? '#4ade80' : (tone === 'warn' ? '#fbbf24' : (tone === 'error' ? '#fca5a5' : '#94a3b8'));
}

async function validateClientCampaign() {
  const body = clientCampaignBody();
  body.set('strict_assets', '1');
  const log = document.getElementById('clientCampaignLog');
  log.style.display = 'block';
  log.textContent = 'Valideren...';
  const r = await fetch('/api/client_campaign_validate', {method: 'POST', body});
  const data = await r.json();
  log.textContent = data.output || data.error || '';
  updateClientCampaignStatus(data.ok ? 'Validatie OK. Klaar om te genereren.' : 'Validatie heeft nog issues.', data.ok ? 'ok' : 'error');
}

async function generateClientCampaign() {
  const btn = document.getElementById('clientGenerateBtn');
  const body = clientCampaignBody();
  if (!body.get('profile') || !body.get('leads') || !body.get('output_root') || !body.get('public_base_url')) {
    alert('Kies profiel, leadsbestand, outputmap en publieke QR-base.');
    return;
  }
  btn.disabled = true;
  document.getElementById('clientCampaignLog').style.display = 'block';
  updateClientCampaignStatus('Generator wordt gestart...', 'warn');
  const r = await fetch('/api/client_campaign_generate', {method: 'POST', body});
  const data = await r.json();
  if (!data.ok) {
    btn.disabled = false;
    updateClientCampaignStatus(data.error || 'Start mislukt', 'error');
    return;
  }
  pollClientCampaign();
}

async function pollClientCampaign() {
  const r = await fetch('/api/client_campaign_state');
  const state = await r.json();
  const log = document.getElementById('clientCampaignLog');
  const btn = document.getElementById('clientGenerateBtn');
  if (state.log) {
    log.style.display = 'block';
    log.textContent = state.log;
    log.scrollTop = log.scrollHeight;
  }
  if (state.status === 'running') {
    btn.disabled = true;
    updateClientCampaignStatus(state.message || 'Clientcampagne loopt...', 'warn');
    setTimeout(pollClientCampaign, 1200);
  } else {
    btn.disabled = false;
    if (state.status === 'done') {
      updateClientCampaignStatus(`Klaar. Output: ${state.output_root}`, 'ok');
    } else if (state.status === 'error') {
      updateClientCampaignStatus(state.error || state.message || 'Clientcampagne mislukt', 'error');
    }
  }
}

// Load module status
async function loadModules() {
  const r = await fetch('/api/modules');
  const m = await r.json();
  for (const [key, avail] of Object.entries(m)) {
    const map = {adresselectie:'modAdres',lead_scoring:'modScore',render:'modRender',flyer:'modFlyer'};
    const el = document.getElementById(map[key]);
    if (el) {
      el.textContent = avail ? 'OK' : 'NIET';
      el.className = 'badge ' + (avail ? 'ok' : 'warn');
    }
  }
}

// Live resolve hint (postcode of NIS-code)
let resolveTimer = null;
document.getElementById('niscode').addEventListener('input', function() {
  _mapMode = 'leads';
  const csv = document.getElementById('inputCsv');
  if (csv.value) {
    csv.value = '';
    document.getElementById('stepAdres').checked = true;
    document.getElementById('niscode').disabled = false;
  }
  const hint = document.getElementById('gemeenteHint');
  const val = this.value.trim();
  clearTimeout(resolveTimer);
  if (!val || val.length < 4) { hint.textContent = ''; hint.style.color = '#475569'; return; }
  resolveTimer = setTimeout(async () => {
    try {
      const r = await fetch('/api/resolve?code=' + encodeURIComponent(val));
      const d = await r.json();
      if (d.ok) {
        hint.innerHTML = '<strong>' + d.naam + '</strong> (NIS ' + d.niscode + ')';
        hint.style.color = '#4ade80';
      } else if (d.error) {
        hint.textContent = d.error;
        hint.style.color = '#fca5a5';
      } else {
        hint.textContent = '';
      }
    } catch(e) { hint.textContent = ''; }
  }, 300);
});

// Toggle adresselectie vs CSV input
document.getElementById('inputCsv').addEventListener('change', function() {
  const adresToggle = document.getElementById('stepAdres');
  if (this.value) {
    adresToggle.checked = false;
    document.getElementById('niscode').disabled = true;
  } else {
    adresToggle.checked = true;
    document.getElementById('niscode').disabled = false;
  }
  applyPipelineMode();
});

function getSelectedPresets(groupId) {
  return Array.from(document.querySelectorAll(`#${groupId} input[type="checkbox"]:checked`))
    .map(input => input.value)
    .filter(Boolean);
}

function setPresetSelection(groupId, presets) {
  const wanted = new Set((presets && presets.length ? presets : [defaultRenderPresetKey()]));
  document.querySelectorAll(`#${groupId} input[type="checkbox"]`).forEach(input => {
    input.checked = wanted.has(input.value);
  });
  syncPresetSummary();
}

function syncPresetSummary() {
  const selected = getSelectedPresets('presetOptions');
  const primary = selected[0] || defaultRenderPresetKey();
  const hidden = document.getElementById('facadePreset');
  if (hidden) hidden.value = primary;
  const isWindowPilot = getClientBrandMode() === 'windowpilot';

  const cost = document.getElementById('presetCost');
  if (cost) {
    cost.textContent = selected.length <= 1
      ? (isWindowPilot ? '1 schrijnwerkoptie per woning' : '1 afwerking per woning')
      : `${selected.length} ${isWindowPilot ? 'schrijnwerkopties' : 'afwerkingen'} per woning · ongeveer ${selected.length}x renderkost`;
  }

  const manualSelected = getSelectedPresets('manualPresetOptions');
  const manualCost = document.getElementById('manualPresetCost');
  if (manualCost) {
    manualCost.textContent = manualSelected.length <= 1
      ? (isWindowPilot ? '1 schrijnwerkoptie voor handmatige adressen' : '1 afwerking voor handmatige adressen')
      : `${manualSelected.length} ${isWindowPilot ? 'schrijnwerkopties' : 'afwerkingen'} voor handmatige adressen · ongeveer ${manualSelected.length}x renderkost`;
  }
}

function requirePresetSelection(groupId) {
  const selected = getSelectedPresets(groupId);
  if (selected.length) return selected;
  const first = document.querySelector(`#${groupId} input[type="checkbox"]`);
  if (first) {
    first.checked = true;
    syncPresetSummary();
    return [first.value];
  }
  return [defaultRenderPresetKey()];
}

document.querySelectorAll('#presetOptions input, #manualPresetOptions input').forEach(input => {
  input.addEventListener('change', syncPresetSummary);
});
renderPresetOptionsForBrand();

function getPipelineMode() {
  const checked = document.querySelector('input[name="pipelineMode"]:checked');
  return checked ? checked.value : 'full';
}

function setPipelineMode(mode) {
  const wanted = mode === 'map_only' ? 'map_only' : 'full';
  const radio = document.querySelector(`input[name="pipelineMode"][value="${wanted}"]`);
  if (radio) radio.checked = true;
  applyPipelineMode();
}

function applyPipelineMode() {
  const mapOnly = getPipelineMode() === 'map_only';
  const startBtn = document.getElementById('startBtn');
  const note = document.getElementById('pipelineModeNote');
  const inputCsv = document.getElementById('inputCsv');
  const forcedOff = ['stepRender', 'stepFlyer', 'stepLanding', 'stepPublish', 'stepEmail'];

  forcedOff.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (mapOnly) {
      if (el.dataset.mapOnlyPrev === undefined) el.dataset.mapOnlyPrev = el.checked ? '1' : '0';
      el.checked = false;
    } else if (el.dataset.mapOnlyPrev !== undefined) {
      el.checked = el.dataset.mapOnlyPrev === '1';
      delete el.dataset.mapOnlyPrev;
    }
    el.disabled = mapOnly;
  });

  const stepScore = document.getElementById('stepScore');
  if (stepScore && mapOnly) {
    stepScore.checked = true;
  }
  const stepAdres = document.getElementById('stepAdres');
  if (stepAdres && mapOnly && inputCsv && !inputCsv.value) {
    stepAdres.checked = true;
  }

  if (startBtn && !startBtn.disabled) {
    startBtn.textContent = mapOnly ? 'Maak leads + kaart' : 'Start Pipeline';
  }
  if (note) {
    note.textContent = mapOnly
      ? 'Deze run stopt zodra de kaart en selectielijst klaarstaan. Renders, flyers en QR-sites blijven uit.'
      : 'Gebruik Leads/Map only om eerst rustig woningen te selecteren zonder renders te starten.';
  }
}

document.querySelectorAll('input[name="pipelineMode"]').forEach(input => {
  input.addEventListener('change', applyPipelineMode);
});

// ─── RENDER-KOSTENRAMING (Fase F) ───────────────────────────────────────────
// Vraagt vóór de render-stap een schatting op en laat de gebruiker bevestigen.
async function confirmRenderCost(body) {
  if (body.get('step_render') !== '1') return true;
  const nEst = parseInt(document.getElementById('renderTop').value, 10);
  if (!(nEst > 0)) return true;
  try {
    const er = await fetch('/api/render_estimate?n=' + nEst);
    const est = await er.json();
    if (est && typeof est.cost_eur === 'number' && typeof est.budget_eur === 'number') {
      const vraag = 'Geschatte kost: €' + est.cost_eur.toFixed(2) + ' voor ' + est.n +
        ' renders (budget €' + est.budget_eur.toFixed(2) + '). Doorgaan?';
      if (!confirm(vraag)) return false;
    }
  } catch (e) { /* raming niet beschikbaar — start gewoon */ }
  return true;
}

async function startPipeline() {
  const niscode = document.getElementById('niscode').value.trim();
  const inputCsv = document.getElementById('inputCsv').value;
  const pipelineMode = getPipelineMode();
  const mapOnly = pipelineMode === 'map_only';

  if (!niscode && !inputCsv) {
    return alert('Voer een postcode (bv. 3300) of NIS-code (bv. 24107) in, of kies een bestaand CSV bestand.');
  }

  const body = new URLSearchParams();
  body.set('pipeline_mode', pipelineMode);
  if (niscode) body.set('niscode', niscode);
  if (inputCsv) body.set('input_csv', inputCsv);
  body.set('client_profile', document.getElementById('clientProfileSelect').value || '');
  body.set('client_brand_mode', getClientBrandMode());
  body.set('target_regions', document.getElementById('targetRegions').value || '');
  body.set('target_house_types', getSelectedPresets('targetHouseTypes').join(','));
  body.set('income_target', document.getElementById('incomeTarget').value || 'any');
  body.set('min_woning', document.getElementById('minWoning').value || '60');
  body.set('max_woning', document.getElementById('maxWoning').value || '350');
  body.set('max_bebouwd_ratio', document.getElementById('maxBebouwdRatio').value || '0.75');
  body.set('render_top', document.getElementById('renderTop').value || '');
  body.set('render_klassen', document.getElementById('renderKlassen').value || '');
  body.set('builder_naam', document.getElementById('builderNaam').value || '');
  body.set('builder_tel', document.getElementById('builderTel').value || '');
  const selectedPresets = requirePresetSelection('presetOptions');
  body.set('facade_preset', selectedPresets[0] || defaultRenderPresetKey());
  body.set('facade_presets', selectedPresets.join(','));
  body.set('flyer_style', 'auto');
  body.set('flyer_styles', 'auto');
  body.set('quality_check', document.getElementById('qualityCheck').checked ? '1' : '0');
  body.set('multi_preset', selectedPresets.length > 1 ? '1' : '0');
  body.set('auto_preset', document.getElementById('autoPreset').checked ? '1' : '0');

  // Steps
  body.set('step_adres', document.getElementById('stepAdres').checked ? '1' : '0');
  body.set('step_score', document.getElementById('stepScore').checked ? '1' : '0');
  body.set('step_render', mapOnly ? '0' : (document.getElementById('stepRender').checked ? '1' : '0'));
  body.set('step_flyer', mapOnly ? '0' : (document.getElementById('stepFlyer').checked ? '1' : '0'));
  body.set('step_landing', mapOnly ? '0' : (document.getElementById('stepLanding').checked ? '1' : '0'));
  body.set('step_publish', mapOnly ? '0' : (document.getElementById('stepPublish').checked ? '1' : '0'));
  body.set('step_email', mapOnly ? '0' : (document.getElementById('stepEmail').checked ? '1' : '0'));
  body.set('vergunning_filter', document.getElementById('vergunningFilter').checked ? '1' : '0');
  body.set('crm_sync', document.getElementById('crmSync').checked ? '1' : '0');

  if (!(await confirmRenderCost(body))) return;

  const r = await fetch('/api/start', { method: 'POST', body });
  if (!r.ok) {
    const t = await r.text();
    return alert('Start mislukt: ' + t);
  }

  document.getElementById('startBtn').disabled = true;
  document.getElementById('cancelBtn').style.display = 'block';
  document.getElementById('doneBanner').classList.remove('active');
}

async function cancelPipeline() {
  await fetch('/api/cancel', { method: 'POST' });
}

// Animated dots for "Bezig..."
let dotCount = 0;
setInterval(() => {
  dotCount = (dotCount + 1) % 4;
  const el = document.getElementById('elapsedDots');
  if (el) el.textContent = '.'.repeat(dotCount || 1);
}, 500);

function formatElapsed(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
}

function updateUI(s) {
  // Elapsed timer
  const bar = document.getElementById('elapsedBar');
  if (s.running || s.done) {
    bar.classList.remove('hidden');
    if (s.start_time) {
      const now = Date.now() / 1000;
      const elapsed = s.done ? 0 : (now - s.start_time);
      if (!s.done) document.getElementById('elapsedTime').textContent = formatElapsed(elapsed);
    }
    document.getElementById('elapsedGemeente').textContent = s.gemeente ? s.gemeente : '';
    if (s.done) {
      document.getElementById('elapsedStatus').innerHTML = 'Voltooid';
      document.getElementById('elapsedStatus').style.color = '#4ade80';
    } else if (s.error) {
      document.getElementById('elapsedStatus').innerHTML = 'Fout';
      document.getElementById('elapsedStatus').style.color = '#fca5a5';
    } else {
      const stepLabels = {adresselectie:'Adresselectie',scoring:'Scoring',render:'Renders',flyer:'Flyers',landing:'Landing pages',publish:'Online publicatie',email:'E-mails'};
      const label = stepLabels[s.current_step] || 'Bezig';
      document.getElementById('elapsedStatus').innerHTML = label + '<span class="elapsed-dots" id="elapsedDots">.</span>';
      document.getElementById('elapsedStatus').style.color = '#60a5fa';
    }
  } else {
    bar.classList.add('hidden');
  }

  // Steps
  const stepNames = ['adresselectie','scoring','render','flyer','landing','publish','email'];
  const nums = {adresselectie:'1',scoring:'2',render:'3',flyer:'4',landing:'5',publish:'6',email:'7'};

  for (const name of stepNames) {
    const step = s.steps[name];
    const el = document.getElementById('step-' + name);
    const icon = document.getElementById('icon-' + name);
    const msg = document.getElementById('msg-' + name);
    const barFill = document.getElementById('bar-' + name);

    el.className = 'step ' + step.status;
    icon.className = 'step-icon ' + step.status;

    if (step.status === 'running') {
      icon.innerHTML = '<div class="spinner-sm"></div>';
    } else if (step.status === 'done') {
      icon.innerHTML = 'OK';
      icon.style.color = '#4ade80';
      icon.style.fontWeight = '700';
      icon.style.fontSize = '11px';
    } else if (step.status === 'skipped') {
      icon.innerHTML = '--';
      icon.style.color = '#94a3b8';
      icon.style.fontSize = '11px';
    } else {
      icon.textContent = nums[name];
      icon.style.color = '';
      icon.style.fontWeight = '';
      icon.style.fontSize = '';
    }

    msg.textContent = step.message || 'Wacht op start';

    if (step.total > 0) {
      barFill.style.width = Math.round((step.progress / step.total) * 100) + '%';
    }
  }

  // Cost tracker widget
  if (s.costs && (s.running || s.done) && (s.costs.streetview_photos > 0 || s.costs.quality_checks > 0 || s.costs.renders_done > 0)) {
    const costCard = document.getElementById('costCard');
    costCard.style.display = 'block';
    costCard.classList.remove('hidden');
    document.getElementById('costTotal').textContent = '$' + s.costs.total_usd.toFixed(2);
    document.getElementById('costSV').textContent = '$' + s.costs.streetview_usd.toFixed(2);
    document.getElementById('costSVPhotos').textContent = s.costs.streetview_photos;
    document.getElementById('costQC').textContent = '$' + s.costs.quality_usd.toFixed(3);
    document.getElementById('costQCDone').textContent = s.costs.quality_checks;
    document.getElementById('costQCFailed').textContent = s.costs.quality_failed;
    document.getElementById('costRender').textContent = '$' + s.costs.render_usd.toFixed(2);
    document.getElementById('costRenderDone').textContent = s.costs.renders_done;
    // Bespaarde renderkosten = aantal qc-fails * $0.10
    if (s.costs.renders_skipped_quality > 0) {
      const saved = s.costs.renders_skipped_quality * 0.10;
      const savedEl = document.getElementById('costSavings');
      savedEl.style.display = 'block';
      document.getElementById('costSavedAmount').textContent =
        'Quality check bespaarde ~$' + saved.toFixed(2) + ' op ' + s.costs.renders_skipped_quality + ' slechte foto(s)';
    }
  }

  // Log
  const logEl = document.getElementById('log');
  const wasBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 10;
  logEl.textContent = (s.log || []).join('\n');
  if (wasBottom) logEl.scrollTop = logEl.scrollHeight;

  // Output files (clickable)
  if (s.output_files && s.output_files.length > 0) {
    const card = document.getElementById('outputCard');
    card.style.display = 'block';
    const list = document.getElementById('fileList');
    list.innerHTML = '';
    for (const f of s.output_files) {
      const li = document.createElement('li');
      const icon = f.name.endsWith('/') ? '[DIR]' : '[CSV]';
      li.innerHTML = `<div><span class="file-icon">${icon}</span>${f.name}</div>
                       <div class="file-label">${f.label}${f.rows ? ' / ' + f.rows + ' rijen' : ''}</div>`;
      li.onclick = () => showPreview(f);
      list.appendChild(li);
    }
  }

  // Show render card when renders exist
  if (s.done || (s.steps.render && s.steps.render.status === 'done')) {
    loadRenderGallery();
  }

  // Done banner
  if (s.done) {
    const banner = document.getElementById('doneBanner');
    banner.classList.add('active');
    let summary = '';
    const mapOnlyDone = s.summary && s.summary.map_only;
    const doneTitle = document.getElementById('doneTitle');
    if (doneTitle) doneTitle.textContent = mapOnlyDone ? 'Kaartselectie klaar!' : 'Pipeline voltooid!';
    if (s.summary.scoring) {
      summary += `Scoring: ${s.summary.scoring.total} leads (gem. ${s.summary.scoring.avg_score}). `;
    }
    if (mapOnlyDone) {
      summary += 'Klik op de leads op de kaart en selecteer welke woningen naar de render-pipeline mogen.';
    } else {
      summary += `${s.output_files.length} output bestanden gegenereerd.`;
    }
    document.getElementById('doneSummary').textContent = summary;
  }

  // Buttons
  document.getElementById('startBtn').disabled = s.running;
  document.getElementById('cancelBtn').style.display = s.running ? 'block' : 'none';
}

async function poll() {
  try {
    const r = await fetch('/api/status');
    if (r.ok) {
      const s = await r.json();
      updateUI(s);
    }
  } catch(e) {}
}

// ── Preview panel ──────────────────────────────────────────────
function showPreview(f) {
  const panel = document.getElementById('previewPanel');
  const title = document.getElementById('previewTitle');
  const content = document.getElementById('previewContent');

  if (f.name.includes('renders/')) {
    document.getElementById('renderCard').style.display = 'block';
    loadRenderGallery();
    panel.classList.remove('active');
    return;
  }
  if (f.name.includes('flyers/')) {
    panel.classList.add('active');
    title.textContent = 'Flyers';
    content.innerHTML = '<p style="color:#94a3b8;font-size:13px">Flyer PDFs staan in de flyers/ map. Open ze via Finder.</p>';
    loadFlyerList(content);
    return;
  }
  if (f.name.includes('landing/')) {
    panel.classList.add('active');
    title.textContent = 'QR-landingspagina’s';
    content.innerHTML = '<p style="color:#94a3b8;font-size:13px">Lokaal gegenereerde websites achter de QR-codes. Bekijk en keur ze goed voor publicatie.</p>';
    loadLandingList(content, f.name);
    return;
  }
  if (f.name.endsWith('.csv')) {
    panel.classList.add('active');
    title.textContent = f.name;
    content.innerHTML = `<p style="color:#94a3b8;font-size:13px">${f.label} -- ${f.rows || '?'} rijen</p>
      <p style="margin-top:8px;font-size:12px;color:#475569">CSV bestand beschikbaar in de projectmap.</p>`;
    return;
  }
  panel.classList.remove('active');
}

async function loadFlyerList(container) {
  try {
    const r = await fetch('/api/outputs');
    const files = await r.json();
    const flyers = files.filter(f => f.name.includes('flyers/'));
    if (flyers.length > 0) {
      container.innerHTML += '<p style="margin-top:8px;color:#94a3b8;font-size:12px">' + flyers[0].name + '</p>';
    }
  } catch(e) {}
}

async function loadLandingList(container, dirName) {
  try {
    const cleanDir = (dirName || '').replace(/\s*\([^)]*\)\s*/g, '').trim();
    const r = await fetch('/api/landing_pages?dir=' + encodeURIComponent(cleanDir));
    const pages = await r.json();
    if (!pages.length) {
      container.innerHTML += '<p style="margin-top:10px;color:#fca5a5;font-size:12px">Nog geen landingpagina’s gevonden in deze map.</p>';
      return;
    }
    const cards = pages.map(page => `
      <div class="landing-preview-card">
        <strong>${escapeHtml(page.slug || page.name)}</strong>
        <span>${escapeHtml(page.name)} · ${page.size_kb || 0} KB</span>
        <a href="${escapeHtml(page.preview_url)}" target="_blank" rel="noopener">Open lokale preview</a>
      </div>
    `).join('');
    container.innerHTML += `<div class="landing-preview-list">${cards}</div>`;
  } catch(e) {
    container.innerHTML += '<p style="margin-top:10px;color:#fca5a5;font-size:12px">Landingpagina’s konden niet geladen worden.</p>';
  }
}

// ── Render gallery ──────────────────────────────────────────────
let renderData = [];
let selectedRenderId = null;
let galleryLoaded = false;

async function loadRenderGallery() {
  try {
    const r = await fetch('/api/renders');
    renderData = await r.json();
  } catch(e) { return; }

  if (renderData.length === 0) return;

  const card = document.getElementById('renderCard');
  card.style.display = 'block';

  const gallery = document.getElementById('renderGallery');
  gallery.innerHTML = '';

  for (const item of renderData) {
    const div = document.createElement('div');
    div.className = 'render-thumb' + (item.id === selectedRenderId ? ' selected' : '');
    const imgSrc = item.render ? `/files/${item.render}` : (item.streetview ? `/files/${item.streetview}` : '');
    const label = item.has_render ? '' : 'Geen render';
    const title = item.adres || item.id;
    const variantCount = item.variant_count || (item.variants ? item.variants.length : 0);
    div.innerHTML = `<img src="${imgSrc}" loading="lazy" onerror="this.style.display='none'">
      ${variantCount > 1 ? `<div class="variant-count">${variantCount}</div>` : ''}
      <div class="overlay"><span>${escapeHtml(title).substring(0,42)}${label ? '<br>'+label : ''}</span></div>`;
    div.onclick = (event) => selectRender(item, event.currentTarget);
    gallery.appendChild(div);
  }
  galleryLoaded = true;
}

function selectRender(item, targetEl=null) {
  selectedRenderId = item.id;

  // Update gallery selection
  document.querySelectorAll('.render-thumb').forEach(el => el.classList.remove('selected'));
  if (targetEl) targetEl.classList.add('selected');

  // Update replace panel
  const info = document.getElementById('selectedRenderInfo');
  info.style.display = 'block';

  if (item.streetview) {
    document.getElementById('replaceStreetview').src = '/files/' + item.streetview;
    document.getElementById('replaceStreetview').style.display = 'block';
  }
  if (item.render) {
    document.getElementById('replaceCurrentRender').src = '/files/' + item.render + '?t=' + Date.now();
    document.getElementById('replaceCurrentRender').style.display = 'block';
  }

  // Also show preview
  const panel = document.getElementById('previewPanel');
  panel.classList.add('active');
  const title = document.getElementById('previewTitle');
  title.textContent = item.adres || item.id;
  const content = document.getElementById('previewContent');
  const variants = item.variants && item.variants.length ? item.variants : (
    item.render ? [{preset_label: 'Gevelrenovatie render', render: item.render}] : []
  );
  const variantHtml = variants.map(v => `
    <div class="variant-item">
      <div class="label">${escapeHtml(v.preset_label || 'Render')}</div>
      <img src="/files/${v.render}?t=${Date.now()}" loading="lazy">
    </div>
  `).join('');
  content.innerHTML = `<div class="preview-grid" style="margin-bottom:12px">
    ${item.streetview ? `<div class="preview-item"><div class="label">Street View</div><img src="/files/${item.streetview}"></div>` : ''}
    ${item.render ? `<div class="preview-item"><div class="label">Gekozen hoofdbeeld</div><img src="/files/${item.render}?t=${Date.now()}"></div>` : '<div class="preview-item" style="display:flex;align-items:center;justify-content:center;min-height:200px;color:#fca5a5">Geen render</div>'}
  </div>
  <div class="variant-grid">
    ${variantHtml || '<div style="color:#fca5a5;font-size:13px">Geen afwerkingsvarianten gevonden.</div>'}
  </div>`;
}

function switchRenderTab(tab) {
  document.querySelectorAll('.tab-bar .tab').forEach(el => el.classList.remove('active'));
  event.currentTarget.classList.add('active');

  document.getElementById('renderGalleryTab').style.display = tab === 'gallery' ? 'block' : 'none';
  document.getElementById('renderReplaceTab').style.display = tab === 'replace' ? 'block' : 'none';
}

function copyFacadePrompt() {
  const prompt = `Renoveer de gevel van dit huis op de foto. Geef het een moderne uitstraling:
- Strakke witte crepi-afwerking of moderne gevelbekleding
- Nieuwe donkergrijze aluminium ramen en deuren
- Modern afdak boven de voordeur
- Stijlvolle buitenverlichting
- Behoud de vorm en structuur van het huis
- De rest van de omgeving (straat, buren, beplanting) blijft ongewijzigd
- Fotorealistisch resultaat`;

  navigator.clipboard.writeText(prompt).then(() => {
    const btn = event.currentTarget;
    const orig = btn.textContent;
    btn.textContent = 'Gekopieerd!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}

function downloadStreetview() {
  if (!selectedRenderId) return;
  const item = renderData.find(r => r.id === selectedRenderId);
  if (item && item.streetview) {
    const a = document.createElement('a');
    a.href = '/files/' + item.streetview;
    a.download = item.streetview.split('/').pop();
    a.click();
  }
}

// ── Drag & drop upload ──────────────────────────────────────────
const dropZone = document.getElementById('dropZone');
if (dropZone) {
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) uploadRenderFile(e.dataTransfer.files[0]);
  });
}

function handleRenderUpload(e) {
  if (e.target.files.length > 0) uploadRenderFile(e.target.files[0]);
}

async function uploadRenderFile(file) {
  if (!selectedRenderId) {
    alert('Selecteer eerst een render in de galerij om te vervangen.');
    return;
  }

  const status = document.getElementById('uploadStatus');
  status.style.display = 'block';
  status.style.color = '#60a5fa';
  status.textContent = 'Uploaden...';

  const formData = new FormData();
  formData.append('render_id', selectedRenderId);
  formData.append('file', file);

  try {
    const r = await fetch('/api/replace_render', { method: 'POST', body: formData });
    const result = await r.json();
    if (result.ok) {
      status.style.color = '#4ade80';
      status.textContent = `Render vervangen! (${result.size_kb} KB) -- oude versie opgeslagen als backup.`;
      setTimeout(() => {
        loadRenderGallery();
        const item = renderData.find(r => r.id === selectedRenderId);
        if (item) {
          document.getElementById('replaceCurrentRender').src = '/files/' + item.render + '?t=' + Date.now();
        }
      }, 500);
    } else {
      status.style.color = '#fca5a5';
      status.textContent = (result.error || 'Upload mislukt');
    }
  } catch(e) {
    status.style.color = '#fca5a5';
    status.textContent = 'Netwerkfout: ' + e.message;
  }
}

// ── Builder profile ──────────────────────────────────────────
function setFlyerCopyFields(copy) {
  document.querySelectorAll('[data-copy-key]').forEach(field => {
    const key = field.dataset.copyKey;
    field.value = copy && copy[key] !== undefined ? copy[key] : '';
  });
}

function collectFlyerCopyFields() {
  const copy = {};
  document.querySelectorAll('[data-copy-key]').forEach(field => {
    copy[field.dataset.copyKey] = field.value;
  });
  return copy;
}

async function loadProfile() {
  try {
    const r = await fetch('/api/builder_profile');
    const p = await r.json();
    if (p.naam) document.getElementById('builderNaam').value = p.naam;
    if (p.telefoon) document.getElementById('builderTel').value = p.telefoon;
    if (p.accent_color) {
      document.getElementById('accentColor').value = p.accent_color;
      document.getElementById('accentColorText').value = p.accent_color;
    }
    if (p.headline) document.getElementById('headline').value = p.headline;
    setFlyerCopyFields(p.flyer_copy || {});
    if (p.facade_preset) {
      setPresetSelection('presetOptions', [p.facade_preset]);
      setPresetSelection('manualPresetOptions', [p.facade_preset]);
    }
    if (p.logo_path) {
      const fname = p.logo_path.split('/').pop();
      const img = document.getElementById('logoPreview');
      img.src = '/files/' + fname;
      img.style.display = 'block';
    }
  } catch(e) {}
}

async function saveProfile() {
  const body = new URLSearchParams();
  body.set('naam', document.getElementById('builderNaam').value);
  body.set('telefoon', document.getElementById('builderTel').value);
  body.set('accent_color', document.getElementById('accentColor').value);
  body.set('headline', document.getElementById('headline').value);
  body.set('facade_preset', requirePresetSelection('presetOptions')[0] || defaultRenderPresetKey());
  body.set('flyer_copy', JSON.stringify(collectFlyerCopyFields()));

  try {
    const r = await fetch('/api/save_profile', { method: 'POST', body });
    const result = await r.json();
    const status = document.getElementById('profileStatus');
    status.style.display = 'block';
    if (result.ok) {
      status.textContent = 'Profiel opgeslagen!';
      status.style.color = '#4ade80';
    } else {
      status.textContent = 'Fout bij opslaan';
      status.style.color = '#fca5a5';
    }
    setTimeout(() => status.style.display = 'none', 3000);
  } catch(e) {
    console.error(e);
  }
}

async function uploadLogo(e) {
  const file = e.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('logo', file);

  const status = document.getElementById('logoStatus');
  status.style.display = 'block';
  status.textContent = 'Uploaden...';
  status.style.color = '#60a5fa';

  try {
    const r = await fetch('/api/upload_logo', { method: 'POST', body: formData });
    const result = await r.json();
    if (result.ok) {
      status.textContent = 'Logo opgeslagen!';
      status.style.color = '#4ade80';
      const img = document.getElementById('logoPreview');
      img.src = '/files/builder_logo.png?t=' + Date.now();
      img.style.display = 'block';
    } else {
      status.textContent = (result.error || 'Upload mislukt');
      status.style.color = '#fca5a5';
    }
  } catch(e) {
    status.textContent = 'Fout';
    status.style.color = '#fca5a5';
  }
}

// Sync color picker
document.getElementById('accentColor').addEventListener('input', function() {
  document.getElementById('accentColorText').value = this.value;
});


// Database-dashboard v2 intelligence workspace
const INTEL_CLASS_COLORS = {"A+":"#5fbe8f","A":"#5aa2e0","B":"#e2a35c","C":"#5c6b80","D":"#49586c","LEAD":"#8b9bb0","MAN":"#8b9bb0"};
const INTEL_STATUS_COLORS = {"wachtrij":"#5c6b80","verstuurd":"#8b9bb0","gescand":"#5aa2e0","reactie":"#5fbe8f","afspraak":"#e2a35c","no-response":"#e07a6a"};
let intelligenceState = {
  loaded: false,
  tab: 'overview',
  stats: null,
  rows: [],
  total: 0,
  offset: 0,
  limit: 250,
  sort: 'score',
  dir: 'desc',
  selectedId: '',
  charts: {},
  map: null,
  cluster: null,
  mapRows: [],
  rowDebounce: null,
};

function intelligenceParams(extra={}) {
  const params = new URLSearchParams();
  const selected = document.getElementById('clientLeadsSelect')?.value || '';
  if (selected) params.set('campaign', selected);
  if (hpIsDemoDataset()) params.set('demo', '1');
  Object.entries(extra).forEach(([k,v]) => {
    if (v !== undefined && v !== null && String(v) !== '') params.set(k, v);
  });
  return params;
}

function intelligenceMoney(value) {
  const n = Number(value || 0);
  if (n >= 1000000) return '€ ' + (n / 1000000).toFixed(1).replace('.', ',') + 'M';
  if (n >= 1000) return '€ ' + Math.round(n / 1000).toLocaleString('nl-BE') + 'K';
  return '€ ' + Math.round(n).toLocaleString('nl-BE');
}

function intelligenceSetText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function intelligenceShow(tab) {
  intelligenceState.tab = tab;
  document.querySelectorAll('[data-intel-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.intelTab === tab));
  document.querySelectorAll('.intel-view').forEach(sec => sec.classList.remove('active'));
  const view = document.getElementById('intelView' + tab.charAt(0).toUpperCase() + tab.slice(1));
  if (view) view.classList.add('active');
  if (tab === 'map') intelligenceLoadMap();
  if (tab === 'database') intelligenceLoadRows();
  if (tab === 'brain') IntelligenceBrain.load();
}

async function intelligenceRefresh() {
  await intelligenceLoadOverview();
  if (intelligenceState.tab === 'database') await intelligenceLoadRows();
  if (intelligenceState.tab === 'map') await intelligenceLoadMap(true);
  if (intelligenceState.tab === 'brain') await IntelligenceBrain.load(true);
}

async function intelligenceLoadOverview() {
  try {
    const params = intelligenceParams();
    const r = await fetch('/api/stats?' + params.toString());
    const data = await r.json();
    if (!data.ok) throw new Error(data.error || 'stats laden mislukt');
    intelligenceState.stats = data;
    intelligenceState.loaded = true;
    const k = data.kpis || {};
    intelligenceSetText('intelKpiTotal', (k.addresses || 0).toLocaleString('nl-BE'));
    intelligenceSetText('intelKpiTop', `${k.top_pct || 0}% (${k.top_count || 0})`);
    intelligenceSetText('intelKpiPipeline', intelligenceMoney(k.weighted_pipeline || 0));
    intelligenceSetText('intelKpiM2', (k.facade_m2 || 0).toLocaleString('nl-BE'));
    intelligenceSetText('intelKpiResponse', `${k.response_rate || 0}%`);
    intelligenceSetText('intelKpiResponseDenom', `${k.response_numerator || 0} van ${k.response_denominator || 0} gecontacteerd`);
    intelligenceSetText('intelKpiAppointments', (k.appointments || 0).toLocaleString('nl-BE'));
    intelligenceSetText('intelKpiBacklog', (k.backlog || 0).toLocaleString('nl-BE'));
    intelligenceSetText('hpIntelCount', (k.addresses || 0).toLocaleString('nl-BE'));
    const meta = data.meta || {};
    document.body.classList.toggle('hp-demo-data', !!meta.synthetic || hpIsDemoDataset());
    intelligenceSetText('intelSourceNote', `${meta.source_label || meta.source || 'geen bron'} · ${meta.simulated_outcomes ? 'respons/status is demo-simulatie zolang CRM-events ontbreken' : 'respons/status uit campagne/CRM'}`);
    intelligenceSetText('intelFooterSource', `${meta.source_label || meta.source || 'geen bron'} · bronvermelding per veld staat in elk dossier.`);
    const actions = document.getElementById('intelActions');
    if (actions) actions.innerHTML = (data.actions || []).map(a => `<div class="tlitem"><b>${escapeHtml(a.title)}</b>${escapeHtml(a.detail)}</div>`).join('');
    intelligenceRenderCharts(data);
  } catch (e) {
    intelligenceSetText('intelSub', 'Intelligence laden mislukt: ' + e.message);
  }
}

function intelligenceChart(id, config) {
  if (typeof Chart === 'undefined') return;
  const canvas = document.getElementById(id);
  if (!canvas) return;
  if (intelligenceState.charts[id]) intelligenceState.charts[id].destroy();
  Chart.defaults.color = '#8b9bb0';
  Chart.defaults.borderColor = 'rgba(255,255,255,.06)';
  intelligenceState.charts[id] = new Chart(canvas, config);
}

function intelligenceRenderCharts(data) {
  if (typeof Chart === 'undefined') {
    intelligenceSetText('intelSourceNote', 'Chart.js is offline niet geladen; cijfers en tabellen blijven beschikbaar.');
    return;
  }
  const funnel = data.funnel || [];
  intelligenceChart('intelChartFunnel', {
    type: 'bar',
    data: { labels: funnel.map(f => `${f.label} (${f.count}/${f.denominator || f.count})`), datasets: [{data: funnel.map(f => f.count), backgroundColor:['#5c6b80','#5aa2e0','#5aa2e0','#5fbe8f','#e2a35c'], borderRadius:6, barThickness:22}] },
    options: { indexAxis:'y', plugins:{legend:{display:false}}, scales:{x:{grid:{color:'rgba(255,255,255,.05)'}},y:{grid:{display:false}}}, maintainAspectRatio:false }
  });
  const classes = data.class_distribution || [];
  intelligenceChart('intelChartClass', {
    type:'doughnut',
    data:{labels:classes.map(c=>c.klasse), datasets:[{data:classes.map(c=>c.count), backgroundColor:classes.map(c=>INTEL_CLASS_COLORS[c.klasse] || '#8b9bb0'), borderColor:'#121a26', borderWidth:3, hoverOffset:6}]},
    options:{cutout:'62%', plugins:{legend:{position:'bottom', labels:{boxWidth:9, boxHeight:9, padding:14}}}, maintainAspectRatio:false}
  });
  const partners = data.partner_response || [];
  intelligenceChart('intelChartPartner', {
    type:'bar',
    data:{labels:partners.map(p=>p.partner), datasets:[{data:partners.map(p=>p.rate), backgroundColor:'#e2a35c', borderRadius:6}]},
    options:{plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>`${c.raw}% respons`}}}, scales:{y:{ticks:{callback:v=>v+'%'}}}, maintainAspectRatio:false}
  });
  const weekly = data.weekly_response || [];
  intelligenceChart('intelChartTrend', {
    type:'line',
    data:{labels:weekly.map(w=>w.week), datasets:[{label:'Respons', data:weekly.map(w=>w.rate), borderColor:'#5fbe8f', backgroundColor:'rgba(95,190,143,.15)', fill:true, tension:.35, pointRadius:4}]},
    options:{plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>`${c.raw}% respons`}}}, scales:{y:{ticks:{callback:v=>v+'%'}}}, maintainAspectRatio:false}
  });
}

function intelligenceActiveClasses() {
  return Array.from(document.querySelectorAll('.intel-fchip.on')).map(b => b.dataset.k).join(',');
}

async function intelligenceLoadRows() {
  const params = intelligenceParams({
    limit: intelligenceState.limit,
    offset: intelligenceState.offset,
    sort: intelligenceState.sort,
    dir: intelligenceState.dir,
    q: document.getElementById('intelSearch')?.value || '',
    status: document.getElementById('intelStatusFilter')?.value || '',
    klasse: intelligenceActiveClasses(),
  });
  const r = await fetch('/api/database_rows?' + params.toString());
  const data = await r.json();
  intelligenceState.rows = data.rows || [];
  intelligenceState.total = data.total || 0;
  intelligenceRenderTable();
}

function intelligenceDebouncedRows() {
  clearTimeout(intelligenceState.rowDebounce);
  intelligenceState.offset = 0;
  intelligenceState.rowDebounce = setTimeout(intelligenceLoadRows, 180);
}

function intelligenceSort(key) {
  if (intelligenceState.sort === key) intelligenceState.dir = intelligenceState.dir === 'asc' ? 'desc' : 'asc';
  else { intelligenceState.sort = key; intelligenceState.dir = key === 'adres' ? 'asc' : 'desc'; }
  intelligenceLoadRows();
}

function intelligenceToggleClass(btn) {
  btn.classList.toggle('on');
  intelligenceState.offset = 0;
  intelligenceLoadRows();
}

function intelligenceRenderTable() {
  const body = document.getElementById('intelTableBody');
  if (!body) return;
  if (!intelligenceState.rows.length) {
    body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--db-muted);padding:18px">Geen rijen voor deze filter.</td></tr>';
  } else {
    body.innerHTML = intelligenceState.rows.map(r => {
      const klass = String(r.klasse || '').replace('+','p');
      const statusColor = INTEL_STATUS_COLORS[r.status] || '#8b9bb0';
      return `<tr data-lead-id="${escapeHtml(r.id)}" class="${r.id === intelligenceState.selectedId ? 'sel' : ''}" onclick="intelligenceOpenDossier('${jsq(r.id)}')">
        <td>${escapeHtml(r.adres)}</td>
        <td><span class="scorebar"><i style="width:${Math.max(0, Math.min(100, r.score || 0))}%"></i></span>${Number(r.score || 0).toFixed(1)}</td>
        <td><span class="kbadge k${klass}">${escapeHtml(r.klasse || '?')}</span></td>
        <td>${Number(r.m2 || 0).toLocaleString('nl-BE')}</td>
        <td>${intelligenceMoney(r.waarde || 0)}</td>
        <td>${escapeHtml(r.partner || '-')}</td>
        <td><span class="sdot"><i style="background:${statusColor}"></i>${escapeHtml(r.status || '-')}</span></td>
      </tr>`;
    }).join('');
  }
  const start = intelligenceState.total ? intelligenceState.offset + 1 : 0;
  const end = Math.min(intelligenceState.offset + intelligenceState.limit, intelligenceState.total);
  intelligenceSetText('intelPageInfo', `${start}-${end} van ${intelligenceState.total.toLocaleString('nl-BE')} rijen`);
}

function intelligencePrevPage() {
  intelligenceState.offset = Math.max(0, intelligenceState.offset - intelligenceState.limit);
  intelligenceLoadRows();
}

function intelligenceNextPage() {
  if (intelligenceState.offset + intelligenceState.limit >= intelligenceState.total) return;
  intelligenceState.offset += intelligenceState.limit;
  intelligenceLoadRows();
}

async function intelligenceOpenDossier(id) {
  intelligenceState.selectedId = id;
  intelligenceRenderTable();
  const params = intelligenceParams({id});
  const r = await fetch('/api/lead_dossier?' + params.toString());
  const data = await r.json();
  if (!data.ok) return;
  intelligenceRenderDrawer(data.dossier);
  const tr = document.querySelector(`[data-lead-id="${CSS.escape(id)}"]`);
  if (tr) tr.scrollIntoView({block:'nearest'});
}

function intelligenceRenderDrawer(d) {
  const drawer = document.getElementById('intelDrawer');
  if (!drawer) return;
  const metrics = Object.entries(d.metrics || {}).map(([k,v]) => `<div class="mrow"><span>${escapeHtml(k)}</span><div class="bar"><i style="width:${Math.max(0, Math.min(100, Number(v)||0))}%"></i></div><b>${Number(v||0).toFixed(0)}</b></div>`).join('');
  const sources = (d.sources || []).map(s => `<div class="prov"><b>${escapeHtml(s.field)}</b><span>${escapeHtml(s.source || 'bron onbekend')}<br>${escapeHtml(s.retrieved_at || 'datum onbekend')}</span></div>`).join('');
  const timeline = (d.timeline || []).map(e => `<div class="tlitem"><b>${escapeHtml(e.date)} · ${escapeHtml(e.status)}</b>${escapeHtml(e.label)}<br><span>${escapeHtml(e.source || '')}</span></div>`).join('');
  const render = d.render_path ? `<img src="/files/${encodeURI(d.render_path)}" alt="">` : '';
  drawer.innerHTML = `<div class="dr-hero"><h3>${escapeHtml(d.adres)}</h3><div class="meta">${escapeHtml(d.klasse)} · score ${Number(d.score||0).toFixed(1)} · ${escapeHtml(d.partner || '')}</div></div>
    <div class="dr-render">${render}</div>
    <div class="dr-sec"><h4>Score-opbouw</h4>${metrics}</div>
    <div class="dr-sec"><h4>Bronnen</h4>${sources}<div class="intel-footnote" style="padding:10px 0 0">${escapeHtml(d.provenance_note || '')}</div></div>
    <div class="dr-sec"><h4>Historiek</h4><div class="tl">${timeline}</div></div>
    <div class="dr-cta"><button class="hp-secondary-action" onclick="intelligenceShowOnMap('${jsq(d.id)}')">Op kaart</button><button class="hp-secondary-action" onclick="intelligenceRetarget('${jsq(d.id)}')">Retarget</button><button class="hp-secondary-action" onclick="intelligenceAssign('${jsq(d.id)}')">Toewijzen</button></div>`;
}

function intelligenceRetarget(id) { alert('Retarget gemarkeerd voor ' + id + '. In productie koppelen we dit aan wave/outcome-tabellen.'); }
function intelligenceAssign(id) { alert('Toewijzen geopend voor ' + id + '. In productie koppelen we dit aan partnerrechten.'); }

async function intelligenceLoadMap(force=false) {
  if (!intelligenceState.map) {
    intelligenceState.map = L.map('intelMap', {zoomControl:true, attributionControl:false}).setView([50.85,4.7], 9);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', {maxZoom:19, subdomains:'abcd'}).addTo(intelligenceState.map);
    intelligenceState.cluster = L.markerClusterGroup({
      showCoverageOnHover:false,
      maxClusterRadius:60,
      iconCreateFunction: cluster => L.divIcon({html:`<div class="mcluster" style="width:40px;height:40px">${cluster.getChildCount()}</div>`, className:'', iconSize:[44,44]})
    });
    intelligenceState.map.addLayer(intelligenceState.cluster);
    intelligenceState.map.on('moveend', () => intelligenceUpdateMapStats());
  }
  setTimeout(() => intelligenceState.map.invalidateSize(), 80);
  if (intelligenceState.mapRows.length && !force) return intelligenceUpdateMapStats();
  const params = intelligenceParams({limit:5000, sort:'score', dir:'desc'});
  const r = await fetch('/api/database_rows?' + params.toString());
  const data = await r.json();
  intelligenceState.mapRows = (data.rows || []).filter(r => r.lat !== null && r.lon !== null);
  intelligenceState.cluster.clearLayers();
  const bounds = [];
  intelligenceState.mapRows.forEach(row => {
    const color = INTEL_CLASS_COLORS[row.klasse] || '#8b9bb0';
    const radius = Math.max(5, Math.min(12, 4 + Number(row.score || 0) / 12));
    const marker = L.circleMarker([row.lat, row.lon], {radius, fillColor:color, color:'#fff', weight:1.2, opacity:.9, fillOpacity:.75});
    marker.bindPopup(`<div class="pop-adres">${escapeHtml(row.adres)}</div><div class="pop-meta">Klasse <b style="color:${color}">${escapeHtml(row.klasse)}</b> · score ${Number(row.score||0).toFixed(1)} · ${Number(row.m2||0).toFixed(0)}m2</div><div class="pop-meta">${escapeHtml(row.partner)} · ${escapeHtml(row.status)}</div><button class="hp-secondary-action" style="margin-top:8px;height:30px" onclick="intelligenceOpenDossier('${jsq(row.id)}'); intelligenceShow('database')">Open dossier</button>`);
    marker.on('click', () => intelligenceState.selectedId = row.id);
    intelligenceState.cluster.addLayer(marker);
    bounds.push([row.lat, row.lon]);
  });
  if (bounds.length) intelligenceState.map.fitBounds(bounds, {padding:[35,35], maxZoom:14});
  intelligenceUpdateMapStats();
}

function intelligenceUpdateMapStats() {
  if (!intelligenceState.map) return;
  const b = intelligenceState.map.getBounds();
  const inView = intelligenceState.mapRows.filter(r => b.contains([r.lat, r.lon]));
  intelligenceSetText('intelMapCount', inView.length.toLocaleString('nl-BE'));
  intelligenceSetText('intelMapTop', inView.filter(r => r.klasse === 'A+' || r.klasse === 'A').length.toLocaleString('nl-BE'));
}

function intelligenceShowOnMap(id) {
  intelligenceShow('map');
  setTimeout(() => {
    const row = intelligenceState.mapRows.find(r => r.id === id);
    if (row && intelligenceState.map) intelligenceState.map.setView([row.lat, row.lon], 17);
  }, 250);
}

function intelligenceSetPresentationMode(on) {
  document.body.classList.toggle('hp-presentation-mode', !!on);
  try { localStorage.setItem('homepilot.presentationMode', on ? '1' : '0'); } catch(e) {}
}

function intelligenceExportVisible() {
  const rows = intelligenceState.rows || [];
  if (!rows.length) return alert('Geen zichtbare rijen om te exporteren.');
  const cols = ['adres','capakey','score','klasse','m2','waarde','partner','status','sector'];
  const csv = [cols.join(',')].concat(rows.map(r => cols.map(c => '"' + String(r[c] ?? '').replace(/"/g,'""') + '"').join(','))).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'facadepilot_intelligence_visible.csv';
  a.click();
  URL.revokeObjectURL(a.href);
}

const IntelligenceBrain = (() => {
  let canvas, ctx, graph = {nodes:[], edges:[]}, running=false, hover=null, scale=1, ox=0, oy=0, drag=null;
  const colors = {campaign:'#e9eef5', lead:'#e2a35c', signal:'#5aa2e0', partner:'#5fbe8f', learning:'#a98fe8'};
  function init() {
    canvas = document.getElementById('intelBrain');
    if (!canvas || ctx) return;
    ctx = canvas.getContext('2d');
    canvas.addEventListener('wheel', e => { e.preventDefault(); const k=e.deltaY<0?1.08:.92; scale=Math.max(.25, Math.min(3, scale*k)); draw(); }, {passive:false});
    canvas.addEventListener('pointerdown', e => { drag={x:e.clientX,y:e.clientY,ox,oy}; canvas.classList.add('grabbing'); });
    canvas.addEventListener('pointerup', () => { drag=null; canvas.classList.remove('grabbing'); });
    canvas.addEventListener('pointermove', e => {
      if (drag) { ox=drag.ox+(e.clientX-drag.x)/scale; oy=drag.oy+(e.clientY-drag.y)/scale; draw(); return; }
      hover = nearest(e); draw(); info();
    });
    canvas.addEventListener('click', () => { if (hover && hover.lead_id) { intelligenceOpenDossier(hover.lead_id); intelligenceShow('database'); } });
    window.addEventListener('resize', resize);
  }
  function resize(){ if(!canvas) return; const r=canvas.getBoundingClientRect(); canvas.width=Math.max(300, r.width*devicePixelRatio); canvas.height=Math.max(300, r.height*devicePixelRatio); draw(); }
  function nearest(e){ const r=canvas.getBoundingClientRect(); const x=(e.clientX-r.left)*devicePixelRatio/scale-ox, y=(e.clientY-r.top)*devicePixelRatio/scale-oy; let best=null, bd=9999; graph.nodes.forEach(n=>{const d=Math.hypot(n.x-x,n.y-y); if(d<Math.max(18,n.size||10)&&d<bd){best=n;bd=d;}}); return best; }
  function layout(){
    const w=(canvas?.width||900), h=(canvas?.height||600), cx=w/2, cy=h/2;
    graph.nodes.forEach((n,i)=>{ if(n.x==null){ const a=i/Math.max(1,graph.nodes.length)*Math.PI*2; const ring=n.type==='campaign'?0:n.type==='lead'?240:n.type==='partner'?140:190; n.x=cx+Math.cos(a)*ring; n.y=cy+Math.sin(a)*ring; n.vx=0; n.vy=0; }});
  }
  function tick(){
    const byId=Object.fromEntries(graph.nodes.map(n=>[n.id,n]));
    graph.edges.forEach(e=>{const a=byId[e.source], b=byId[e.target]; if(!a||!b)return; const dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)); const f=(d-130)*.0008; a.vx+=dx*f; a.vy+=dy*f; b.vx-=dx*f; b.vy-=dy*f;});
    for(let i=0;i<graph.nodes.length;i++) for(let j=i+1;j<graph.nodes.length;j++){const a=graph.nodes[i],b=graph.nodes[j],dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)); if(d<90){const f=(90-d)*.002; a.vx-=dx/d*f; a.vy-=dy/d*f; b.vx+=dx/d*f; b.vy+=dy/d*f;}}
    graph.nodes.forEach(n=>{n.vx=(n.vx||0)*.86; n.vy=(n.vy||0)*.86; n.x+=n.vx; n.y+=n.vy;});
  }
  function draw(){
    if(!ctx) return; resizeOnce();
    ctx.clearRect(0,0,canvas.width,canvas.height); ctx.save(); ctx.scale(scale,scale); ctx.translate(ox,oy);
    const byId=Object.fromEntries(graph.nodes.map(n=>[n.id,n]));
    graph.edges.forEach(e=>{const a=byId[e.source],b=byId[e.target]; if(!a||!b)return; const hi=hover&&(hover.id===a.id||hover.id===b.id); ctx.strokeStyle=hi?'rgba(226,163,92,.75)':'rgba(255,255,255,.08)'; ctx.lineWidth=hi?2:1; ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();});
    graph.nodes.forEach(n=>{const hi=hover&&hover.id===n.id; ctx.beginPath(); ctx.fillStyle=colors[n.type]||'#8b9bb0'; ctx.globalAlpha=hi?1:.9; ctx.arc(n.x,n.y,hi?(n.size||10)+4:(n.size||10),0,Math.PI*2); ctx.fill(); ctx.globalAlpha=1; ctx.fillStyle=hi?'#fff':'#cbd5e1'; ctx.font=(hi?'700 ':'600 ')+'12px -apple-system,BlinkMacSystemFont,Segoe UI'; ctx.fillText(n.label.length>32?n.label.slice(0,31)+'...':n.label,n.x+(n.size||10)+6,n.y+4);});
    ctx.restore();
  }
  let sized=false; function resizeOnce(){ if(!sized){sized=true; resize();}}
  function loop(){ if(!running)return; tick(); draw(); requestAnimationFrame(loop); }
  function info(){ const el=document.getElementById('intelBrainInfo'); if(!el)return; if(!hover){el.classList.remove('show'); return;} el.classList.add('show'); el.innerHTML=`<span class="tag">${escapeHtml(hover.type)}</span><h4>${escapeHtml(hover.label)}</h4><div>${escapeHtml(hover.detail || '')}</div>`; }
  async function load(force=false){ init(); if(graph.nodes.length && !force){running=true; loop(); return;} const r=await fetch('/api/brain_graph?'+intelligenceParams().toString()); const data=await r.json(); graph={nodes:data.nodes||[],edges:data.edges||[]}; sized=false; resize(); layout(); running=true; loop(); }
  function fit(){ scale=1; ox=0; oy=0; draw(); }
  function focusBest(){ const best=graph.nodes.filter(n=>n.type==='lead').sort((a,b)=>(b.score||0)-(a.score||0))[0]; if(best&&canvas){scale=1.35; ox=(canvas.width/2/scale)-best.x; oy=(canvas.height/2/scale)-best.y; draw();}}
  function shake(){ graph.nodes.forEach(n=>{n.x=null;n.y=null;}); layout(); draw(); }
  return {load,fit,focusBest,shake};
})();

function intelligenceInstall() {
  try {
    const stored = localStorage.getItem('homepilot.presentationMode') === '1';
    const box = document.getElementById('intelPresentationMode');
    if (box) box.checked = stored;
    intelligenceSetPresentationMode(stored);
  } catch(e) {}
}
intelligenceInstall();


// ─── KAART (Leaflet + MarkerCluster) ────────────────────────────────────
let _map = null;
let _markerCluster = null;
let _activeLeadReview = null;
let _streetviewDebounce = null;
let _streetPositionDebounce = null;
let _currentMapSource = '';
let _currentMapCsv = '';
let _reviewSummary = null;
let _cameraDrag = null;
let _mapMode = 'leads';
let _mapFeatures = [];
let _addressListLimit = 80;
let _streetviewMiniObserver = null;
let _fieldRoute = null;
let _fieldRouteMode = 'driving';
let _fieldPhotos = {};
let _boxMode = false;
let _boxDrag = null;

const KLASSE_KLEUR = {
  "A+": "#22c55e",
  "A":  "#4ade80",
  "B":  "#60a5fa",
  "C":  "#fbbf24",
  "D":  "#94a3b8",
  "MAN": "#38bdf8",
};

const REVIEW_LABELS = {
  selected: 'Pipeline',
  reserve: 'Reserve',
  removed: 'Verwijderd',
  unreviewed: 'Niet beoordeeld',
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function markerOpacityFor(decision) {
  return decision === 'removed' ? 0.28 : 0.88;
}

function markerStrokeFor(decision, fallback) {
  if (decision === 'selected') return '#22c55e';
  if (decision === 'reserve') return '#fbbf24';
  if (decision === 'removed') return '#f87171';
  return fallback;
}

function reviewPill(decision) {
  const d = decision || 'unreviewed';
  return `<span class="review-pill ${d}">${REVIEW_LABELS[d] || d}</span>`;
}

function featureKey(feature) {
  const p = feature?.properties || {};
  return String(p.capakey || p.CAPAKEY || p.id || p.adres || '').trim();
}

function featureAddress(feature) {
  return String(feature?.properties?.adres || '(geen adres)').trim();
}

function featureCoords(feature) {
  const coords = feature?.geometry?.coordinates || [];
  const lon = Number(coords[0]);
  const lat = Number(coords[1]);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return {lat, lon};
}

function googleStreetviewEmbedUrl(lat, lon) {
  const la = Number(lat);
  const lo = Number(lon);
  if (!Number.isFinite(la) || !Number.isFinite(lo)) return '';
  return `https://www.google.com/maps?q=&layer=c&cbll=${la},${lo}&cbp=11,0,0,0,0&output=svembed`;
}

function streetviewEmbedForFeature(feature) {
  const coords = featureCoords(feature);
  if (!coords) return '';
  return googleStreetviewEmbedUrl(coords.lat, coords.lon);
}

function sortedMapFeatures() {
  return (_mapFeatures || []).slice().sort((a, b) => featureAddress(a).localeCompare(featureAddress(b), 'nl-BE'));
}

function routeCandidateFeatures() {
  const selected = (_mapFeatures || []).filter(f => (f.properties || {}).review_decision === 'selected');
  return selected.length ? selected : (_mapFeatures || []);
}

function loadStreetviewMini(node) {
  if (!node || node.dataset.loaded === '1') return;
  const src = node.dataset.svUrl || '';
  if (!src) {
    node.innerHTML = '<span class="lead-review-empty">Geen coördinaten</span>';
    return;
  }
  node.dataset.loaded = '1';
  node.innerHTML = `<iframe loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen title="Google Street View mini preview" src="${escapeHtml(src)}"></iframe>`;
}

function installStreetviewMiniObserver() {
  if (_streetviewMiniObserver) _streetviewMiniObserver.disconnect();
  const nodes = Array.from(document.querySelectorAll('.streetview-mini[data-sv-url]:not([data-loaded="1"])'));
  if (!nodes.length) return;
  if (!('IntersectionObserver' in window)) {
    nodes.slice(0, 12).forEach(loadStreetviewMini);
    return;
  }
  _streetviewMiniObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      loadStreetviewMini(entry.target);
      _streetviewMiniObserver.unobserve(entry.target);
    });
  }, {rootMargin:'180px'});
  nodes.forEach(node => _streetviewMiniObserver.observe(node));
}

function renderLeadAddressList() {
  const target = document.getElementById('leadAddressList');
  if (!target) return;
  const rows = sortedMapFeatures();
  if (!rows.length) {
    target.innerHTML = '<div class="lead-review-empty">Geen kaartleads geladen.</div>';
    const more = document.getElementById('leadAddressMoreBtn');
    if (more) more.style.display = 'none';
    return;
  }
  const visible = rows.slice(0, _addressListLimit);
  target.innerHTML = visible.map((feature, index) => {
    const p = feature.properties || {};
    const key = featureKey(feature);
    const decision = p.review_decision || 'unreviewed';
    const embed = streetviewEmbedForFeature(feature);
    const selectedClass = decision === 'selected' ? ' is-selected' : '';
    return `<article class="lead-address-row${selectedClass}" data-address-key="${escapeHtml(key)}">
      <div class="streetview-mini" data-sv-url="${escapeHtml(embed)}">
        <button type="button" onclick="loadStreetviewMini(this.parentElement)">Street View laden</button>
      </div>
      <div class="lead-address-main">
        <strong>${escapeHtml(featureAddress(feature))}</strong>
        <span>Klasse ${escapeHtml(p.klasse || '?')} · score ${Number(p.score || 0).toFixed(1)} · ${(p.bebouwd_m2 || 0).toFixed(0)}m² bebouwd</span>
        <div class="lead-address-badges">
          <b>${escapeHtml(decision.replace('_',' '))}</b>
          <b>${escapeHtml(p.huistype || 'woningtype ?')}</b>
          ${p.review_heading !== null && p.review_heading !== undefined ? '<b>camera</b>' : ''}
          ${p.review_target_box ? '<b>gevelkader</b>' : ''}
        </div>
      </div>
      <div class="lead-address-buttons">
        <button type="button" class="primary" onclick="openLeadReviewByKey('${jsq(key)}')">Open</button>
        <button type="button" onclick="chooseLeadFromList('${jsq(key)}','selected')">Selecteer</button>
        <button type="button" onclick="chooseLeadFromList('${jsq(key)}','reserve')">Reserve</button>
      </div>
    </article>`;
  }).join('');
  const more = document.getElementById('leadAddressMoreBtn');
  if (more) {
    more.style.display = rows.length > visible.length ? 'block' : 'none';
    more.textContent = `Toon meer adressen (${visible.length}/${rows.length})`;
  }
  installStreetviewMiniObserver();
}

function showMoreLeadAddresses() {
  _addressListLimit += 80;
  renderLeadAddressList();
}

async function openLeadReviewByKey(key) {
  const feature = (_mapFeatures || []).find(f => featureKey(f) === key);
  if (!feature) return null;
  await openLeadReview(feature);
  document.querySelectorAll('.lead-address-row').forEach(row => {
    row.classList.toggle('is-selected', row.dataset.addressKey === key);
  });
  const panel = document.getElementById('leadReviewPanel');
  if (panel) panel.scrollIntoView({behavior:'smooth', block:'center'});
  return feature;
}

async function chooseLeadFromList(key, decision) {
  const feature = await openLeadReviewByKey(key);
  if (!feature) return;
  await setLeadDecision(decision);
}

function haversineKm(a, b) {
  if (!a || !b) return 0;
  const R = 6371;
  const dLat = (b.lat - a.lat) * Math.PI / 180;
  const dLon = (b.lon - a.lon) * Math.PI / 180;
  const lat1 = a.lat * Math.PI / 180;
  const lat2 = b.lat * Math.PI / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

function orderedRouteFeatures(features) {
  const remaining = features.filter(featureCoords);
  const ordered = [];
  let current = remaining.shift();
  if (current) ordered.push(current);
  while (remaining.length) {
    const currentCoords = featureCoords(current);
    let bestIndex = 0;
    let bestDistance = Infinity;
    remaining.forEach((candidate, index) => {
      const distance = haversineKm(currentCoords, featureCoords(candidate));
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });
    current = remaining.splice(bestIndex, 1)[0];
    ordered.push(current);
  }
  return ordered;
}

function formatMinutes(minutes) {
  const value = Math.max(0, Math.round(minutes));
  if (value < 60) return `${value} min`;
  const h = Math.floor(value / 60);
  const m = value % 60;
  return `${h}u${m ? ` ${m}m` : ''}`;
}

function buildGoogleRouteUrl(mode, stops) {
  if (!stops.length) return '';
  const originInput = (document.getElementById('fieldRouteOrigin') || {}).value || '';
  const travelmode = mode === 'bicycling' ? 'bicycling' : 'driving';
  const labels = stops.map(featureAddress);
  const origin = originInput.trim() || labels[0];
  const destination = labels[labels.length - 1] || origin;
  const waypointLabels = originInput.trim() ? labels : labels.slice(1, -1);
  const params = new URLSearchParams({
    api: '1',
    origin,
    destination,
    travelmode
  });
  if (waypointLabels.length) params.set('waypoints', waypointLabels.slice(0, 20).join('|'));
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

function buildFieldRoute(mode='driving') {
  _fieldRouteMode = mode;
  const target = document.getElementById('fieldRouteList');
  const summary = document.getElementById('fieldRouteSummary');
  if (!target || !summary) return;
  const candidates = orderedRouteFeatures(routeCandidateFeatures()).slice(0, 24);
  if (!candidates.length) {
    target.innerHTML = '<div class="lead-review-empty">Selecteer eerst adressen op de kaart of in de alfabetische lijst.</div>';
    summary.innerHTML = '<div><span>Stops</span><strong>-</strong></div><div><span>Afstand</span><strong>-</strong></div><div><span>Auto</span><strong>-</strong></div><div><span>Fiets</span><strong>-</strong></div>';
    _fieldRoute = null;
    return;
  }
  let distance = 0;
  for (let i = 1; i < candidates.length; i += 1) {
    distance += haversineKm(featureCoords(candidates[i - 1]), featureCoords(candidates[i]));
  }
  const carMinutes = distance / 34 * 60 + candidates.length * 2.5;
  const bikeMinutes = distance / 15 * 60 + candidates.length * 1.5;
  _fieldRoute = {
    mode,
    stops: candidates,
    distance,
    url: buildGoogleRouteUrl(mode, candidates)
  };
  summary.innerHTML = `
    <div><span>Stops</span><strong>${candidates.length}</strong></div>
    <div><span>Afstand</span><strong>${distance.toFixed(1)} km</strong></div>
    <div><span>Auto</span><strong>${formatMinutes(carMinutes)}</strong></div>
    <div><span>Fiets</span><strong>${formatMinutes(bikeMinutes)}</strong></div>
  `;
  target.innerHTML = candidates.map((feature, index) => `
    <div class="route-stop">
      <i>${index + 1}</i>
      <div><strong>${escapeHtml(featureAddress(feature))}</strong><span>${escapeHtml((feature.properties || {}).klasse || '?')} · ${escapeHtml((feature.properties || {}).review_decision || 'niet beoordeeld')}</span></div>
      <button type="button" class="hp-secondary-action" onclick="openLeadReviewByKey('${jsq(featureKey(feature))}')">Open</button>
    </div>
  `).join('');
  hpSyncTopbar();
}

function openFieldRouteInGoogle() {
  if (!_fieldRoute) buildFieldRoute(_fieldRouteMode || 'driving');
  if (!_fieldRoute || !_fieldRoute.url) return alert('Geen route beschikbaar. Selecteer eerst adressen.');
  window.open(_fieldRoute.url, '_blank', 'noopener');
}

async function loadFieldPhotos() {
  try {
    const res = await fetch('/api/field_photos');
    const data = await res.json();
    _fieldPhotos = data.photos || {};
    hpSyncTopbar();
  } catch (e) {
    _fieldPhotos = {};
  }
}

function renderFieldPhotoList() {
  const target = document.getElementById('fieldPhotoList');
  if (!target) return;
  const features = (_fieldRoute && _fieldRoute.stops && _fieldRoute.stops.length)
    ? _fieldRoute.stops
    : routeCandidateFeatures().slice(0, 120);
  if (!features.length) {
    target.innerHTML = '<div class="lead-review-empty">Nog geen geselecteerde adressen. Ga eerst naar Leads & kaart.</div>';
    return;
  }
  target.innerHTML = features.map(feature => {
    const key = featureKey(feature);
    const photo = _fieldPhotos[key];
    return `<div class="photo-row">
      <i class="${photo ? 'photo-ready' : ''}">${photo ? 'OK' : '—'}</i>
      <div>
        <strong>${escapeHtml(featureAddress(feature))}</strong>
        <span>${photo ? `Foto gekoppeld: ${escapeHtml(photo.file || photo.path || 'bronbeeld')}` : 'Nog geen eigen foto gekoppeld.'}</span>
      </div>
      <label class="photo-drop">Foto kiezen
        <input type="file" accept="image/*" onchange="uploadFieldPhoto('${jsq(key)}', '${jsq(featureAddress(feature))}', this)">
      </label>
    </div>`;
  }).join('');
  hpSyncTopbar();
}

async function uploadFieldPhoto(key, address, input) {
  const file = input && input.files && input.files[0];
  if (!file) return;
  const body = new FormData();
  body.set('capakey', key);
  body.set('address', address || '');
  body.set('file', file);
  const row = input.closest('.photo-row');
  try {
    const res = await fetch('/api/lead_photo_upload', {method:'POST', body});
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'upload mislukt');
    _fieldPhotos[key] = data.photo;
    if (row) {
      row.querySelector('i').textContent = 'OK';
      row.querySelector('i').classList.add('photo-ready');
      row.querySelector('span').textContent = `Foto gekoppeld: ${data.photo.file || data.photo.path}`;
    }
    hpSyncTopbar();
  } catch (e) {
    alert('Foto uploaden mislukt: ' + e.message);
  }
}

function initMap() {
  if (_map) return _map;
  _map = L.map('mapContainer', {
    zoomControl: true,
    attributionControl: false,
  }).setView([50.85, 4.7], 9);  // Vlaanderen
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
  }).addTo(_map);
  _markerCluster = L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 60,
    iconCreateFunction: function(cluster) {
      const markers = cluster.getAllChildMarkers();
      const top = markers.filter(m => m.options.klasse === 'A+' || m.options.klasse === 'A').length;
      const total = markers.length;
      const pct = total > 0 ? Math.round(top / total * 100) : 0;
      const bg = pct >= 50 ? '#22c55e' : (pct >= 25 ? '#4ade80' : '#60a5fa');
      return L.divIcon({
        html: `<div style="background:${bg};color:#0f172a;border-radius:50%;width:38px;height:38px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:3px solid rgba(255,255,255,0.3);box-shadow:0 2px 8px rgba(0,0,0,0.4)">${total}<span style="font-size:8px;margin-left:1px">·${pct}%</span></div>`,
        className: 'custom-cluster',
        iconSize: [44, 44],
      });
    },
  });
  _map.addLayer(_markerCluster);
  return _map;
}

async function reloadMap() {
  initMap();
  _markerCluster.clearLayers();
  document.getElementById('mapMeta').textContent = 'Laden...';
  const rawCode = document.getElementById('niscode').value.trim();
  const params = new URLSearchParams();
  if (_mapMode === 'manual') {
    params.set('manual', '1');
  } else if (rawCode) {
    params.set('niscode', rawCode);
  }
  const r = await fetch('/api/leads_geojson' + (params.toString() ? '?' + params.toString() : ''));
  const data = await r.json();
  _currentMapSource = data.source || '';
  _currentMapCsv = _currentMapSource === 'manual:manual_leads.csv'
    ? 'manual_leads.csv'
    : (_currentMapSource.startsWith('csv:') ? _currentMapSource.substring(4) : '');
  const features = data.features || [];
  _mapFeatures = features;
  if (features.length === 0) {
    renderLeadAddressList();
    document.getElementById('mapMeta').textContent = _mapMode === 'manual'
      ? 'Geen handmatige adressen op de kaart'
      : rawCode
      ? `Geen kaartleads voor ${rawCode} — draai eerst adresselectie + scoring`
      : 'Geen leads — draai eerst de pipeline';
    await refreshReviewSummary();
    return;
  }
  const bounds = [];
  for (const f of features) {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    const kleur = KLASSE_KLEUR[p.klasse] || '#94a3b8';
    const reviewDecision = p.review_decision || 'unreviewed';
    const radius = p.klasse === 'A+' ? 9 : (p.klasse === 'A' ? 7 : 5);
    const marker = L.circleMarker([lat, lon], {
      radius: radius,
      fillColor: kleur,
      color: markerStrokeFor(reviewDecision, '#fff'),
      weight: reviewDecision === 'unreviewed' ? 1.5 : 3,
      opacity: markerOpacityFor(reviewDecision),
      fillOpacity: markerOpacityFor(reviewDecision),
      klasse: p.klasse,
    });
    let popup = `<div class="pop-adres">${escapeHtml(p.adres || '(geen adres)')}</div>`;
    popup += `<div class="pop-meta">Klasse <b style="color:${kleur}">${p.klasse}</b> • Score ${(p.score||0).toFixed(1)} • ${p.huistype || 'huistype ?'}</div>`;
    popup += `<div class="pop-meta">Review: ${reviewPill(reviewDecision)} • ${(p.bebouwd_m2||0).toFixed(0)}m² gevel</div>`;
    if (p.render_path) {
      popup += `<img src="/files/${p.render_path}" alt="">`;
    }
    marker.bindPopup(popup);
    marker.on('click', () => openLeadReview(f));
    _markerCluster.addLayer(marker);
    bounds.push([lat, lon]);
  }
  if (bounds.length > 0) {
    _map.fitBounds(bounds, {padding: [40, 40], maxZoom: 15});
  }
  setTimeout(() => _map.invalidateSize(), 100);
  const meta = document.getElementById('mapMeta');
  meta.textContent = `${features.length} leads • bron: ${data.source}`;
  // Cluster hint
  const klassen = features.reduce((acc, f) => {
    const k = f.properties.klasse || '?';
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
  const hintParts = ['A+', 'A', 'B', 'C', 'D'].filter(k => klassen[k]).map(k =>
    `<b style="color:${KLASSE_KLEUR[k]}">${k}</b>: ${klassen[k]}`
  );
  document.getElementById('clusterHint').innerHTML =
    `Verdeling: ${hintParts.join(' • ')}. <i style="color:#94a3b8">Tip: zoom in om clusters open te splitsen — getallen tonen hoeveel A+/A leads in dat cluster zitten.</i>`;
  renderLeadAddressList();
  if (document.body.classList.contains('hp-view-route')) buildFieldRoute(_fieldRouteMode || 'driving');
  if (document.body.classList.contains('hp-view-photos')) renderFieldPhotoList();
  await refreshReviewSummary();
}

async function openLeadReview(feature) {
  const p = feature.properties || {};
  const [lon, lat] = feature.geometry.coordinates;
  const panel = document.getElementById('leadReviewPanel');
  const decision = p.review_decision || 'unreviewed';
  _boxMode = false;
  _boxDrag = null;
  _cameraDrag = null;
  _activeLeadReview = {
    capakey: p.capakey || '',
    lat,
    lon,
    decision,
    heading: p.review_heading,
    pitch: p.review_pitch,
    fov: p.review_fov,
    strafeM: p.review_strafe_m || 0,
    targetBox: p.review_target_box || null,
  };

  panel.innerHTML = `
    <div>
      <div class="lead-review-title">${escapeHtml(p.adres || '(geen adres)')}</div>
      <div class="lead-review-meta">
        Klasse <b style="color:${KLASSE_KLEUR[p.klasse] || '#94a3b8'}">${escapeHtml(p.klasse || '?')}</b>
        • score ${(p.score || 0).toFixed(1)} • ${escapeHtml(p.huistype || 'huistype ?')}<br>
        ${reviewPill(decision)} • ${(p.bebouwd_m2 || 0).toFixed(0)}m² bebouwd
      </div>
    </div>

    <div class="streetview-frame loading" id="streetviewFrame">
      <img id="reviewStreetviewImg" alt="Street View preview">
      <iframe id="reviewStreetviewEmbed" title="Google Street View fallback" loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen hidden></iframe>
      <div class="target-box-overlay" id="targetBoxOverlay"></div>
      <div class="target-box-help" id="targetBoxHelp">Sleep: camera • Scroll: zoom • Kader: gevelzone</div>
    </div>

    <div class="review-actions">
      <button class="review-action" data-decision="selected" onclick="setLeadDecision('selected')">Selecteren</button>
      <button class="review-action" data-decision="reserve" onclick="setLeadDecision('reserve')">Reserve</button>
      <button class="review-action" data-decision="removed" onclick="setLeadDecision('removed')">Verwijderen</button>
    </div>

    <div class="camera-grid">
      <div class="camera-row">
        <span>Heading</span>
        <input type="range" id="svHeading" min="0" max="359" step="1" value="0" oninput="queueStreetviewPreview()">
        <span class="camera-value" id="svHeadingValue">0°</span>
      </div>
      <div class="camera-row">
        <span>Pitch</span>
        <input type="range" id="svPitch" min="-25" max="25" step="1" value="5" oninput="queueStreetviewPreview()">
        <span class="camera-value" id="svPitchValue">5°</span>
      </div>
      <div class="camera-row">
        <span>FOV</span>
        <input type="range" id="svFov" min="30" max="100" step="1" value="65" oninput="queueStreetviewPreview()">
        <span class="camera-value" id="svFovValue">65°</span>
      </div>
      <div class="camera-row">
        <span>Straat</span>
        <input type="range" id="svStrafe" min="-40" max="40" step="2" value="0" oninput="queueStreetPositionPreview()">
        <span class="camera-value" id="svStrafeValue">0m</span>
      </div>
      <div class="camera-nudges">
        <button onclick="nudgeCamera('heading', -8)">Links</button>
        <button onclick="nudgeCamera('heading', 8)">Rechts</button>
        <button onclick="nudgeCamera('pitch', 3)">Omhoog</button>
        <button onclick="nudgeCamera('pitch', -3)">Omlaag</button>
        <button onclick="nudgeStreetPosition(-8)">Strafe links</button>
        <button onclick="nudgeStreetPosition(8)">Strafe rechts</button>
        <button id="boxModeBtn" onclick="toggleBoxMode()">Kader</button>
        <button onclick="clearTargetBox()">Wis kader</button>
      </div>
      <button class="camera-save" onclick="saveLeadCamera()">Camera opslaan voor render</button>
      <div id="leadReviewStatus" style="font-size:11px;color:#94a3b8;min-height:16px"></div>
    </div>
  `;

  bindStreetviewPointerControls();
  drawTargetBox();
  updateDecisionButtons(decision);
  await loadStreetviewCamera();
}

async function loadStreetviewCamera() {
  if (!_activeLeadReview) return;
  const status = document.getElementById('leadReviewStatus');
  status.textContent = 'Camera zoeken...';
  try {
    const params = new URLSearchParams({
      capakey: _activeLeadReview.capakey,
      lat: _activeLeadReview.lat,
      lon: _activeLeadReview.lon,
    });
    const res = await fetch('/api/streetview_camera?' + params.toString());
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'camera niet beschikbaar');
    setCameraControls(data.heading, data.pitch, data.fov, data.strafe_m || 0);
    status.textContent = data.source === 'override' ? 'Opgeslagen camera geladen.' : 'Automatische Street View richting geladen.';
  } catch (e) {
    setCameraControls(_activeLeadReview.heading || 0, _activeLeadReview.pitch || 5, _activeLeadReview.fov || 65, _activeLeadReview.strafeM || 0);
    status.textContent = 'Camera fallback: ' + e.message;
  }
  refreshStreetviewPreview();
}

function setCameraControls(heading, pitch, fov, strafeM=null) {
  document.getElementById('svHeading').value = Math.round(Number(heading || 0)) % 360;
  document.getElementById('svPitch').value = Math.round(Number(pitch ?? 5));
  document.getElementById('svFov').value = Math.round(Number(fov ?? 65));
  if (strafeM !== null && document.getElementById('svStrafe')) {
    document.getElementById('svStrafe').value = Math.round(Number(strafeM || 0));
  }
  updateCameraLabels();
}

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function setTargetBox(box) {
  _activeLeadReview.targetBox = box || null;
  drawTargetBox();
}

function drawTargetBox() {
  const overlay = document.getElementById('targetBoxOverlay');
  if (!overlay || !_activeLeadReview) return;
  const box = _activeLeadReview.targetBox;
  if (!box) {
    overlay.style.display = 'none';
    return;
  }
  overlay.style.display = 'block';
  overlay.style.left = (box.x * 100).toFixed(3) + '%';
  overlay.style.top = (box.y * 100).toFixed(3) + '%';
  overlay.style.width = (box.w * 100).toFixed(3) + '%';
  overlay.style.height = (box.h * 100).toFixed(3) + '%';
}

function boxFromPointer(frame, startX, startY, currentX, currentY) {
  const rect = frame.getBoundingClientRect();
  const x1 = clampNumber((startX - rect.left) / rect.width, 0, 1);
  const y1 = clampNumber((startY - rect.top) / rect.height, 0, 1);
  const x2 = clampNumber((currentX - rect.left) / rect.width, 0, 1);
  const y2 = clampNumber((currentY - rect.top) / rect.height, 0, 1);
  return {
    x: Math.min(x1, x2),
    y: Math.min(y1, y2),
    w: Math.abs(x2 - x1),
    h: Math.abs(y2 - y1),
  };
}

function toggleBoxMode() {
  _boxMode = !_boxMode;
  const frame = document.getElementById('streetviewFrame');
  const btn = document.getElementById('boxModeBtn');
  if (frame) frame.classList.toggle('box-mode', _boxMode);
  if (btn) btn.classList.toggle('active', _boxMode);
  const status = document.getElementById('leadReviewStatus');
  if (status) status.textContent = _boxMode
    ? 'Kader-modus: sleep een rechthoek rond de gezamenlijke gevel.'
    : 'Kader-modus uit. Sleep nu weer om de camera te draaien.';
}

async function clearTargetBox() {
  if (!_activeLeadReview) return;
  setTargetBox(null);
  try {
    await saveLeadReview({target_box: 'null'});
    document.getElementById('leadReviewStatus').textContent = 'Kader gewist.';
    refreshReviewSummary();
  } catch (e) {
    document.getElementById('leadReviewStatus').textContent = 'Kader wissen mislukt: ' + e.message;
  }
}

function bindStreetviewPointerControls() {
  const frame = document.getElementById('streetviewFrame');
  if (!frame) return;

  frame.addEventListener('pointerdown', e => {
    if (e.button !== undefined && e.button !== 0) return;
    e.preventDefault();
    if (_boxMode) {
      _boxDrag = {pointerId: e.pointerId, x: e.clientX, y: e.clientY};
      setTargetBox(boxFromPointer(frame, e.clientX, e.clientY, e.clientX, e.clientY));
      if (frame.setPointerCapture) frame.setPointerCapture(e.pointerId);
      return;
    }
    _cameraDrag = {
      pointerId: e.pointerId,
      mode: (e.shiftKey || e.altKey) ? 'strafe' : 'rotate',
      x: e.clientX,
      y: e.clientY,
      heading: Number(document.getElementById('svHeading').value || 0),
      pitch: Number(document.getElementById('svPitch').value || 5),
      strafe: Number((document.getElementById('svStrafe') || {}).value || 0),
    };
    frame.classList.add('dragging');
    if (frame.setPointerCapture) frame.setPointerCapture(e.pointerId);
  });

  frame.addEventListener('pointermove', e => {
    if (_boxDrag) {
      e.preventDefault();
      setTargetBox(boxFromPointer(frame, _boxDrag.x, _boxDrag.y, e.clientX, e.clientY));
      return;
    }
    if (!_cameraDrag) return;
    e.preventDefault();
    const dx = e.clientX - _cameraDrag.x;
    const dy = e.clientY - _cameraDrag.y;
    if (_cameraDrag.mode === 'strafe') {
      const strafeEl = document.getElementById('svStrafe');
      if (strafeEl) {
        strafeEl.value = clampNumber(Math.round(_cameraDrag.strafe + dx * 0.18), -40, 40);
        queueStreetPositionPreview();
      }
      return;
    }
    const heading = (_cameraDrag.heading + dx * 0.28 + 360) % 360;
    const pitch = clampNumber(Math.round(_cameraDrag.pitch - dy * 0.16), -25, 25);
    setCameraControls(heading, pitch, document.getElementById('svFov').value);
    queueStreetviewPreview();
  });

  const endDrag = e => {
    if (_boxDrag) {
      if (frame.releasePointerCapture && e.pointerId === _boxDrag.pointerId) {
        try { frame.releasePointerCapture(e.pointerId); } catch (_) {}
      }
      const box = _activeLeadReview && _activeLeadReview.targetBox;
      _boxDrag = null;
      if (!box || box.w < 0.04 || box.h < 0.04) {
        setTargetBox(null);
        document.getElementById('leadReviewStatus').textContent = 'Kader is te klein. Sleep ruimer rond de gevelzone.';
      } else {
        document.getElementById('leadReviewStatus').textContent = 'Kader klaar. Klik “Camera opslaan voor render”.';
      }
      return;
    }
    if (!_cameraDrag) return;
    if (frame.releasePointerCapture && e.pointerId === _cameraDrag.pointerId) {
      try { frame.releasePointerCapture(e.pointerId); } catch (_) {}
    }
    const dragMode = _cameraDrag.mode;
    _cameraDrag = null;
    frame.classList.remove('dragging');
    if (dragMode === 'strafe') {
      clearTimeout(_streetPositionDebounce);
      recenterStreetPosition();
    } else {
      queueStreetviewPreview();
    }
  };

  frame.addEventListener('pointerup', endDrag);
  frame.addEventListener('pointercancel', endDrag);
  frame.addEventListener('pointerleave', e => {
    if (_cameraDrag && e.buttons === 0) endDrag(e);
  });

  frame.addEventListener('wheel', e => {
    if (_boxMode) return;
    e.preventDefault();
    const fovEl = document.getElementById('svFov');
    const current = Number(fovEl.value || 65);
    const next = clampNumber(current + (e.deltaY > 0 ? 4 : -4), 30, 100);
    fovEl.value = next;
    queueStreetviewPreview();
  }, {passive: false});
}

function updateCameraLabels() {
  document.getElementById('svHeadingValue').textContent = document.getElementById('svHeading').value + '°';
  document.getElementById('svPitchValue').textContent = document.getElementById('svPitch').value + '°';
  document.getElementById('svFovValue').textContent = document.getElementById('svFov').value + '°';
  const strafe = document.getElementById('svStrafe');
  if (strafe) document.getElementById('svStrafeValue').textContent = strafe.value + 'm';
}

function queueStreetviewPreview() {
  updateCameraLabels();
  clearTimeout(_streetviewDebounce);
  _streetviewDebounce = setTimeout(refreshStreetviewPreview, 280);
}

function currentStreetPosition() {
  const el = document.getElementById('svStrafe');
  if (!el) return 0;
  const value = clampNumber(Number(el.value || 0), -40, 40);
  el.value = value;
  return value;
}

function queueStreetPositionPreview() {
  updateCameraLabels();
  clearTimeout(_streetPositionDebounce);
  _streetPositionDebounce = setTimeout(recenterStreetPosition, 320);
}

async function recenterStreetPosition() {
  if (!_activeLeadReview) return;
  const strafeM = currentStreetPosition();
  const status = document.getElementById('leadReviewStatus');
  if (status) {
    status.textContent = strafeM === 0
      ? 'Originele straatpositie zoeken...'
      : `Straatpositie ${Math.abs(strafeM)}m ${strafeM < 0 ? 'links' : 'rechts'} zoeken...`;
  }
  try {
    const params = new URLSearchParams({
      capakey: _activeLeadReview.capakey,
      lat: _activeLeadReview.lat,
      lon: _activeLeadReview.lon,
      strafe_m: strafeM,
      recenter: '1',
    });
    const res = await fetch('/api/streetview_camera?' + params.toString());
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'camera niet beschikbaar');
    setCameraControls(
      data.heading,
      document.getElementById('svPitch').value,
      document.getElementById('svFov').value,
      data.strafe_m ?? strafeM
    );
    refreshStreetviewPreview();
    if (status) {
      status.textContent = strafeM === 0
        ? 'Originele straatpositie geladen.'
        : `Straatpositie ${Math.abs(strafeM)}m ${strafeM < 0 ? 'links' : 'rechts'} geladen.`;
    }
  } catch (e) {
    queueStreetviewPreview();
    if (status) status.textContent = 'Straatpositie niet automatisch gecentreerd: ' + e.message;
  }
}

function refreshStreetviewPreview() {
  if (!_activeLeadReview) return;
  const frame = document.getElementById('streetviewFrame');
  const img = document.getElementById('reviewStreetviewImg');
  const embed = document.getElementById('reviewStreetviewEmbed');
  if (!frame || !img) return;
  frame.classList.add('loading');
  img.style.display = 'block';
  if (embed) {
    embed.hidden = true;
    embed.removeAttribute('src');
  }
  const params = new URLSearchParams({
    capakey: _activeLeadReview.capakey,
    lat: _activeLeadReview.lat,
    lon: _activeLeadReview.lon,
    heading: document.getElementById('svHeading').value,
    pitch: document.getElementById('svPitch').value,
    fov: document.getElementById('svFov').value,
    strafe_m: currentStreetPosition(),
  });
  img.onload = () => frame.classList.remove('loading');
  img.onerror = () => {
    frame.classList.remove('loading');
    const fallback = googleStreetviewEmbedUrl(_activeLeadReview.lat, _activeLeadReview.lon);
    if (embed && fallback) {
      img.style.display = 'none';
      embed.hidden = false;
      embed.src = fallback;
      document.getElementById('leadReviewStatus').textContent = 'Officiële Google Street View embed geladen als fallback.';
    } else {
      document.getElementById('leadReviewStatus').textContent = 'Street View preview kon niet geladen worden.';
    }
  };
  img.src = '/api/streetview_image?' + params.toString();
}

function nudgeCamera(kind, delta) {
  const el = document.getElementById(kind === 'heading' ? 'svHeading' : 'svPitch');
  let value = Number(el.value || 0) + delta;
  if (kind === 'heading') value = (value + 360) % 360;
  el.value = value;
  queueStreetviewPreview();
}

function nudgeStreetPosition(delta) {
  const el = document.getElementById('svStrafe');
  if (!el) return;
  el.value = clampNumber(Number(el.value || 0) + delta, -40, 40);
  recenterStreetPosition();
}

function updateDecisionButtons(decision) {
  document.querySelectorAll('.review-action').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.decision === decision);
  });
}

async function saveLeadReview(payload) {
  if (!_activeLeadReview) return null;
  const body = new URLSearchParams();
  body.set('capakey', _activeLeadReview.capakey);
  for (const [key, value] of Object.entries(payload)) {
    body.set(key, value);
  }
  const res = await fetch('/api/lead_review', {method: 'POST', body});
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'opslaan mislukt');
  return data.review;
}

async function setLeadDecision(decision) {
  const status = document.getElementById('leadReviewStatus');
  try {
    await saveLeadReview({decision});
    _activeLeadReview.decision = decision;
    updateDecisionButtons(decision);
    status.textContent = decision === 'selected'
      ? 'Geselecteerd voor de pipeline.'
      : (decision === 'reserve' ? 'Op reservelijst gezet.' : 'Uit de pipeline gehaald.');
    reloadMap();
  } catch (e) {
    status.textContent = 'Opslaan mislukt: ' + e.message;
  }
}

async function saveLeadCamera() {
  const status = document.getElementById('leadReviewStatus');
  const payload = {
    heading: document.getElementById('svHeading').value,
    pitch: document.getElementById('svPitch').value,
    fov: document.getElementById('svFov').value,
    strafe_m: currentStreetPosition(),
  };
  if (_activeLeadReview && _activeLeadReview.targetBox) {
    payload.target_box = JSON.stringify(_activeLeadReview.targetBox);
  }
  try {
    await saveLeadReview(payload);
    _activeLeadReview.heading = Number(payload.heading);
    _activeLeadReview.pitch = Number(payload.pitch);
    _activeLeadReview.fov = Number(payload.fov);
    _activeLeadReview.strafeM = Number(payload.strafe_m);
    status.textContent = _activeLeadReview && _activeLeadReview.targetBox
      ? 'Camera en gevelkader opgeslagen. De render gebruikt deze uitsnede.'
      : 'Camera opgeslagen. Deze Street View wordt gebruikt bij de render.';
    refreshReviewSummary();
  } catch (e) {
    status.textContent = 'Camera opslaan mislukt: ' + e.message;
  }
}

async function refreshReviewSummary() {
  const rawCode = document.getElementById('niscode').value.trim();
  const params = new URLSearchParams();
  if (_mapMode === 'manual') {
    params.set('manual', '1');
  } else if (rawCode) {
    params.set('niscode', rawCode);
  }
  const res = await fetch('/api/lead_review_summary' + (params.toString() ? '?' + params.toString() : ''));
  _reviewSummary = await res.json();
  const counts = _reviewSummary.counts || {};
  const selected = counts.selected || 0;
  const reserve = counts.reserve || 0;
  const removed = counts.removed || 0;
  const total = _reviewSummary.total || 0;
  document.getElementById('reviewCounts').innerHTML =
    `<span>${total} leads op kaart</span>` +
    `<span>${reviewPill('selected')} ${selected}</span>` +
    `<span>${reviewPill('reserve')} ${reserve}</span>` +
    `<span>${reviewPill('removed')} ${removed}</span>`;
  document.getElementById('reviewStartBtn').disabled = selected === 0;

  const list = document.getElementById('reviewList');
  const items = _reviewSummary.items || {};
  const columns = [
    ['selected', 'Geselecteerd voor pipeline'],
    ['reserve', 'Reservelijst'],
    ['removed', 'Verwijderd'],
  ];
  list.innerHTML = columns.map(([key, title]) => {
    const rows = (items[key] || []).slice(0, 12);
    const extra = (items[key] || []).length - rows.length;
    const body = rows.length
      ? rows.map(item => `<li><b>${escapeHtml(item.adres || '(geen adres)')}</b><br><span style="color:#94a3b8">${escapeHtml(item.klasse || '?')} • score ${(item.score || 0).toFixed(1)}${item.heading !== null && item.heading !== undefined ? ' • camera' : ''}${item.target_box ? ' • kader' : ''}</span></li>`).join('')
      : '<li style="color:#64748b">Geen adressen.</li>';
    return `<div class="review-list-col"><h4>${title}</h4><ul>${body}${extra > 0 ? `<li style="color:#94a3b8">+ ${extra} meer</li>` : ''}</ul></div>`;
  }).join('');
  hpSyncTopbar();
}

async function startPipelineFromMapSelection() {
  if (!_reviewSummary || (_reviewSummary.selected_count || 0) === 0) {
    alert('Selecteer eerst minstens één woning op de kaart.');
    return;
  }
  if (!_currentMapCsv) {
    alert('Ik heb geen lokale CSV-bron voor deze kaart gevonden. Draai eerst adresselectie + scoring voor deze gemeente, of kies de juiste CSV links in het dashboard.');
    return;
  }

  const sel = document.getElementById('inputCsv');
  let option = [...sel.options].find(opt => opt.value === _currentMapCsv);
  if (!option) {
    option = document.createElement('option');
    option.value = _currentMapCsv;
    option.textContent = _currentMapCsv;
    sel.appendChild(option);
  }
  sel.value = _currentMapCsv;
  setPipelineMode('full');
  document.getElementById('stepAdres').checked = false;
  document.getElementById('stepScore').checked = _currentMapCsv !== 'manual_leads.csv' && !_currentMapCsv.includes('_scored');
  document.getElementById('stepRender').checked = true;
  document.getElementById('stepFlyer').checked = true;
  document.getElementById('stepLanding').checked = true;
  document.getElementById('stepPublish').checked = true;
  document.getElementById('stepEmail').checked = false;
  document.getElementById('renderTop').value = '';

  await startPipeline();
}

function showMapWhenAvailable(s) {
  // Show map card zodra scoring done is
  const haveLeads = (s.steps && s.steps.scoring && s.steps.scoring.status === 'done') || s.done;
  if (haveLeads) {
    const card = document.getElementById('mapCard');
    if (card.style.display === 'none') {
      card.style.display = 'block';
      reloadMap();
    }
  }
}

// ─── CRM TAB ────────────────────────────────────────────────────────────
async function reloadCrm() {
  const statusEl = document.getElementById('crmStatus');
  const funnelEl = document.getElementById('crmFunnel');
  const tbody = document.getElementById('crmTableBody');
  statusEl.textContent = 'Laden...';

  const [funnelRes, leadsRes] = await Promise.all([
    fetch('/api/crm_funnel').then(r => r.json()),
    fetch('/api/crm_leads?limit=50').then(r => r.json()),
  ]);

  if (!funnelRes.configured) {
    statusEl.innerHTML = `<span style="color:#fbbf24">⚠ ${funnelRes.error || 'CRM niet geconfigureerd'}</span><br><span style="color:#94a3b8">Voeg SUPABASE_SERVICE_KEY toe aan .env.</span>`;
    funnelEl.innerHTML = '';
    tbody.innerHTML = '';
    return;
  }

  statusEl.textContent = `${funnelRes.total} leads in CRM`;

  // Funnel
  funnelEl.innerHTML = '';
  const statuses = ['gegenereerd','geflyerd','gescand','contact','afspraak','klant','afgewezen'];
  for (const s of statuses) {
    const row = funnelRes.funnel[s];
    if (!row) continue;
    const div = document.createElement('div');
    div.className = 'funnel-row';
    div.innerHTML = `
      <div class="funnel-label">${row.label}</div>
      <div class="funnel-bar-bg"><div class="funnel-bar-fill" style="width:${row.pct}%"></div></div>
      <div class="funnel-count">${row.count}</div>
      <div class="funnel-pct">${row.pct}%</div>
    `;
    funnelEl.appendChild(div);
  }

  // Lead lijst
  tbody.innerHTML = '';
  if (leadsRes.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:16px">Nog geen leads in CRM. Draai eerst de pipeline.</td></tr>';
    return;
  }
  for (const l of leadsRes.slice(0, 30)) {
    const tr = document.createElement('tr');
    const klasse = l.lead_klasse || '?';
    const kleur = KLASSE_KLEUR[klasse] || '#94a3b8';
    tr.innerHTML = `
      <td><span class="crm-status ${l.status}">${l.status}</span></td>
      <td><span style="color:${kleur};font-weight:700">${klasse}</span></td>
      <td style="font-variant-numeric:tabular-nums">${(l.lead_score||0).toFixed(1)}</td>
      <td style="font-size:12px">${(l.adres || '(geen adres)').substring(0,55)}</td>
      <td>
        <select onchange="updateLeadStatus('${l.capakey}', this.value)" style="font-size:11px;padding:3px 6px;background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);color:#e2e8f0;border-radius:4px">
          <option value="">→ status</option>
          <option value="geflyerd">Flyer bezorgd</option>
          <option value="gescand">QR gescand</option>
          <option value="contact">Eerste contact</option>
          <option value="afspraak">Afspraak</option>
          <option value="klant">Klant</option>
          <option value="afgewezen">Afgewezen</option>
        </select>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

async function updateLeadStatus(capakey, status) {
  if (!status) return;
  const body = new URLSearchParams();
  body.set('capakey', capakey);
  body.set('status', status);
  const r = await fetch('/api/crm_status', {method: 'POST', body});
  if (r.ok) reloadCrm();
}

function showCrmWhenAvailable(s) {
  const haveLeads = s.done || (s.steps && s.steps.scoring && s.steps.scoring.status === 'done');
  if (haveLeads) {
    const card = document.getElementById('crmCard');
    if (card.style.display === 'none') {
      card.style.display = 'block';
      reloadCrm();
    }
  }
}

// ─── HOOK INTO POLL ─────────────────────────────────────────────────────
const _origUpdateUI = updateUI;
updateUI = function(s) {
  _origUpdateUI(s);
  showMapWhenAvailable(s);
  showCrmWhenAvailable(s);
};

// ─── HANDMATIG ADRES ────────────────────────────────────────────────────
async function addManualAddress() {
  const inp = document.getElementById('manualAdres');
  const adres = inp.value.trim();
  if (!adres) return;
  const body = new URLSearchParams();
  body.set('adres', adres);
  const r = await fetch('/api/manual_address', {method: 'POST', body});
  const data = await r.json();
  if (!data.ok) {
    alert(data.error || 'Toevoegen mislukt');
    return;
  }
  inp.value = '';
  refreshManualList();
  showManualMap();
}

async function refreshManualList() {
  const r = await fetch('/api/manual_addresses');
  const items = await r.json();
  const list = document.getElementById('manualList');
  const btn = document.getElementById('manualRunBtn');
  if (items.length === 0) {
    list.textContent = 'Nog geen handmatige adressen.';
    btn.style.display = 'none';
  } else {
    list.className = 'manual-list';
    list.innerHTML = items.map(item => `
      <div class="manual-item">
        <div>
          <div class="manual-item-title">${escapeHtml(item.adres || '(geen adres)')}</div>
          <div class="manual-item-meta">${escapeHtml(item.CAPAKEY || '')}</div>
        </div>
        <button class="manual-icon-btn" title="Toon op kaart" onclick="showManualMap('${escapeHtml(item.CAPAKEY || '')}')">⌖</button>
        <button class="manual-icon-btn danger" title="Verwijder adres" onclick="deleteManualAddress('${escapeHtml(item.CAPAKEY || '')}')">×</button>
      </div>
    `).join('');
    btn.style.display = 'block';
  }
}

async function showManualMap(capakeyToOpen='') {
  _mapMode = 'manual';
  document.getElementById('mapCard').style.display = 'block';
  await reloadMap();
  if (capakeyToOpen) {
    const feature = _mapFeatures.find(f => (f.properties || {}).capakey === capakeyToOpen);
    if (feature) openLeadReview(feature);
    document.getElementById('leadReviewPanel').scrollIntoView({behavior: 'smooth', block: 'center'});
  }
}

async function deleteManualAddress(capakey) {
  if (!capakey) return;
  const body = new URLSearchParams();
  body.set('capakey', capakey);
  const r = await fetch('/api/manual_delete', {method: 'POST', body});
  const data = await r.json();
  if (!data.ok) {
    alert(data.error || 'Verwijderen mislukt');
    return;
  }
  await refreshManualList();
  if (_mapMode === 'manual') reloadMap();
}

async function clearManual() {
  if (!confirm('Wis alle handmatige adressen?')) return;
  await fetch('/api/manual_clear', {method: 'POST'});
  refreshManualList();
  if (_mapMode === 'manual') reloadMap();
}

async function manualRun() {
  const selectedPresets = requirePresetSelection('manualPresetOptions');
  const body = new URLSearchParams();
  body.set('facade_preset', selectedPresets[0] || defaultRenderPresetKey());
  body.set('facade_presets', selectedPresets.join(','));
  body.set('flyer_style', 'auto');
  body.set('flyer_styles', 'auto');
  body.set('client_profile', document.getElementById('clientProfileSelect').value || '');
  body.set('client_brand_mode', getClientBrandMode());
  body.set('target_regions', document.getElementById('targetRegions').value || '');
  body.set('target_house_types', getSelectedPresets('targetHouseTypes').join(','));
  body.set('income_target', document.getElementById('incomeTarget').value || 'any');
  const r = await fetch('/api/manual_run', {method: 'POST', body});
  if (!r.ok) {
    const t = await r.text();
    alert('Start mislukt: ' + t);
    return;
  }
  document.getElementById('startBtn').disabled = true;
  document.getElementById('cancelBtn').style.display = 'block';
  document.getElementById('doneBanner').classList.remove('active');
}

document.getElementById('manualAdres').addEventListener('keypress', e => {
  if (e.key === 'Enter') { e.preventDefault(); addManualAddress(); }
});
document.getElementById('clientProfileSelect').addEventListener('change', applyClientProfileDefaults);
document.querySelectorAll('input[name="clientBrandMode"]').forEach(input => {
  input.addEventListener('change', () => {
    renderPresetOptionsForBrand();
    updateClientPublicBaseUrl(true);
  });
});
document.getElementById('clientLeadsSelect').addEventListener('change', () => {
  const leadValue = document.getElementById('clientLeadsSelect').value || '';
  if (leadValue) {
    const parts = leadValue.split('/');
    parts.pop();
    document.getElementById('clientSourceDir').value = parts.join('/') || '';
  }
  updateClientPathSummary();
});
['clientSourceDir','clientOutputRoot','clientPublicBaseUrl'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('input', updateClientPathSummary);
});

// ─── REVIEW-POORTEN (HITL stap 3) ────────────────────────────────────────────
let _reviewGate = 'voorfoto';
let _reviewReasonCodes = [];

function jsq(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function reviewItemDiv(key) {
  return Array.from(document.querySelectorAll('.review-item')).find(d => d.dataset.key === key);
}

function switchReviewGate(gate) {
  _reviewGate = gate;
  document.querySelectorAll('#reviewTabBar .tab').forEach(t => {
    t.classList.toggle('active', t.dataset.gate === gate);
  });
  loadReview();
}

function reviewStatsHtml(s) {
  const q = s.queue || {};
  const pending = (q.pending || 0) + (q.retry || 0);
  const rate = s.n_human_decisions_100
    ? Math.round((s.approval_rate_100 || 0) * 100) + '% over ' + s.n_human_decisions_100 + ' beslissingen'
    : 'nog geen menselijke beslissingen';
  const reasons = (s.top_afkeurredenen || []).map(r =>
    `<span class="review-chip">${escapeHtml(r[0])} ×${r[1]}</span>`).join(' ') ||
    '<span class="review-muted">nog geen afkeurredenen</span>';
  return `<div><b>${pending}</b> te beoordelen · goedkeuring (laatste 100): <b>${rate}</b> · autonomie: <b>${escapeHtml(s.autonomy_level || 'L1')}</b></div>` +
         `<div>Top-5 afkeurredenen: ${reasons}</div>`;
}

function reviewImagePair(item) {
  const img = item.images || {};
  if (_reviewGate === 'voorfoto') {
    return [['Gekadreerd origineel', img.original_path], ['Voorfoto', img.voorfoto_path]];
  }
  return [['Bron / voorfoto', img.source_path || img.voorfoto_path || img.original_path || img.streetview_path],
          ['Render', img.render_path]];
}

function reviewItemHtml(item) {
  const key = item.key || '';
  const p = item.payload || {};
  let media = '';
  if (_reviewGate === 'flyer_proof') {
    const links = (item.flyer_previews || []).map(f =>
      `<a href="/files/${encodeURI(f)}" target="_blank">${escapeHtml(f.split('/').pop())}</a>`).join(' · ');
    media = `<div class="review-flyerinfo">Batch met <b>${p.n_flyers || 0}</b> pdf's` +
      (p.n_leads ? ` voor ${p.n_leads} leads` : '') +
      ` — map: ${escapeHtml(p.output_dir || '?')}` +
      (links ? `<div>Voorbeelden: ${links}</div>` : '') + `</div>`;
  } else {
    const pair = reviewImagePair(item);
    media = '<div class="preview-grid">' + pair.map(([label, src]) =>
      `<div class="preview-item"><div class="label">${label}</div>` +
      (src ? `<img src="/files/${encodeURI(src)}" loading="lazy">`
           : '<div class="review-noimg">geen beeld gevonden</div>') +
      '</div>').join('') + '</div>';
  }
  const meta = [p.address, p.preset, p.mode,
                item.status === 'retry' ? 'opnieuw aangevraagd' : '']
    .filter(Boolean).map(escapeHtml).join(' · ');
  const truth = (p.truth && p.truth.pass === false)
    ? ` <span class="review-truthfail">waarheidscheck: ${escapeHtml(p.truth.reason || 'FAIL')}</span>` : '';
  return `<div class="review-item" data-key="${escapeHtml(key)}">
    <div class="review-item-head">
      <label><input type="checkbox" class="review-check" value="${escapeHtml(key)}"> <b>${escapeHtml(key)}</b></label>
      <span class="review-muted">${meta}</span>${truth}
    </div>
    ${media}
    <div class="review-actions">
      <button class="btn-sm btn-copy" onclick="reviewDecide('${jsq(key)}', 'approved')">Goedkeuren</button>
      <button class="btn-sm" onclick="reviewShowReasons('${jsq(key)}', 'retry')">Opnieuw</button>
      <button class="btn-sm" onclick="reviewShowReasons('${jsq(key)}', 'rejected')">Afkeuren</button>
      <span class="review-item-status"></span>
    </div>
    <div class="review-reason-panel" style="display:none">
      <div class="review-reason-chips"></div>
      <input type="text" class="review-note" placeholder="Notitie (optioneel)">
    </div>
  </div>`;
}

async function loadReview() {
  const queue = document.getElementById('reviewQueue');
  const stats = document.getElementById('reviewStats');
  const bulkBar = document.getElementById('reviewBulkBar');
  const goPanel = document.getElementById('campaignGoPanel');
  if (!queue) return;
  if (_reviewGate === 'campaign_go') {
    queue.innerHTML = '';
    stats.innerHTML = '';
    bulkBar.style.display = 'none';
    goPanel.style.display = 'block';
    return loadCampaignGo();
  }
  goPanel.style.display = 'none';
  queue.innerHTML = '<div class="review-empty">Wachtrij laden...</div>';
  try {
    const r = await fetch('/api/review/' + _reviewGate + '/pending');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'wachtrij laden mislukt');
    _reviewReasonCodes = d.reason_codes || [];
    stats.innerHTML = reviewStatsHtml(d.stats || {});
    const items = d.items || [];
    bulkBar.style.display = items.length ? 'flex' : 'none';
    queue.innerHTML = items.length
      ? items.map(reviewItemHtml).join('')
      : '<div class="review-empty">Geen items te beoordelen in deze poort.</div>';
  } catch (e) {
    stats.innerHTML = '';
    bulkBar.style.display = 'none';
    queue.innerHTML = '<div class="review-empty">Reviewwachtrij laden mislukt: ' + escapeHtml(e.message) + '</div>';
  }
}

function reviewShowReasons(key, decision) {
  const div = reviewItemDiv(key);
  if (!div) return;
  const panel = div.querySelector('.review-reason-panel');
  panel.style.display = 'block';
  const chips = panel.querySelector('.review-reason-chips');
  chips.innerHTML = '<span class="review-muted">Reden voor \'' +
    (decision === 'retry' ? 'opnieuw' : 'afkeuren') + '\':</span> ' +
    _reviewReasonCodes.map(c =>
      `<button class="btn-sm" onclick="reviewDecide('${jsq(key)}', '${decision}', '${jsq(c)}')">${escapeHtml(c)}</button>`
    ).join(' ');
}

async function reviewDecide(key, decision, reasonCode) {
  const div = reviewItemDiv(key);
  const statusEl = div ? div.querySelector('.review-item-status') : null;
  const noteEl = div ? div.querySelector('.review-note') : null;
  if (statusEl) statusEl.textContent = 'Bezig...';
  const body = new URLSearchParams();
  body.set('key', key);
  body.set('decision', decision);
  if (reasonCode) body.set('reason_code', reasonCode);
  if (noteEl && noteEl.value.trim()) body.set('note', noteEl.value.trim());
  try {
    const r = await fetch('/api/review/' + _reviewGate + '/decide', {method: 'POST', body});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'beslissing opslaan mislukt');
    loadReview();
  } catch (e) {
    if (statusEl) statusEl.textContent = 'Mislukt: ' + e.message;
  }
}

function reviewSelectAll(checked) {
  document.querySelectorAll('.review-check').forEach(cb => { cb.checked = checked; });
}

async function reviewBulkApprove() {
  const status = document.getElementById('reviewBulkStatus');
  const keys = Array.from(document.querySelectorAll('.review-check:checked')).map(cb => cb.value);
  if (!keys.length) { if (status) status.textContent = 'Geen items aangevinkt.'; return; }
  if (keys.length > 500) { if (status) status.textContent = 'Maximaal 500 items per bulk-actie.'; return; }
  if (!confirm('Keur ' + keys.length + ' geselecteerde items goed in poort \'' + _reviewGate + '\'?')) return;
  if (status) status.textContent = 'Bezig...';
  const body = new URLSearchParams();
  body.set('keys', keys.join('\n'));
  try {
    const r = await fetch('/api/review/' + _reviewGate + '/bulk', {method: 'POST', body});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'bulk-actie mislukt');
    if (status) status.textContent = d.updated + ' goedgekeurd' + (d.failed ? (', ' + d.failed + ' mislukt') : '') + '.';
    loadReview();
  } catch (e) {
    if (status) status.textContent = 'Bulk goedkeuren mislukt: ' + e.message;
  }
}

async function loadCampaignGo() {
  const panel = document.getElementById('campaignGoPanel');
  panel.innerHTML = '<div class="review-empty">Kostenoverzicht laden...</div>';
  try {
    const r = await fetch('/api/review/campaign_summary');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'overzicht laden mislukt');
    const enforcement = d.require_go
      ? 'Handhaving AAN (FACADEPILOT_REQUIRE_GO=1): publiceren/printen vereist vrijgave.'
      : 'Handhaving uit — zet FACADEPILOT_REQUIRE_GO=1 om publiceren/printen zonder vrijgave te blokkeren.';
    panel.innerHTML = `<div class="review-go-card">
      <h3>Campagne ${escapeHtml(d.key)}</h3>
      <div class="review-go-grid">
        <div><div class="review-go-num">&euro;${(d.cost_today_eur || 0).toFixed(2)}</div><div class="review-muted">renderkosten vandaag (${d.cost_entries_today || 0} betaalde calls)</div></div>
        <div><div class="review-go-num">${d.n_flyer_pdfs || 0}</div><div class="review-muted">flyer-pdf's klaar</div></div>
        <div><div class="review-go-num">${d.n_flyer_batches || 0}</div><div class="review-muted">flyer-batches in reviewpoort</div></div>
      </div>
      <div style="margin-top:12px">
        ${d.approved
          ? '<span class="review-go-ok">Vrijgegeven — verzenden/publiceren mag vandaag.</span>'
          : '<button class="btn-sm btn-copy" onclick="releaseCampaign()">Geef campagne vrij</button>'}
        <div class="review-muted" style="margin-top:6px">${enforcement}</div>
      </div>
    </div>`;
  } catch (e) {
    panel.innerHTML = '<div class="review-empty">Campagne-overzicht laden mislukt: ' + escapeHtml(e.message) + '</div>';
  }
}

async function releaseCampaign() {
  if (!confirm('Campagne van vandaag vrijgeven voor verzending/publicatie?')) return;
  try {
    const r = await fetch('/api/review/campaign_go', {method: 'POST', body: new URLSearchParams()});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'vrijgeven mislukt');
    loadCampaignGo();
  } catch (e) {
    alert('Vrijgeven mislukt: ' + e.message);
  }
}

loadGemeenten();
loadCSVs();
loadModules();
loadProfile();
refreshManualList();
refreshClientCampaignOptions();
pollClientCampaign();
poll();
setInterval(poll, 1000);
loadReview();
</script>
</body>
</html>
"""

HTML = install_flyer_editor(HTML, title="Facade/Window Flyer editor")


# ─── HTTP HANDLER ─────────────────────────────────────────────────────────────


# ─── RENDER-KOSTENRAMING (Fase F) ────────────────────────────────────────────
def _render_estimate_payload(qs) -> dict:
    """Kostenraming voor het dashboard (GET /api/render_estimate).

    Defensief: als homepilot_shared ontbreekt, geven we nulls terug zodat het
    dashboard zonder bevestigingsdialoog gewoon doorgaat.
    """
    try:
        n = int((qs.get("n", ["0"])[0] or "0").strip())
    except (TypeError, ValueError):
        n = 0
    n = max(0, min(n, 10000))
    size = (qs.get("size", [""])[0] or "").strip() or "1536x1024"
    try:
        import facadepilot_tracking  # noqa: F401  (sys.path bootstrap)
        from homepilot_shared.cost_guard import BudgetGuard, estimate_cost
        guard = BudgetGuard(pilot="facadepilot", project_dir=HERE)
        return {"n": n, "size": size,
                "cost_eur": estimate_cost(n, size=size),
                "budget_eur": round(float(guard.budget_eur), 2)}
    except Exception:
        return {"n": n, "size": size, "cost_eur": None, "budget_eur": None}


# ─── REVIEWPOORTEN (HITL stap 3 — ONTWERP_HITL_LEERLUS §2) ──────────────────
# Wachtrij-API voor de poorten voorfoto/render/flyer_proof/campaign_go.
# De pure logica (payload-shaping, pad-whitelist) leeft testbaar in
# homepilot_shared.review_ui; hier alleen de dunne dashboard-laag.

REVIEW_UI_GATES = ("voorfoto", "render", "flyer_proof", "campaign_go")


def _load_review_gate(gate_name: str):
    import facadepilot_tracking  # noqa: F401  (sys.path bootstrap)
    from homepilot_shared.review_gate import ReviewGate
    if gate_name not in REVIEW_UI_GATES:
        raise ValueError(f"Onbekende reviewpoort: {gate_name!r}")
    return ReviewGate(pilot="facadepilot", project_dir=HERE, gate=gate_name)


def get_review_pending(gate_name: str) -> dict:
    """GET /api/review/<gate>/pending — wachtrij + stats + redencodes."""
    gate = _load_review_gate(gate_name)
    from homepilot_shared.review_ui import pending_response
    return pending_response(gate, HERE)


def post_review_decision(gate_name: str, key: str, decision: str,
                         reason_code: str = "", note: str = "") -> dict:
    """POST /api/review/<gate>/decide — één beslissing met redencode."""
    gate = _load_review_gate(gate_name)
    item = gate.decide(key, decision, reason_code=(reason_code or None),
                       note=note or "")
    return {"ok": True, "key": item["key"], "status": item["status"]}


def post_review_bulk(gate_name: str, keys: list[str]) -> dict:
    """POST /api/review/<gate>/bulk — bulk-goedkeuren (PoolPilot-patroon)."""
    gate = _load_review_gate(gate_name)
    result = gate.decide_bulk(keys, "approved", cap=500)
    return {"ok": True, "updated": result["updated"],
            "failed": result["failed"], "errors": result["errors"][:10]}


def get_campaign_go_summary() -> dict:
    """Kostenoverzicht + status van de campagnepoort van vandaag."""
    import facadepilot_tracking  # noqa: F401  (sys.path bootstrap)
    from homepilot_shared.review_gate import ReviewGate
    from homepilot_shared.review_ui import campaign_go_key, cost_summary_today
    costs = cost_summary_today(HERE / "facadepilot_render_costs.jsonl")
    flyers_dir = HERE / "flyers"
    n_flyer_pdfs = len(list(flyers_dir.glob("*.pdf"))) if flyers_dir.exists() else 0
    try:
        flyer_gate = ReviewGate(pilot="facadepilot", project_dir=HERE,
                                gate="flyer_proof")
        n_flyer_batches = len(flyer_gate._load_queue())
    except Exception:
        n_flyer_batches = 0
    gate = _load_review_gate("campaign_go")
    key = campaign_go_key()
    return {
        "ok": True,
        "key": key,
        "approved": gate.is_approved(key),
        "cost_today_eur": costs["cost_eur"],
        "cost_entries_today": costs["n_entries"],
        "n_flyer_pdfs": n_flyer_pdfs,
        "n_flyer_batches": n_flyer_batches,
        "require_go": os.environ.get("FACADEPILOT_REQUIRE_GO") == "1",
    }


def post_campaign_go(note: str = "") -> dict:
    """POST /api/review/campaign_go — geef de campagne van vandaag vrij."""
    import facadepilot_tracking  # noqa: F401  (sys.path bootstrap)
    from homepilot_shared.review_ui import campaign_go_key, cost_summary_today
    gate = _load_review_gate("campaign_go")
    key = campaign_go_key()
    costs = cost_summary_today(HERE / "facadepilot_render_costs.jsonl")
    gate.submit(key=key, payload={
        "cost_today_eur": costs["cost_eur"],
        "cost_entries_today": costs["n_entries"],
    })
    item = gate.decide(key, "approved", note=note or "vrijgegeven via dashboard")
    return {"ok": True, "key": key, "status": item["status"]}


def _campaign_go_blocked_message() -> str | None:
    """Nederlandse blokkeermelding voor de verzend/export-stap, of None.

    Alleen actief bij FACADEPILOT_REQUIRE_GO=1 (standaard uit); fail-open
    bij interne fouten zodat de poortcontrole de pipeline nooit zelf breekt.
    """
    try:
        import facadepilot_tracking  # noqa: F401  (sys.path bootstrap)
        from homepilot_shared.review_ui import campaign_go_blocked
        return campaign_go_blocked(
            "facadepilot", HERE,
            require=os.environ.get("FACADEPILOT_REQUIRE_GO") == "1")
    except Exception:
        return None


# ─── LOKALE REQUEST-GUARD (CSRF / DNS-rebinding) ────────────────────────────
# Het dashboard draait zonder login op localhost. Zonder deze check kan een
# kwaadaardige webpagina in de browser POST-requests naar 127.0.0.1 sturen
# (CSRF) of via DNS-rebinding het dashboard aanspreken.
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _local_request_allowed(headers) -> bool:
    from urllib.parse import urlparse as _up
    host = (headers.get("Host") or "").split(":")[0].strip().lower()
    if host and host not in _LOOPBACK_HOSTS:
        return False
    origin = (headers.get("Origin") or "").strip()
    if origin:
        origin_host = (_up(origin).hostname or "").lower()
        if origin_host not in _LOOPBACK_HOSTS:
            return False
    return True


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._html(HTML)
        elif url.path == "/flyer-editor":
            try:
                from homepilot_shared.flyer_editor import flyer_editor_html
                self._html(flyer_editor_html())
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/state" or url.path == "/api/status":
            with state_lock:
                snap = json.loads(json.dumps(pipeline_state))
            self._json(snap)
        elif url.path == "/api/files":
            self._json(list_csv_files())
        elif url.path == "/api/gemeenten":
            # Combineer NIS-codes + postcodes voor autocomplete
            combined = dict(VOORBEELD_GEMEENTEN)
            for pc, (nis, naam) in POSTCODE_NIS.items():
                combined[pc] = f"{naam} (-> NIS {nis})"
            self._json(combined)
        elif url.path == "/api/modules":
            self._json(MODULES)
        elif url.path == "/api/facade_presets":
            self._json({k: {"label": v["label"], "afmeting": v["afmeting"],
                           "prijs": v["prijs"], "bouwtijd": v["bouwtijd"]}
                        for k, v in FACADE_PRESETS.items()})
        elif url.path == "/api/builder_profile":
            self._json(load_builder_profile())
        elif url.path == "/api/client_campaign_options":
            self._json(list_client_campaign_options())
        elif url.path == "/api/client_campaign_state":
            with client_campaign_lock:
                snap = json.loads(json.dumps(CLIENT_CAMPAIGN_STATE))
            self._json(snap)
        elif url.path == "/api/client_campaign_file":
            qs = parse_qs(url.query)
            try:
                path, content = read_editable_client_json((qs.get("path", [""])[0] or "").strip())
                self._json({"ok": True, "path": _path_for_ui(path), "content": content})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif url.path == "/api/open_local_path":
            qs = parse_qs(url.query)
            try:
                path = open_local_path(
                    (qs.get("path", [""])[0] or "").strip(),
                    create=(qs.get("create", ["0"])[0] or "0") == "1",
                )
                self._json({"ok": True, "path": _path_for_ui(path)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif url.path == "/api/resolve":
            qs = parse_qs(url.query)
            code = (qs.get("code", [""])[0] or "").strip()
            if code:
                try:
                    nis, naam = resolve_gemeente(code)
                    self._json({"ok": True, "niscode": nis, "naam": naam})
                except ValueError as e:
                    self._json({"ok": False, "error": str(e)})
            else:
                self._json({"ok": False, "error": ""})
        elif url.path == "/api/outputs":
            self._json(list_output_files())
        elif url.path == "/api/landing_pages":
            qs = parse_qs(url.query)
            self._json(list_landing_pages((qs.get("dir", [""])[0] or "").strip()))
        elif url.path == "/api/renders":
            self._json(list_render_details())
        elif url.path == "/api/flyer_editor_assets":
            try:
                qs = parse_qs(url.query)
                client_profile_path = (qs.get("profile", [""])[0] or "").strip()
                with state_lock:
                    default_niscode = pipeline_state.get("niscode", "")
                self._json(flyer_editor_payload(
                    HERE,
                    profile=None if client_profile_path else load_builder_profile(),
                    public_base_url=(qs.get("base", [""])[0] or os.environ.get("FACADEPILOT_TRACKER_URL", DEFAULT_LANDING_BASE_URL)).strip(),
                    default_niscode=default_niscode,
                    client_profile_path=client_profile_path,
                    client_leads_path=(qs.get("leads", [""])[0] or "").strip(),
                    source_dir=(qs.get("source", [""])[0] or "").strip(),
                    output_root=(qs.get("output", [""])[0] or "").strip(),
                ))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/flyer_editor_qr":
            try:
                from homepilot_shared.flyer_editor import flyer_editor_qr
                qs = parse_qs(url.query)
                with state_lock:
                    default_niscode = pipeline_state.get("niscode", "")
                self._json(flyer_editor_qr(
                    HERE,
                    capakey=(qs.get("capakey", [""])[0] or "").strip(),
                    url=(qs.get("url", [""])[0] or "").strip(),
                    profile=None if (qs.get("profile", [""])[0] or "").strip() else load_builder_profile(),
                    public_base_url=(qs.get("base", [""])[0] or os.environ.get("FACADEPILOT_TRACKER_URL", DEFAULT_LANDING_BASE_URL)).strip(),
                    default_niscode=default_niscode,
                ))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/flyer_editor_draft":
            try:
                from homepilot_shared.flyer_editor import load_flyer_editor_draft
                qs = parse_qs(url.query)
                self._json(load_flyer_editor_draft(HERE, (qs.get("id", [""])[0] or "").strip()))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/render_estimate":
            self._json(_render_estimate_payload(parse_qs(url.query)))
        elif url.path == "/api/stats":
            try:
                self._json(get_intelligence_stats(parse_qs(url.query)))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/database_rows":
            try:
                self._json(get_intelligence_rows(parse_qs(url.query)))
            except Exception as e:
                self._json({"ok": False, "error": str(e), "rows": []}, 500)
        elif url.path == "/api/lead_dossier":
            qs = parse_qs(url.query)
            try:
                self._json(get_lead_dossier(qs, (qs.get("id", [""])[0] or "").strip()))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/lead_events":
            qs = parse_qs(url.query)
            try:
                self._json(get_lead_events(qs, (qs.get("id", [""])[0] or "").strip()))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/brain_graph":
            try:
                self._json(get_brain_graph(parse_qs(url.query)))
            except Exception as e:
                self._json({"ok": False, "error": str(e), "nodes": [], "edges": []}, 500)
        elif url.path == "/api/field_photos":
            self._json(list_field_photos())
        elif url.path == "/api/leads_geojson":
            qs = parse_qs(url.query)
            niscode = (qs.get("niscode", [""])[0] or "").strip() or None
            manual = (qs.get("manual", ["0"])[0] or "0") == "1"
            self._json(get_leads_geojson(niscode, manual=manual))
        elif url.path == "/api/crm_funnel":
            qs = parse_qs(url.query)
            niscode = (qs.get("niscode", [""])[0] or "").strip() or None
            self._json(get_crm_funnel(niscode))
        elif url.path == "/api/manual_addresses":
            try:
                from facadepilot_manueel import list_manual_addresses
                self._json(list_manual_addresses())
            except Exception:
                self._json([])
        elif url.path == "/api/crm_leads":
            qs = parse_qs(url.query)
            self._json(get_crm_leads(
                niscode=(qs.get("niscode", [""])[0] or "").strip() or None,
                status=(qs.get("status", [""])[0] or "").strip() or None,
                klasse=(qs.get("klasse", [""])[0] or "").strip() or None,
                limit=int((qs.get("limit", ["100"])[0] or "100"))
            ))
        elif url.path == "/api/streetview_camera":
            qs = parse_qs(url.query)
            try:
                lat = float((qs.get("lat", [""])[0] or "").strip())
                lon = float((qs.get("lon", [""])[0] or "").strip())
                capakey = (qs.get("capakey", [""])[0] or "").strip()
                strafe_override = (qs.get("strafe_m", [""])[0] or "").strip()
                recenter = (qs.get("recenter", ["0"])[0] or "0") == "1"
                self._json({
                    "ok": True,
                    **get_streetview_camera(
                        lat,
                        lon,
                        capakey,
                        strafe_override=strafe_override,
                        recenter=recenter,
                    ),
                })
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        elif url.path == "/api/lead_review_summary":
            qs = parse_qs(url.query)
            niscode = (qs.get("niscode", [""])[0] or "").strip() or None
            manual = (qs.get("manual", ["0"])[0] or "0") == "1"
            self._json(get_lead_review_summary(niscode, manual=manual))
        elif url.path == "/api/streetview_image":
            self._serve_streetview_image(parse_qs(url.query))
        elif url.path.startswith("/api/review/"):
            self._handle_review_get(url)
        elif url.path.startswith("/files/"):
            self._serve_file(url.path[7:])  # strip "/files/"
        elif url.path.startswith("/landing-preview/"):
            self._serve_landing_preview(url.path[len("/landing-preview/"):])
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_review_get(self, url):
        """GET-routes voor de reviewpoorten (HITL stap 3)."""
        parts = [p for p in url.path.split("/") if p]  # ['api','review',...]
        try:
            if parts[2:] == ["campaign_summary"]:
                return self._json(get_campaign_go_summary())
            if len(parts) == 4 and parts[3] == "pending":
                return self._json(get_review_pending(parts[2]))
            return self._json({"ok": False, "error": "Onbekend review-endpoint"}, 404)
        except ValueError as e:
            return self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            return self._json({"ok": False, "error": str(e)}, 500)

    def _handle_review_post(self, url, data):
        """POST-routes voor de reviewpoorten (achter de lokale request-guard)."""
        def g(key, default=""):
            return (data.get(key, [default])[0] or default).strip()

        parts = [p for p in url.path.split("/") if p]
        try:
            if parts[2:] == ["campaign_go"]:
                return self._json(post_campaign_go(note=g("note")))
            if len(parts) != 4:
                return self._json({"ok": False, "error": "Onbekend review-endpoint"}, 404)
            gate_name, action = parts[2], parts[3]
            if action == "decide":
                return self._json(post_review_decision(
                    gate_name, g("key"), g("decision"),
                    reason_code=g("reason_code"), note=g("note")))
            if action == "bulk":
                keys = [k.strip() for k in (data.get("keys", [""])[0] or "").split("\n")
                        if k.strip()]
                if not keys:
                    return self._json({"ok": False, "error": "Geen items opgegeven"}, 400)
                if len(keys) > 500:
                    return self._json(
                        {"ok": False, "error": "Maximaal 500 items per bulk-actie"}, 400)
                return self._json(post_review_bulk(gate_name, keys))
            return self._json({"ok": False, "error": "Onbekend review-endpoint"}, 404)
        except (ValueError, KeyError) as e:
            return self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            return self._json({"ok": False, "error": str(e)}, 500)

    def _serve_file(self, rel_path):
        """Serve a file from the project directory (images, PDFs)."""
        import mimetypes
        safe_path = HERE / rel_path
        # Security: ensure path is within HERE
        try:
            safe_path.resolve().relative_to(HERE.resolve())
        except ValueError:
            self.send_response(403)
            self.end_headers()
            return
        if not safe_path.exists() or not safe_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        mime, _ = mimetypes.guess_type(str(safe_path))
        if not mime:
            mime = "application/octet-stream"
        data = safe_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_landing_preview(self, rel_path):
        """Serve a generated landing page locally before publication."""
        safe_rel = unquote(str(rel_path or "")).lstrip("/")
        safe_path = HERE / "landing" / safe_rel
        try:
            safe_path.resolve().relative_to((HERE / "landing").resolve())
        except ValueError:
            self.send_response(403)
            self.end_headers()
            return
        if not safe_path.exists() or not safe_path.is_file() or safe_path.suffix.lower() != ".html":
            self.send_response(404)
            self.end_headers()
            return
        data = safe_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_streetview_image(self, qs):
        """Serve a cached Street View preview without exposing the Google API key."""
        try:
            from facadepilot_streetview import fetch_streetview, DEFAULT_FOV, DEFAULT_PITCH

            lat = float((qs.get("lat", [""])[0] or "").strip())
            lon = float((qs.get("lon", [""])[0] or "").strip())
            capakey = (qs.get("capakey", [""])[0] or "").strip() or f"{lat}_{lon}"
            heading = _safe_float((qs.get("heading", [""])[0] or "").strip(), 0)
            pitch = _safe_int((qs.get("pitch", [str(DEFAULT_PITCH)])[0] or ""), DEFAULT_PITCH)
            fov = _safe_int((qs.get("fov", [str(DEFAULT_FOV)])[0] or ""), DEFAULT_FOV)
            strafe_m = _safe_float((qs.get("strafe_m", ["0"])[0] or ""), 0) or 0

            pitch = max(-30, min(30, pitch))
            fov = max(25, min(120, fov))
            strafe_m = max(-60, min(60, strafe_m))
            heading = heading % 360

            cache_dir = HERE / "streetview_review"
            cache_dir.mkdir(exist_ok=True)
            cache_name = f"{_safe_cache_key(capakey)}_h{round(heading, 1)}_p{pitch}_f{fov}_s{round(strafe_m, 1)}.jpg"
            img_path = cache_dir / cache_name

            if not img_path.exists():
                img = fetch_streetview(lat, lon, heading=heading, pitch=pitch, fov=fov, strafe_m=strafe_m)
                img.save(img_path, "JPEG", quality=90)

            data = img_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            body = f"Street View preview fout: {e}".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if not _local_request_allowed(self.headers):
            return self._json({"error": "Cross-origin verzoek geweigerd"}, 403)
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        data = parse_qs(raw)

        def g(key, default=""):
            return (data.get(key, [default])[0] or default).strip()

        def selected_presets(default_key=None):
            raw = g("facade_presets")
            presets = [p.strip() for p in raw.split(",") if p.strip()]
            presets = [p for p in presets if p in FACADE_PRESETS]
            if presets:
                return presets
            fallback = g("facade_preset") or default_key or DEFAULT_FACADE_PRESET
            if fallback not in FACADE_PRESETS:
                fallback = DEFAULT_FACADE_PRESET
            if g("multi_preset", "0") == "1":
                return list(FACADE_PRESETS.keys())
            return [fallback]

        def selected_flyer_styles(default_key="auto"):
            allowed = {"premium", "design", "klassiek", "printpartner", "auto"}
            raw = g("flyer_styles")
            styles = [s.strip().lower() for s in raw.split(",") if s.strip()]
            styles = [s for s in styles if s in allowed]
            if styles:
                return styles
            fallback = (g("flyer_style") or default_key or "premium").lower()
            if fallback not in allowed:
                fallback = "premium"
            return [fallback]

        if url.path == "/api/flyer_editor_export":
            try:
                payload = json.loads(raw or "{}")
                result = save_flyer_editor_export(HERE, payload)
                self._json(result, 200 if result.get("ok") else 400)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return

        if url.path.startswith("/api/review/"):
            return self._handle_review_post(url, data)

        if url.path == "/api/client_campaign_file_save":
            try:
                path, content = save_editable_client_json(g("path"), g("content"))
                self._json({"ok": True, "path": _path_for_ui(path), "content": content})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif url.path == "/api/client_campaign_validate":
            try:
                ok, output = validate_client_campaign(
                    g("profile"),
                    g("leads"),
                    source_dir=g("source_dir"),
                    render_source_dir=g("render_source_dir"),
                    strict_assets=g("strict_assets", "0") == "1",
                )
                self._json({"ok": ok, "output": output})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/client_campaign_generate":
            with client_campaign_lock:
                if CLIENT_CAMPAIGN_STATE.get("running"):
                    return self._json({"ok": False, "error": "Clientcampagne loopt al"}, 409)
            config = {
                "profile": g("profile"),
                "leads": g("leads"),
                "source_dir": g("source_dir"),
                "render_source_dir": g("render_source_dir"),
                "output_root": g("output_root"),
                "public_base_url": g("public_base_url"),
                "brand_mode": g("brand_mode", "auto"),
                "skip_renders": g("skip_renders", "1") == "1",
                "force": g("force", "0") == "1",
            }
            missing = [key for key in ("profile", "leads", "output_root", "public_base_url") if not config.get(key)]
            if missing:
                return self._json({"ok": False, "error": "Ontbrekend: " + ", ".join(missing)}, 400)
            t = threading.Thread(target=run_client_campaign, args=(config,), daemon=True)
            t.start()
            self._json({"ok": True})

        elif url.path == "/api/start":
            with state_lock:
                if pipeline_state["running"]:
                    return self._json({"error": "Pipeline loopt al"}, 409)

            reset_state()

            # Load builder profile
            profile = load_builder_profile()

            quality_check = g("quality_check", "1") == "1"
            selected_render_presets = selected_presets(profile.get("facade_preset", DEFAULT_FACADE_PRESET))
            selected_templates = selected_flyer_styles()
            pipeline_mode = "map_only" if g("pipeline_mode") == "map_only" else "full"

            config = {
                "mode": pipeline_mode,
                "client_profile": g("client_profile"),
                "client_brand_mode": g("client_brand_mode", "windowpilot"),
                "target_regions": g("target_regions"),
                "target_house_types": [v for v in g("target_house_types").split(",") if v],
                "income_target": g("income_target", "any"),
                "niscode": g("niscode"),
                "input_csv": g("input_csv") or None,
                "min_woning": float(g("min_woning", "60")),
                "max_woning": float(g("max_woning", "350")),
                "max_bebouwd_ratio": float(g("max_bebouwd_ratio", "0.75")),
                "min_perceel": 100,
                "max_perceel": 5000,
                "render_top": int(g("render_top")) if g("render_top").isdigit() else None,
                "render_klassen": [k for k in g("render_klassen").split(",") if k] or None,
                "builder_naam": g("builder_naam") or profile.get("naam", "Uw Gevelrenoveerder"),
                "builder_telefoon": g("builder_tel") or profile.get("telefoon", "0800 00 000"),
                "facade_preset": selected_render_presets[0],
                "facade_presets": selected_render_presets,
                "builder_profile": profile,
                "flyer_format": "both",
                "flyer_top": None,
                "quality_check": quality_check,
                "multi_preset_klassen": None,
                "multi_presets": selected_render_presets if len(selected_render_presets) > 1 else None,
                "auto_preset": g("auto_preset", "0") == "1",
                "flyer_style": selected_templates[0],
                "flyer_styles": selected_templates,
                "vergunning_filter": g("vergunning_filter", "1") == "1",
                "crm_sync": g("crm_sync", "1") == "1",
                "landing_base_url": DEFAULT_LANDING_BASE_URL,
                "publish_online": g("step_publish", "1") == "1",
                "steps": {
                    "adresselectie": g("step_adres", "1") == "1",
                    "scoring": g("step_score", "1") == "1",
                    "render": g("step_render", "1") == "1",
                    "flyer": g("step_flyer", "1") == "1",
                    "landing": g("step_landing", "1") == "1",
                    "publish": g("step_publish", "1") == "1",
                    "email": g("step_email", "0") == "1",
                },
            }

            if pipeline_mode == "map_only":
                config["render_top"] = None
                config["publish_online"] = False
                config["steps"].update({
                    "scoring": True,
                    "render": False,
                    "flyer": False,
                    "landing": False,
                    "publish": False,
                    "email": False,
                })

            with state_lock:
                pipeline_state["running"] = True

            t = threading.Thread(target=run_pipeline, args=(config,), daemon=True)
            t.start()
            self._json({"ok": True})

        elif url.path == "/api/cancel":
            with state_lock:
                pipeline_state["cancelled"] = True
            self._json({"ok": True})

        elif url.path == "/api/crm_status":
            capakey = g("capakey")
            new_status = g("status")
            note = g("note", "")
            store, err = _try_load_crm()
            if not store:
                return self._json({"ok": False, "error": err}, 500)
            try:
                ok = store.update_status(capakey, new_status, note)
                self._json({"ok": ok})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/crm_note":
            capakey = g("capakey")
            note = g("note")
            store, err = _try_load_crm()
            if not store:
                return self._json({"ok": False, "error": err}, 500)
            try:
                ok = store.add_note(capakey, note)
                self._json({"ok": ok})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/lead_review":
            try:
                self._json({"ok": True, "review": save_lead_review(data)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/manual_address":
            try:
                from facadepilot_manueel import add_manual_address, append_to_csv
                from facadepilot_lead_review import update_review
                adres = g("adres")
                with_perceel = g("with_perceel", "0") == "1"
                if not adres:
                    return self._json({"ok": False, "error": "adres ontbreekt"}, 400)
                rec = add_manual_address(adres, with_perceel=with_perceel)
                if not rec:
                    return self._json({"ok": False, "error": "geocoding mislukt"}, 400)
                append_to_csv(rec)
                update_review(rec["CAPAKEY"], decision="selected")
                self._json({"ok": True, "rec": rec})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/manual_delete":
            try:
                from facadepilot_manueel import delete_manual_address
                capakey = g("capakey")
                ok = delete_manual_address(capakey)
                self._json({"ok": ok})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/manual_clear":
            try:
                from facadepilot_manueel import clear_manual
                clear_manual()
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/manual_run":
            # Express-flow: pipeline starten met manual_leads.csv, alleen render+flyer
            try:
                from facadepilot_manueel import MANUAL_CSV
                if not MANUAL_CSV.exists():
                    return self._json({"ok": False, "error": "geen manual_leads.csv"}, 400)
                with state_lock:
                    if pipeline_state["running"]:
                        return self._json({"error": "Pipeline loopt al"}, 409)
                reset_state()
                profile = load_builder_profile()
                selected_render_presets = selected_presets(profile.get("facade_preset", DEFAULT_FACADE_PRESET))
                selected_templates = selected_flyer_styles()
                config = {
                    "mode": "full",
                    "client_profile": g("client_profile"),
                    "client_brand_mode": g("client_brand_mode", "windowpilot"),
                    "target_regions": g("target_regions"),
                    "target_house_types": [v for v in g("target_house_types").split(",") if v],
                    "income_target": g("income_target", "any"),
                    "niscode": "",
                    "input_csv": "manual_leads.csv",
                    "render_top": None,
                    "render_klassen": None,
                    "builder_naam": profile.get("naam", "Uw Gevelrenoveerder"),
                    "builder_telefoon": profile.get("telefoon", "0800 00 000"),
                    "facade_preset": selected_render_presets[0],
                    "facade_presets": selected_render_presets,
                    "builder_profile": profile,
                    "flyer_format": "both",
                    "flyer_top": None,
                    # Manueel = jij koos het adres bewust → quality check is overkill
                    "quality_check": False,
                    "auto_preset": False,
                    "multi_preset_klassen": None,
                    "multi_presets": selected_render_presets if len(selected_render_presets) > 1 else None,
                    "flyer_style": selected_templates[0],
                    "flyer_styles": selected_templates,
                    "vergunning_filter": False,
                    "crm_sync": True,
                    "landing_base_url": DEFAULT_LANDING_BASE_URL,
                    "publish_online": True,
                    "steps": {
                        "adresselectie": False,
                        "scoring": False,
                        "render": True,
                        "flyer": True,
                        "landing": True,
                        "publish": True,
                        "email": False,
                    },
                }
                with state_lock:
                    pipeline_state["running"] = True
                t = threading.Thread(target=run_pipeline, args=(config,), daemon=True)
                t.start()
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif url.path == "/api/replace_render":
            self._handle_render_upload()

        elif url.path == "/api/save_profile":
            # Save builder profile (form-encoded)
            profile = load_builder_profile()
            for key in ["naam", "telefoon", "email", "website", "accent_color",
                        "headline", "subheadline", "facade_preset"]:
                val = g(key)
                if val:
                    profile[key] = val
            flyer_copy_raw = g("flyer_copy")
            if flyer_copy_raw:
                try:
                    from facadepilot_flyer_copy import normalize_copy
                    profile["flyer_copy"] = normalize_copy(json.loads(flyer_copy_raw))
                except Exception as e:
                    return self._json({"ok": False, "error": f"Flyer copy ongeldig: {e}"}, 400)
            save_builder_profile(profile)
            self._json({"ok": True, "profile": profile})

        elif url.path == "/api/upload_logo":
            self._handle_logo_upload()

        elif url.path == "/api/lead_photo_upload":
            self._handle_field_photo_upload()

        else:
            self.send_response(404)
            self.end_headers()

    def _handle_render_upload(self):
        """Handle multipart upload to replace a render image."""
        import re
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return self._json({"error": "multipart/form-data required"}, 400)

        # Parse boundary
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[9:].strip('"')
        if not boundary:
            return self._json({"error": "No boundary found"}, 400)

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Simple multipart parser
        boundary_bytes = f"--{boundary}".encode()
        parts = body.split(boundary_bytes)

        render_id = None
        file_data = None

        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end < 0:
                continue
            headers_raw = part[:header_end].decode("utf-8", errors="replace")
            payload = part[header_end + 4:]
            # Strip trailing \r\n
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]

            name_match = re.search(r'name="([^"]+)"', headers_raw)
            if not name_match:
                continue
            field_name = name_match.group(1)

            if field_name == "render_id":
                render_id = payload.decode("utf-8").strip()
            elif field_name == "file":
                file_data = payload

        if not render_id or not file_data:
            return self._json({"error": "render_id and file required"}, 400)

        # Path-traversal guard: render_id mag geen padscheidingstekens of
        # ".." bevatten en het doelbestand moet binnen renders/ blijven.
        import re as _re
        if not _re.fullmatch(r"[A-Za-z0-9._\-]{1,120}", render_id) or ".." in render_id:
            return self._json({"error": "ongeldig render_id"}, 400)
        renders_dir = (HERE / "renders").resolve()
        target = (renders_dir / f"{render_id}_render.jpg").resolve()
        if target.parent != renders_dir:
            return self._json({"error": "ongeldig render_id"}, 400)

        # Backup old render
        if target.exists():
            backup_dir = renders_dir / "replaced"
            backup_dir.mkdir(exist_ok=True)
            import shutil
            backup_name = f"{render_id}_render_{int(time.time())}.jpg"
            shutil.copy2(target, backup_dir / backup_name)

        # Save new render
        target.write_bytes(file_data)

        self._json({"ok": True, "replaced": str(target), "size_kb": round(len(file_data) / 1024)})

    def _handle_field_photo_upload(self):
        """Handle own/partner photo upload for the pre-render source-image gate."""
        import re
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return self._json({"ok": False, "error": "multipart/form-data required"}, 400)

        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[9:].strip('"')
        if not boundary:
            return self._json({"ok": False, "error": "No boundary found"}, 400)

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        boundary_bytes = f"--{boundary}".encode()
        parts = body.split(boundary_bytes)

        capakey = ""
        address = ""
        file_data = None
        filename = "field_photo.jpg"
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end < 0:
                continue
            headers_raw = part[:header_end].decode("utf-8", errors="replace")
            payload = part[header_end + 4:]
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]
            name_match = re.search(r'name="([^"]+)"', headers_raw)
            if not name_match:
                continue
            field_name = name_match.group(1)
            if field_name == "capakey":
                capakey = payload.decode("utf-8", errors="replace").strip()
            elif field_name == "address":
                address = payload.decode("utf-8", errors="replace").strip()
            elif field_name == "file":
                file_data = payload
                file_match = re.search(r'filename="([^"]*)"', headers_raw)
                if file_match and file_match.group(1):
                    filename = file_match.group(1)

        if not capakey or not file_data:
            return self._json({"ok": False, "error": "capakey and file required"}, 400)

        suffix = Path(filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
            suffix = ".jpg"
        key = safe_photo_key(capakey)
        photo_dir = (HERE / "field_photos").resolve()
        photo_dir.mkdir(exist_ok=True)
        target = (photo_dir / f"{key}{suffix}").resolve()
        if target.parent != photo_dir:
            return self._json({"ok": False, "error": "ongeldige foto-key"}, 400)
        target.write_bytes(file_data)

        index = load_field_photo_index()
        rel_path = f"field_photos/{target.name}"
        photo = {
            "capakey": capakey,
            "address": address,
            "file": target.name,
            "path": rel_path,
            "source_type": "own_capture_or_partner_upload",
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "size_kb": round(len(file_data) / 1024),
        }
        index[capakey] = photo
        save_field_photo_index(index)
        self._json({"ok": True, "photo": photo})

    def _handle_logo_upload(self):
        """Handle logo upload for builder profile."""
        import re
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return self._json({"error": "multipart/form-data required"}, 400)

        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[9:].strip('"')
        if not boundary:
            return self._json({"error": "No boundary found"}, 400)

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        boundary_bytes = f"--{boundary}".encode()
        parts = body.split(boundary_bytes)

        file_data = None
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end < 0:
                continue
            headers_raw = part[:header_end].decode("utf-8", errors="replace")
            payload = part[header_end + 4:]
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]
            name_match = re.search(r'name="([^"]+)"', headers_raw)
            if name_match and name_match.group(1) == "logo":
                file_data = payload

        if not file_data:
            return self._json({"error": "No logo file found"}, 400)

        logo_path = HERE / "builder_logo.png"
        logo_path.write_bytes(file_data)

        # Update profile
        profile = load_builder_profile()
        profile["logo_path"] = str(logo_path)
        save_builder_profile(profile)

        self._json({"ok": True, "logo_path": str(logo_path), "size_kb": round(len(file_data) / 1024)})


# ─── MAIN ────────────────────────────────────────────────────────────────────

class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start het FacadePilot dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host om de lokale server op te starten.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Startpoort voor het dashboard.")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        default=os.environ.get("FACADEPILOT_NO_BROWSER") == "1",
        help="Start de server zonder automatisch een externe browser te openen.",
    )
    args = parser.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost", "::1") and \
            os.environ.get("FACADEPILOT_ALLOW_NETWORK") != "1":
        raise SystemExit(
            "Dashboard heeft geen authenticatie; binden op een niet-loopback host "
            "is geblokkeerd. Zet FACADEPILOT_ALLOW_NETWORK=1 als je dit bewust wil."
        )

    os.chdir(HERE)

    # Show module status
    print(f"\n   FacadePilot Pipeline")
    print(f"    Modules:")
    for k, v in MODULES.items():
        status = "OK" if v else "NIET"
        print(f"      [{status}] {k}")
    print()

    # Zoek automatisch een vrije poort
    try:
        end_port = 8900 if args.port < 8900 else args.port + 100
        port = find_free_port(args.port, end_port)
    except RuntimeError as e:
        sys.exit(f"   FOUT: {e}")

    if port != args.port:
        print(f"    Poort {args.port} is bezet → gebruik poort {port}")

    server = ThreadedServer((args.host, port), Handler)
    url_host = "localhost" if args.host in ("127.0.0.1", "localhost") else args.host
    url = f"http://{url_host}:{port}/"
    print(f"    Dashboard: {url}")
    print("    Druk Ctrl+C om te stoppen.\n")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n    Pipeline gestopt.")
        server.server_close()


if __name__ == "__main__":
    main()
