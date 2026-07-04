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

import asyncio
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
SHARED_PY = HERE / "shared" / "python"
if SHARED_PY.exists():
    sys.path.insert(0, str(SHARED_PY))

DEFAULT_PORT = 8769


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
    "current_step": None,       # "adresselectie" | "scoring" | "render" | "flyer"
    "start_time": None,
    "gemeente": "",
    "niscode": "",
    "steps": {
        "adresselectie": {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "scoring":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "render":        {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "flyer":         {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
        "landing":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
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
            "gemeente": "",
            "niscode": "",
            "steps": {
                "adresselectie": {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "scoring":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "render":        {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "flyer":         {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
                "landing":       {"status": "pending", "progress": 0, "total": 0, "message": "", "output_file": None},
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
    export_cols = ["adres", "CAPAKEY", "perceel_m2", "bebouwd_m2", "bebouwd_ratio", "tuin_m2", "lat", "lon", "google_maps"]
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
    if multi_preset_klassen and multi_presets:
        log(f"  -> Multi-preset: {multi_presets} voor klassen {multi_preset_klassen}")

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
                sp = str(row.get("streetview_path", "") or "")
                if capakey and rp:
                    # Sla relatieve paden op (vanuit FacadePilot/)
                    rel_render = rp.replace(str(HERE) + "/", "").replace(str(HERE) + "\\", "")
                    rel_streetview = sp.replace(str(HERE) + "/", "").replace(str(HERE) + "\\", "") if sp else None
                    store.set_render_paths(capakey, render_path=rel_render, streetview_path=rel_streetview)
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
                 base_url: str = "https://facadepilot.be"):
    """Stap 5: Landingpagina's per adres genereren + URL terugkoppelen naar CRM."""
    import facadepilot_landing as landing_mod

    input_path = HERE / input_file
    log(f"Landingpagina's genereren voor {input_file}")
    update_step("landing", status="running", message="Voorbereiden...")

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    if len(df) == 0:
        update_step("landing", status="done", message="Geen leads")
        return

    # Filter alleen leads met succesvolle render
    if "render_path" in df.columns:
        df = df[df["render_path"].astype(str).str.len() > 5].copy()
    total = len(df)
    if total == 0:
        log("  Geen renders beschikbaar voor landingpagina's")
        update_step("landing", status="done", message="Geen renders")
        return

    update_step("landing", total=total, message=f"0/{total}...")
    output_dir = HERE / "landing" / niscode
    renders_dir = HERE / "renders"

    preset_dict = FACADE_PRESETS.get(facade_preset or "moderne_crepi", {})

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
        progress_callback=landing_progress,
    )

    log(f"  -> {len(results)} landingpagina's gegenereerd")

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
                message=f"{len(results)} pagina's", output_file=f"landing/{niscode}/")

    with state_lock:
        pipeline_state["output_files"].append({
            "name": f"landing/{niscode}/",
            "label": "Landingpagina's (HTML)",
            "rows": len(results)
        })


def step_email(input_file: str, niscode: str, builder_profile: dict,
               facade_preset: str | None = None,
               landing_base_url: str = "https://facadepilot.be"):
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
               flyer_style: str = "premium"):
    """Stap 4: Flyer generatie."""
    import facadepilot_flyer as flyer_mod

    input_path = HERE / input_file
    log(f"Flyer generatie starten voor {input_file}")
    update_step("flyer", status="running", message="Flyers voorbereiden...")

    df = pd.read_csv(input_path, encoding="utf-8-sig")

    if top_n:
        df = df.head(top_n).copy()

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

    log(f"  -> Flyer-stijl: {flyer_style}")

    # Run async flyer generation
    asyncio.run(flyer_mod.generate_flyers(
        df, output_dir, formats,
        builder_naam=builder_naam,
        builder_telefoon=builder_telefoon,
        landing_base_url="facadepilot.be",
        renders_dir=renders_dir,
        progress_callback=flyer_progress,
        extra_vars=extra_vars if extra_vars else None,
        flyer_style=flyer_style,
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
        current_file = config.get("input_csv", None)  # optioneel: start vanaf bestaand CSV

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
            )
            if is_cancelled():
                raise Exception("Geannuleerd")
        else:
            update_step("flyer", status="skipped", message="Overgeslagen")

        # ── STAP 5: Landingpagina's ───────────────────────────────
        if steps_enabled.get("landing", True) and current_file:
            with state_lock:
                pipeline_state["current_step"] = "landing"
            step_landing(
                input_file=current_file,
                niscode=niscode,
                builder_profile=config.get("builder_profile") or {},
                facade_preset=config.get("facade_preset"),
                base_url=config.get("landing_base_url", "https://facadepilot.be"),
            )
            if is_cancelled():
                raise Exception("Geannuleerd")
        else:
            update_step("landing", status="skipped", message="Overgeslagen")

        # ── STAP 6: E-mail-flyers ────────────────────────────────
        if steps_enabled.get("email", False) and current_file:
            with state_lock:
                pipeline_state["current_step"] = "email"
            step_email(
                input_file=current_file,
                niscode=niscode,
                builder_profile=config.get("builder_profile") or {},
                facade_preset=config.get("facade_preset"),
                landing_base_url=config.get("landing_base_url", "https://facadepilot.be"),
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


def list_render_details():
    """Lijst alle renders met streetview + render paren."""
    renders_dir = HERE / "renders"
    if not renders_dir.exists():
        return []
    items = []
    for render_file in sorted(renders_dir.glob("*_render.jpg")):
        base = render_file.name.replace("_render.jpg", "")
        streetview_file = renders_dir / f"{base}_streetview.jpg"
        items.append({
            "id": base,
            "render": f"renders/{render_file.name}",
            "streetview": f"renders/{streetview_file.name}" if streetview_file.exists() else None,
            "has_render": True,
            "size_kb": round(render_file.stat().st_size / 1024),
        })
    # Also list streetview photos without renders (failed renders)
    for sv_file in sorted(renders_dir.glob("*_streetview.jpg")):
        base = sv_file.name.replace("_streetview.jpg", "")
        if not (renders_dir / f"{base}_render.jpg").exists():
            items.append({
                "id": base,
                "render": None,
                "streetview": f"renders/{sv_file.name}",
                "has_render": False,
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
    }
    if BUILDER_PROFILE_PATH.exists():
        try:
            with open(BUILDER_PROFILE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_builder_profile(profile: dict):
    """Sla het bouwer-profiel op."""
    with open(BUILDER_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


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


def get_leads_geojson(niscode: str | None = None) -> dict:
    """Geef alle leads als GeoJSON FeatureCollection.

    Probeert eerst Supabase. Valt terug op de meest recente lokale CSV
    als CRM niet geconfigureerd is.
    """
    features = []

    # 1) Probeer Supabase
    store, err = _try_load_crm()
    if store:
        try:
            leads = store.list_leads(niscode=niscode, limit=5000)
            for l in leads:
                lat, lon = l.get("lat"), l.get("lon")
                if lat is None or lon is None:
                    continue
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "capakey": l.get("capakey"),
                        "adres": l.get("adres", ""),
                        "klasse": l.get("lead_klasse", ""),
                        "score": l.get("lead_score", 0),
                        "huistype": l.get("huistype", ""),
                        "bebouwd_m2": l.get("bebouwd_m2", 0),
                        "status": l.get("status", "gegenereerd"),
                        "render_path": l.get("render_path") or "",
                        "streetview_path": l.get("streetview_path") or "",
                    }
                })
            return {"type": "FeatureCollection", "features": features, "source": "supabase"}
        except Exception as e:
            log(f"GeoJSON Supabase fout, fallback naar CSV: {e}")

    # 2) Fallback: meest recente _scored.csv lezen
    csv_files = sorted(HERE.glob("facadepilot_leads_*_scored*.csv"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    if not csv_files:
        return {"type": "FeatureCollection", "features": [], "source": "none",
                "error": err or "Geen leads gevonden"}

    try:
        df = pd.read_csv(csv_files[0], encoding="utf-8-sig")
        for _, row in df.iterrows():
            lat = row.get("lat")
            lon = row.get("lon")
            if pd.isna(lat) or pd.isna(lon):
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "capakey": str(row.get("CAPAKEY", "")),
                    "adres": str(row.get("adres", "")),
                    "klasse": str(row.get("lead_klasse", "")),
                    "score": float(row.get("lead_score", 0) or 0),
                    "huistype": str(row.get("huistype", "")),
                    "bebouwd_m2": float(row.get("bebouwd_m2", 0) or 0),
                    "status": "gegenereerd",
                    "render_path": str(row.get("render_path", "") or ""),
                    "streetview_path": "",
                }
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
input,select{width:100%;padding:9px 12px;background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.12);border-radius:8px;color:#e2e8f0;font-size:14px;font-family:inherit}
input:focus,select:focus{outline:none;border-color:#60a5fa;box-shadow:0 0 0 3px rgba(96,165,250,0.15)}

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

/* Render gallery */
.render-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:12px}
.render-thumb{position:relative;border-radius:10px;overflow:hidden;cursor:pointer;border:2px solid transparent;transition:all .15s;aspect-ratio:1}
.render-thumb:hover{border-color:rgba(96,165,250,0.5);transform:scale(1.02)}
.render-thumb.selected{border-color:#60a5fa;box-shadow:0 0 12px rgba(96,165,250,0.3)}
.render-thumb img{width:100%;height:100%;object-fit:cover}
.render-thumb .overlay{position:absolute;inset:0;background:linear-gradient(transparent 50%,rgba(0,0,0,0.7));display:flex;align-items:flex-end;padding:6px 8px}
.render-thumb .overlay span{font-size:10px;color:#fff;font-weight:500}

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
#mapContainer{height:520px;border-radius:10px;overflow:hidden;border:1px solid rgba(255,255,255,0.06);background:#1a2236}
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

</style>
</head>
<body>
<div class="container">

<header>
  <div class="logo">
    <div class="logo-icon">FP</div>
    <div>
      <h1>FacadePilot Pipeline</h1>
      <div class="subtitle">Gevelrenovatie lead-campagne in een klik</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <button class="btn-sm btn-copy" onclick="window.location.href='/flyer-editor'">Flyer-editor</button>
    <div class="subtitle">Local / Port <span id="port"></span></div>
  </div>
</header>

<div class="layout">
  <!-- LEFT: Config -->
  <div>
    <div class="card" style="margin-bottom:16px">
      <h2>Campagne instellen</h2>

      <div class="field">
        <label>Postcode of NIS-code</label>
        <input type="text" id="niscode" placeholder="bijv. 3300 of 24107" list="gemeenten-list">
        <datalist id="gemeenten-list"></datalist>
        <div style="font-size:11px;margin-top:4px" id="gemeenteHint"></div>
      </div>

      <div class="field">
        <label>Of start vanaf bestaand CSV <span class="badge">optioneel</span></label>
        <select id="inputCsv">
          <option value="">-- Nieuw (via adresselectie) --</option>
        </select>
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
        <label>Renovatie type</label>
        <select id="facadePreset">
          <option value="moderne_crepi">Moderne crepi-afwerking</option>
          <option value="baksteen_rejoint">Baksteen reiniging + hervoegen</option>
          <option value="isolatie_gevelbekleding">Buitenisolatie + gevelbekleding</option>
          <option value="totaalrenovatie">Totale gevelrenovatie</option>
        </select>
      </div>

      <div class="field">
        <label>Flyer-stijl <span class="badge ok">3 templates</span></label>
        <select id="flyerStyle">
          <option value="premium">Premium — warm taupe, breed toepasbaar</option>
          <option value="design">Design — brutalist, donker, modern statement</option>
          <option value="klassiek">Klassiek — atelier bourgeois, oude rijhuizen</option>
          <option value="auto">🤖 Auto — kies per lead op basis van huistype</option>
        </select>
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
          <div class="toggle-label">Multi-preset voor A+ <span class="badge warn">3x kost</span></div>
          <div class="toggle-hint">Top 5%: render in 3 stijlen</div>
        </div>
        <label class="toggle"><input type="checkbox" id="multiPreset"><span class="slider"></span></label>
      </div>

      <div class="toggle-row">
        <div>
          <div class="toggle-label">🤖 Auto-preset per lead <span class="badge ok">slim</span></div>
          <div class="toggle-hint">Kies type per lead op basis van profiel</div>
        </div>
        <label class="toggle"><input type="checkbox" id="autoPreset"><span class="slider"></span></label>
      </div>
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
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <button class="btn-sm btn-copy" onclick="addManualAddress()" style="flex:1">+ Toevoegen</button>
        <button class="btn-sm" onclick="clearManual()" style="background:rgba(220,53,69,0.15);color:#fca5a5;border:1px solid rgba(220,53,69,0.3)">Wis</button>
      </div>
      <div id="manualList" style="font-size:11px;color:#94a3b8;margin-bottom:10px"></div>
      <button class="btn btn-primary" id="manualRunBtn" onclick="manualRun()" style="background:linear-gradient(135deg,#22c55e,#15803d);font-size:13px;padding:11px;display:none">
        🚀 Express-run (alleen render + flyer + landing)
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
          <div class="toggle-label">3. Gevelrenovatie renders <span class="badge" id="modRender">--</span></div>
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
          <div class="toggle-label">5. Landingpagina's <span class="badge ok">CRM-tracking</span></div>
          <div class="toggle-hint">HTML per adres + scan-tracking</div>
        </div>
        <label class="toggle"><input type="checkbox" id="stepLanding" checked><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">6. E-mail-flyers <span class="badge">optioneel</span></div>
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
  </div>

  <!-- RIGHT: Progress -->
  <div>
    <div class="done-banner" id="doneBanner">
      <h3>Pipeline voltooid!</h3>
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
        <div class="step" id="step-email">
          <div class="step-header">
            <div class="step-icon pending" id="icon-email">6</div>
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
        <button class="btn-sm btn-copy" onclick="reloadMap()">Verversen</button>
      </h2>
      <div class="legend">
        <div class="legend-item"><span class="legend-dot" style="background:#22c55e"></span>A+</div>
        <div class="legend-item"><span class="legend-dot" style="background:#4ade80"></span>A</div>
        <div class="legend-item"><span class="legend-dot" style="background:#60a5fa"></span>B</div>
        <div class="legend-item"><span class="legend-dot" style="background:#fbbf24"></span>C</div>
        <div class="legend-item"><span class="legend-dot" style="background:#94a3b8"></span>D</div>
        <div class="legend-item" style="margin-left:auto"><span id="mapMeta" style="color:#94a3b8;font-size:11px"></span></div>
      </div>
      <div id="mapContainer"></div>
      <div id="clusterHint" style="margin-top:10px;font-size:12px;color:#94a3b8"></div>
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
  for (const f of files) {
    const opt = document.createElement('option');
    opt.value = f.name;
    opt.textContent = `${f.name} (${f.rows} rijen)`;
    sel.appendChild(opt);
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
});

async function startPipeline() {
  const niscode = document.getElementById('niscode').value.trim();
  const inputCsv = document.getElementById('inputCsv').value;

  if (!niscode && !inputCsv) {
    return alert('Voer een postcode (bv. 3300) of NIS-code (bv. 24107) in, of kies een bestaand CSV bestand.');
  }

  const body = new URLSearchParams();
  if (niscode) body.set('niscode', niscode);
  if (inputCsv) body.set('input_csv', inputCsv);
  body.set('min_woning', document.getElementById('minWoning').value || '60');
  body.set('max_woning', document.getElementById('maxWoning').value || '350');
  body.set('max_bebouwd_ratio', document.getElementById('maxBebouwdRatio').value || '0.75');
  body.set('render_top', document.getElementById('renderTop').value || '');
  body.set('render_klassen', document.getElementById('renderKlassen').value || '');
  body.set('builder_naam', document.getElementById('builderNaam').value || '');
  body.set('builder_tel', document.getElementById('builderTel').value || '');
  body.set('facade_preset', document.getElementById('facadePreset').value || 'moderne_crepi');
  body.set('flyer_style', document.getElementById('flyerStyle').value || 'premium');
  body.set('quality_check', document.getElementById('qualityCheck').checked ? '1' : '0');
  body.set('multi_preset', document.getElementById('multiPreset').checked ? '1' : '0');
  body.set('auto_preset', document.getElementById('autoPreset').checked ? '1' : '0');

  // Steps
  body.set('step_adres', document.getElementById('stepAdres').checked ? '1' : '0');
  body.set('step_score', document.getElementById('stepScore').checked ? '1' : '0');
  body.set('step_render', document.getElementById('stepRender').checked ? '1' : '0');
  body.set('step_flyer', document.getElementById('stepFlyer').checked ? '1' : '0');
  body.set('step_landing', document.getElementById('stepLanding').checked ? '1' : '0');
  body.set('step_email', document.getElementById('stepEmail').checked ? '1' : '0');
  body.set('vergunning_filter', document.getElementById('vergunningFilter').checked ? '1' : '0');
  body.set('crm_sync', document.getElementById('crmSync').checked ? '1' : '0');

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
      const stepLabels = {adresselectie:'Adresselectie',scoring:'Scoring',render:'Renders',flyer:'Flyers',landing:'Landing pages',email:'E-mails'};
      const label = stepLabels[s.current_step] || 'Bezig';
      document.getElementById('elapsedStatus').innerHTML = label + '<span class="elapsed-dots" id="elapsedDots">.</span>';
      document.getElementById('elapsedStatus').style.color = '#60a5fa';
    }
  } else {
    bar.classList.add('hidden');
  }

  // Steps
  const stepNames = ['adresselectie','scoring','render','flyer','landing','email'];
  const nums = {adresselectie:'1',scoring:'2',render:'3',flyer:'4',landing:'5',email:'6'};

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
    if (s.summary.scoring) {
      summary += `Scoring: ${s.summary.scoring.total} leads (gem. ${s.summary.scoring.avg_score}). `;
    }
    summary += `${s.output_files.length} output bestanden gegenereerd.`;
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
    div.innerHTML = `<img src="${imgSrc}" loading="lazy" onerror="this.style.display='none'">
      <div class="overlay"><span>${item.id.substring(0,25)}${label ? '<br>'+label : ''}</span></div>`;
    div.onclick = () => selectRender(item);
    gallery.appendChild(div);
  }
  galleryLoaded = true;
}

function selectRender(item) {
  selectedRenderId = item.id;

  // Update gallery selection
  document.querySelectorAll('.render-thumb').forEach(el => el.classList.remove('selected'));
  event.currentTarget.classList.add('selected');

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
  title.textContent = item.id;
  const content = document.getElementById('previewContent');
  content.innerHTML = `<div class="preview-grid">
    ${item.streetview ? `<div class="preview-item"><div class="label">Street View</div><img src="/files/${item.streetview}"></div>` : ''}
    ${item.render ? `<div class="preview-item"><div class="label">Gevelrenovatie render</div><img src="/files/${item.render}?t=${Date.now()}"></div>` : '<div class="preview-item" style="display:flex;align-items:center;justify-content:center;min-height:200px;color:#fca5a5">Geen render</div>'}
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
    if (p.facade_preset) document.getElementById('facadePreset').value = p.facade_preset;
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
  body.set('facade_preset', document.getElementById('facadePreset').value);

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

// ─── KAART (Leaflet + MarkerCluster) ────────────────────────────────────
let _map = null;
let _markerCluster = null;

const KLASSE_KLEUR = {
  "A+": "#22c55e",
  "A":  "#4ade80",
  "B":  "#60a5fa",
  "C":  "#fbbf24",
  "D":  "#94a3b8",
};

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
  const r = await fetch('/api/leads_geojson');
  const data = await r.json();
  const features = data.features || [];
  if (features.length === 0) {
    document.getElementById('mapMeta').textContent = 'Geen leads — draai eerst de pipeline';
    return;
  }
  const bounds = [];
  for (const f of features) {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    const kleur = KLASSE_KLEUR[p.klasse] || '#94a3b8';
    const radius = p.klasse === 'A+' ? 9 : (p.klasse === 'A' ? 7 : 5);
    const marker = L.circleMarker([lat, lon], {
      radius: radius,
      fillColor: kleur,
      color: '#fff',
      weight: 1.5,
      opacity: 0.9,
      fillOpacity: 0.85,
      klasse: p.klasse,
    });
    let popup = `<div class="pop-adres">${p.adres || '(geen adres)'}</div>`;
    popup += `<div class="pop-meta">Klasse <b style="color:${kleur}">${p.klasse}</b> • Score ${(p.score||0).toFixed(1)} • ${p.huistype || 'huistype ?'}</div>`;
    popup += `<div class="pop-meta">Status: <b>${p.status}</b> • ${(p.bebouwd_m2||0).toFixed(0)}m² gevel</div>`;
    if (p.render_path) {
      popup += `<img src="/files/${p.render_path}" alt="">`;
    }
    marker.bindPopup(popup);
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
    list.innerHTML = `<b>${items.length}</b> adres${items.length > 1 ? 'sen' : ''}: ` +
      items.slice(0, 5).map(i => i.adres.substring(0, 35)).join(', ') +
      (items.length > 5 ? ` + ${items.length - 5} meer` : '');
    btn.style.display = 'block';
  }
}

async function clearManual() {
  if (!confirm('Wis alle handmatige adressen?')) return;
  await fetch('/api/manual_clear', {method: 'POST'});
  refreshManualList();
}

async function manualRun() {
  const r = await fetch('/api/manual_run', {method: 'POST'});
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

loadGemeenten();
loadCSVs();
loadModules();
loadProfile();
refreshManualList();
poll();
setInterval(poll, 1000);
</script>
</body>
</html>
"""


# ─── HTTP HANDLER ─────────────────────────────────────────────────────────────

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
        elif url.path == "/api/flyer_editor_assets":
            try:
                from homepilot_shared.flyer_editor import flyer_editor_payload
                with state_lock:
                    default_niscode = pipeline_state.get("niscode", "")
                self._json(flyer_editor_payload(
                    HERE,
                    profile=load_builder_profile(),
                    public_base_url=os.environ.get("FACADEPILOT_TRACKER_URL", "https://facadepilot.be"),
                    default_niscode=default_niscode,
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
                    profile=load_builder_profile(),
                    public_base_url=os.environ.get("FACADEPILOT_TRACKER_URL", "https://facadepilot.be"),
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
        elif url.path == "/api/renders":
            self._json(list_render_details())
        elif url.path == "/api/leads_geojson":
            qs = parse_qs(url.query)
            niscode = (qs.get("niscode", [""])[0] or "").strip() or None
            self._json(get_leads_geojson(niscode))
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
        elif url.path.startswith("/files/"):
            self._serve_file(url.path[7:])  # strip "/files/"
        else:
            self.send_response(404)
            self.end_headers()

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

    def do_POST(self):
        url = urlparse(self.path)
        content_type = self.headers.get("Content-Type", "")
        json_body = {}
        if "multipart/form-data" in content_type:
            # Upload handlers read the raw body themselves.
            raw = ""
            data = {}
        else:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            if "application/json" in content_type and raw:
                try:
                    loaded = json.loads(raw)
                    json_body = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    json_body = {}
            data = {} if json_body else parse_qs(raw)

        def g(key, default=""):
            if key in json_body:
                value = json_body.get(key, default)
                return str(value if value is not None else default).strip()
            return (data.get(key, [default])[0] or default).strip()

        if url.path == "/api/start":
            with state_lock:
                if pipeline_state["running"]:
                    return self._json({"error": "Pipeline loopt al"}, 409)

            reset_state()

            # Load builder profile
            profile = load_builder_profile()

            quality_check = g("quality_check", "1") == "1"
            multi_preset_on = g("multi_preset", "0") == "1"

            config = {
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
                "facade_preset": g("facade_preset") or profile.get("facade_preset", DEFAULT_FACADE_PRESET),
                "builder_profile": profile,
                "flyer_format": "both",
                "flyer_top": None,
                "quality_check": quality_check,
                "multi_preset_klassen": ["A+"] if multi_preset_on else None,
                "multi_presets": ["moderne_crepi", "baksteen_rejoint", "totaalrenovatie"] if multi_preset_on else None,
                "auto_preset": g("auto_preset", "0") == "1",
                "flyer_style": g("flyer_style", "premium"),
                "vergunning_filter": g("vergunning_filter", "1") == "1",
                "crm_sync": g("crm_sync", "1") == "1",
                "landing_base_url": "https://facadepilot.be",
                "steps": {
                    "adresselectie": g("step_adres", "1") == "1",
                    "scoring": g("step_score", "1") == "1",
                    "render": g("step_render", "1") == "1",
                    "flyer": g("step_flyer", "1") == "1",
                    "landing": g("step_landing", "1") == "1",
                    "email": g("step_email", "0") == "1",
                },
            }

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

        elif url.path == "/api/manual_address":
            try:
                from facadepilot_manueel import add_manual_address, append_to_csv
                adres = g("adres")
                with_perceel = g("with_perceel", "0") == "1"
                if not adres:
                    return self._json({"ok": False, "error": "adres ontbreekt"}, 400)
                rec = add_manual_address(adres, with_perceel=with_perceel)
                if not rec:
                    return self._json({"ok": False, "error": "geocoding mislukt"}, 400)
                append_to_csv(rec)
                self._json({"ok": True, "rec": rec})
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
                config = {
                    "niscode": "",
                    "input_csv": "manual_leads.csv",
                    "render_top": None,
                    "render_klassen": None,
                    "builder_naam": profile.get("naam", "Uw Gevelrenoveerder"),
                    "builder_telefoon": profile.get("telefoon", "0800 00 000"),
                    "facade_preset": profile.get("facade_preset", DEFAULT_FACADE_PRESET),
                    "builder_profile": profile,
                    "flyer_format": "both",
                    "flyer_top": None,
                    # Manueel = jij koos het adres bewust → quality check is overkill
                    "quality_check": False,
                    "auto_preset": True,  # express → laat selector kiezen
                    "flyer_style": "auto",  # express → kies stijl per huistype
                    "vergunning_filter": False,
                    "crm_sync": True,
                    "landing_base_url": "https://facadepilot.be",
                    "steps": {
                        "adresselectie": False,
                        "scoring": False,
                        "render": True,
                        "flyer": True,
                        "landing": True,
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

        elif url.path == "/api/flyer_editor_export":
            try:
                from homepilot_shared.flyer_editor import save_flyer_editor_export
                payload = json_body if json_body else {k: v[0] for k, v in data.items() if v}
                result = save_flyer_editor_export(HERE, payload)
                self._json(result, 200 if result.get("ok") else 400)
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
            save_builder_profile(profile)
            self._json({"ok": True, "profile": profile})

        elif url.path == "/api/upload_logo":
            self._handle_logo_upload()

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

        renders_dir = HERE / "renders"
        target = renders_dir / f"{render_id}_render.jpg"

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


def main():
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
        port = find_free_port()
    except RuntimeError as e:
        sys.exit(f"   FOUT: {e}")

    if port != DEFAULT_PORT:
        print(f"    Poort {DEFAULT_PORT} is bezet → gebruik poort {port}")

    server = ThreadedServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print(f"    Dashboard: {url}")
    print("    Druk Ctrl+C om te stoppen.\n")

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
