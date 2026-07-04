#!/usr/bin/env python3
"""
FacadePilot Gevelrenovatie Render — GPT Image 2
=================================================
Genereert fotorealistische renovatie-renders van gevels
op basis van Google Street View foto's.

Workflow:
  1. Neem de gescoorde CSV als input
  2. Per lead: haal Street View foto op (of gebruik bestaande)
  3. Stuur foto + renovatie-prompt naar GPT Image 2
  4. Sla de render op als before/after paar
  5. Voeg render-pad toe aan CSV

Vereist:
  - OPENAI_API_KEY in .env
  - GOOGLE_API_KEY in .env (voor Street View)

Gebruik:
  python3 facadepilot_render.py --input scored.csv --top 10
  python3 facadepilot_render.py --input scored.csv --preset moderne_crepi
  python3 facadepilot_render.py --input scored.csv --single 0
"""

import argparse
import base64
import io
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from PIL import Image
from dotenv import load_dotenv

from facadepilot_keys import (
    first_existing,
    legacy_render_candidates,
    legacy_streetview_candidates,
    render_path as stable_render_path,
    streetview_path as stable_streetview_path,
)

HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

# Cost tracker (module-level) — wordt door pipeline uitgelezen
_render_cost_state = {
    "renders_done": 0,
    "renders_skipped_quality": 0,
    "estimated_cost_usd": 0.0,
}
COST_PER_RENDER_USD = 0.10  # GPT Image 2 (1536x1024)


def get_render_cost_state() -> dict:
    return dict(_render_cost_state)


def reset_render_cost_state():
    _render_cost_state.update({
        "renders_done": 0,
        "renders_skipped_quality": 0,
        "estimated_cost_usd": 0.0,
    })

# ─── FACADE PRESETS ─────────────────────────────────────────────────────────

# Strikte preservatie-instructie die aan elk preset wordt toegevoegd
_PRESERVE_RULE = (
    "STRIKT: behoud de EXACTE positie, grootte en aantal van alle ramen en deuren. "
    "Verplaats NIETS. Verander alleen materiaal en afwerking van de gevel. "
    "De gevelindeling (waar ramen en deuren zitten) blijft 100% identiek. "
    "Verander NIET de dakvorm. Focus uitsluitend op het middelste/aangewezen huis, "
    "NIET op buurhuizen of bijgebouwen. Omgeving (straat, buren, beplanting, auto's) "
    "blijft volledig ongewijzigd. Fotorealistisch."
)

FACADE_PRESETS = {
    "moderne_crepi": {
        "label": "Moderne crépi-afwerking",
        "prompt": (
            "Renoveer ALLEEN de gevel van het centrale huis op de foto. Geef het een "
            "moderne uitstraling met een strakke witte crépi-afwerking. De bestaande "
            "ramen krijgen donkergrijze aluminium profielen, de bestaande voordeur "
            "krijgt een moderne afwerking. Voeg subtiele buitenverlichting toe. "
            + _PRESERVE_RULE
        ),
        "afmeting": '100<span class="unit">m²</span>',
        "afmeting_label": "Geveloppervlak",
        "prijs": 'vanaf <span class="unit">€20K</span>',
        "bouwtijd": '3–6<span class="unit">wk</span>',
    },
    "baksteen_rejoint": {
        "label": "Baksteen gevelreiniging + hervoegen",
        "prompt": (
            "Renoveer ALLEEN de bakstenen gevel van het centrale huis. De bakstenen worden "
            "gereinigd en opnieuw gevoegd met lichtgrijze mortel. De bestaande ramen krijgen "
            "donkergrijze aluminium profielen. De bestaande voordeur krijgt een moderne "
            "afwerking. Voeg subtiele buitenverlichting toe. "
            + _PRESERVE_RULE
        ),
        "afmeting": '80<span class="unit">m²</span>',
        "afmeting_label": "Geveloppervlak",
        "prijs": 'vanaf <span class="unit">€12K</span>',
        "bouwtijd": '2–4<span class="unit">wk</span>',
    },
    "isolatie_gevelbekleding": {
        "label": "Buitenisolatie + gevelbekleding",
        "prompt": (
            "Renoveer ALLEEN de gevel van het centrale huis met buitenisolatie en moderne "
            "gevelbekleding. De gevel krijgt een combinatie van lichte crépi op de "
            "verdiepingen en donkere gevelpanelen (composiet of hout-look) als accent "
            "op de benedenverdieping. De bestaande ramen krijgen strakke aluminium "
            "profielen. Voeg designverlichting bij de voordeur toe. "
            + _PRESERVE_RULE
        ),
        "afmeting": '120<span class="unit">m²</span>',
        "afmeting_label": "Isolatie + bekleding",
        "prijs": 'vanaf <span class="unit">€30K</span>',
        "bouwtijd": '4–8<span class="unit">wk</span>',
    },
    "totaalrenovatie": {
        "label": "Totale gevelrenovatie",
        "prompt": (
            "Voer een complete gevelrenovatie uit op ALLEEN het centrale huis. Geef de "
            "gevel een luxueuze afwerking met een mix van materialen: witte crépi als basis, "
            "natuursteen accent rond de bestaande voordeur, subtiel houten latwerk, en "
            "ingebouwde LED-verlichting. De bestaande ramen krijgen minimale profielen. "
            + _PRESERVE_RULE
        ),
        "afmeting": '150<span class="unit">m²</span>',
        "afmeting_label": "Totaalrenovatie",
        "prijs": 'vanaf <span class="unit">€50K</span>',
        "bouwtijd": '8–14<span class="unit">wk</span>',
    },
}

DEFAULT_PRESET = "moderne_crepi"
DEFAULT_PROMPT = FACADE_PRESETS[DEFAULT_PRESET]["prompt"]

# GPT Image model
IMAGE_MODEL = "gpt-image-2"
IMAGE_SIZE = "1536x1024"  # Landscape — past bij Street View formaat

REQUEST_DELAY = 1.0


# ─── STREET VIEW OPHALEN ───────────────────────────────────────────────────

def fetch_streetview_for_render(lat: float, lon: float) -> Image.Image:
    """Haal Street View foto op via de streetview module."""
    from facadepilot_streetview import fetch_streetview
    return fetch_streetview(lat, lon)


# ─── GPT IMAGE RENDER ──────────────────────────────────────────────────────

def image_to_bytesio(img: Image.Image, fmt: str = "PNG") -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    buf.name = "streetview.png"
    return buf


def render_facade(streetview_img: Image.Image, prompt: str = DEFAULT_PROMPT,
                  size: str = IMAGE_SIZE, max_retries: int = 3) -> Image.Image:
    """
    Stuur Street View foto naar GPT Image 2 voor gevelrenovatie render.

    Retry-strategie:
      - 3 pogingen totaal
      - Exponential backoff: 2s, 4s, 8s
      - 4xx (behalve 429) → geen retry (request is fundamenteel fout)
      - 5xx, 429, connection-errors, timeouts → wel retry
      - Bij definitieve fail: raise originele exception (caller schrijft naar failed_renders.csv)
    """
    from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError

    client = OpenAI()
    last_exc = None

    for attempt in range(max_retries):
        try:
            # Buffer moet per poging opnieuw geopend worden (read-after-EOF)
            img_buf = image_to_bytesio(streetview_img, "PNG")

            response = client.images.edit(
                model=IMAGE_MODEL,
                image=img_buf,
                prompt=prompt,
                size=size,
            )
            result = response.data[0]

            if hasattr(result, "b64_json") and result.b64_json:
                out_bytes = base64.b64decode(result.b64_json)
                return Image.open(io.BytesIO(out_bytes)).convert("RGB")
            elif hasattr(result, "url") and result.url:
                r = requests.get(result.url, timeout=60)
                r.raise_for_status()
                return Image.open(io.BytesIO(r.content)).convert("RGB")
            else:
                raise ValueError("Geen afbeelding ontvangen van de API")

        except (APIConnectionError, APITimeoutError) as e:
            # Netwerk/timeout — altijd retry
            last_exc = e
            backoff = 2 ** (attempt + 1)
            if attempt < max_retries - 1:
                print(f"           ⚠ Connection/timeout (poging {attempt+1}/{max_retries}), "
                      f"retry over {backoff}s: {str(e)[:80]}")
                time.sleep(backoff)
            else:
                raise

        except RateLimitError as e:
            # 429 — retry met langere wait
            last_exc = e
            backoff = 5 * (attempt + 1)
            if attempt < max_retries - 1:
                print(f"           ⚠ Rate limit (poging {attempt+1}/{max_retries}), "
                      f"retry over {backoff}s")
                time.sleep(backoff)
            else:
                raise

        except APIError as e:
            # OpenAI API-fout: 5xx wel retry, 4xx niet
            last_exc = e
            status = getattr(e, "status_code", None) or getattr(e, "http_status", None) or 500
            if status >= 500 and attempt < max_retries - 1:
                backoff = 2 ** (attempt + 1)
                print(f"           ⚠ API {status} (poging {attempt+1}/{max_retries}), "
                      f"retry over {backoff}s")
                time.sleep(backoff)
            else:
                raise

        except requests.RequestException as e:
            # Netwerk-fout op resultaat-download
            last_exc = e
            if attempt < max_retries - 1:
                backoff = 2 ** (attempt + 1)
                print(f"           ⚠ Download-fout (poging {attempt+1}/{max_retries}), "
                      f"retry over {backoff}s")
                time.sleep(backoff)
            else:
                raise

    # Onbereikbaar maar voor de zekerheid
    if last_exc:
        raise last_exc
    raise RuntimeError("render_facade: max retries opgebruikt zonder fout")


def _log_failed_render(output_dir: Path, idx: int, adres: str, capakey: str,
                       lat: float, lon: float, reason: str):
    """Schrijf gefaalde render naar failed_renders.csv voor latere retry."""
    import csv
    failed_csv = output_dir.parent / "failed_renders.csv"
    write_header = not failed_csv.exists()
    try:
        with open(failed_csv, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["timestamp", "idx", "adres", "CAPAKEY", "lat", "lon", "reason"])
            w.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                idx, adres, capakey,
                lat or "", lon or "",
                reason[:200],
            ])
    except Exception:
        pass  # nooit blokkeren op log-fout


# ─── BATCH VERWERKING ────────────────────────────────────────────────────────

def process_renders(df: pd.DataFrame, output_dir: Path,
                    prompt: str = DEFAULT_PROMPT, size: str = IMAGE_SIZE,
                    progress_callback=None,
                    quality_check: bool = True,
                    multi_preset_for_klassen: list = None,
                    multi_presets: list = None,
                    auto_preset: bool = False,
                    preset_key: str = "default") -> pd.DataFrame:
    """Genereer gevelrenovatie-renders voor alle rijen.

    Parameters
    ----------
    quality_check : bool
        Als True (default): elke Street View foto wordt eerst gevalideerd
        met gpt-4o-mini. Faalt de check → render wordt overgeslagen
        (bespaart ~$0.10 per slechte foto).
    multi_preset_for_klassen : list[str] of None
        Bij welke lead_klassen extra renders moeten gemaakt worden, bv.
        ["A+"] om voor topkandidaten 3 stijlen te tonen.
    multi_presets : list[str] of None
        Lijst van preset-keys (uit FACADE_PRESETS) die extra gerenderd
        moeten worden voor bovenstaande klassen. Bv.
        ["moderne_crepi", "baksteen_rejoint", "totaalrenovatie"]
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(df)
    render_paths = [""] * total
    streetview_paths = [""] * total
    quality_results = [{"pass": False, "reason": "not_processed"} for _ in range(total)]
    extra_render_paths = [{} for _ in range(total)]
    success = 0
    errors = 0
    skipped_quality = 0

    # Quality check module lazy-importeren
    quality_checker = None
    if quality_check:
        try:
            from facadepilot_quality_check import check_facade_quality
            quality_checker = check_facade_quality
        except ImportError:
            print("   ⚠️  facadepilot_quality_check niet beschikbaar — kwaliteitscheck uit")
            quality_check = False

    # Auto-preset selector lazy-importeren
    preset_selector = None
    if auto_preset:
        try:
            from facadepilot_facade_selector import select_preset_for_row
            preset_selector = select_preset_for_row
        except ImportError:
            print("   ⚠️  facadepilot_facade_selector niet beschikbaar — auto-preset uit")
            auto_preset = False

    print(f"\n🏠 FacadePilot Gevelrenovatie Render — {total} leads")
    print(f"   Model: {IMAGE_MODEL} | Formaat: {size}")
    print(f"   Quality check: {'AAN (gpt-4o-mini)' if quality_check else 'UIT'}")
    print(f"   Auto-preset:   {'AAN (per lead)' if auto_preset else 'UIT (vaste preset)'}")
    if multi_preset_for_klassen and multi_presets:
        print(f"   Multi-preset: {multi_presets} voor klassen {multi_preset_for_klassen}")
        estimated_extra = 0
        if "lead_klasse" in df.columns:
            estimated_extra = int(df["lead_klasse"].astype(str).isin(multi_preset_for_klassen).sum()) * len(multi_presets)
        else:
            estimated_extra = total * len(multi_presets)
        print(f"   Kostenraming: {total + estimated_extra} mogelijke renders ≈ ${(total + estimated_extra) * COST_PER_RENDER_USD:.2f}")
    print(f"   Output: {output_dir}/")
    print()

    auto_preset_results = [{"key": "", "reden": ""} for _ in range(total)]

    t_start = time.time()

    for i, (idx, row) in enumerate(df.iterrows()):
        adres = str(row.get("adres", f"rij_{i}"))

        # Bepaal welke preset_key we voor de hoofdrender gebruiken (voor filename)
        # — bij auto_preset wordt dit per rij overschreven verderop
        active_preset_key = preset_key if preset_key in FACADE_PRESETS else DEFAULT_PRESET
        row_prompt = prompt
        row_preset_key = ""
        row_preset_reden = ""
        if auto_preset and preset_selector is not None:
            selected_key, selected_reden = preset_selector(row)
            if selected_key in FACADE_PRESETS:
                active_preset_key = selected_key
                row_prompt = FACADE_PRESETS[selected_key]["prompt"]
                row_preset_key = selected_key
                row_preset_reden = selected_reden
            auto_preset_results[i] = {"key": row_preset_key, "reden": row_preset_reden}

        # Skip als render al bestaat — probeer eerst preset-specifieke naam,
        # dan legacy naam zonder preset (backward compatible)
        render_candidates = [
            stable_render_path(output_dir, row, i, active_preset_key),
            *legacy_render_candidates(output_dir, row, i, active_preset_key),
        ]
        existing_render = first_existing(render_candidates)
        if existing_render:
            existing_streetview = first_existing([
                stable_streetview_path(output_dir, row, i),
                *legacy_streetview_candidates(output_dir, row, i),
            ])
            print(f"   [{i+1}/{total}] {adres[:50]}... ⏭️ al gerenderd ({existing_render.name})")
            render_paths[i] = str(existing_render)
            streetview_paths[i] = str(existing_streetview) if existing_streetview else ""
            quality_results[i] = {"pass": True, "reason": "cached"}
            extra_render_paths[i] = {}
            success += 1
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ⏭️ {adres[:40]}... (al gerenderd)")
            continue

        try:
            # Stap 1: Street View foto ophalen
            print(f"   [{i+1}/{total}] {adres[:50]}...")
            if progress_callback:
                progress_callback(i, total, f"[{i+1}/{total}] 📸 Street View ophalen: {adres[:40]}...")

            streetview = fetch_streetview_for_render(row["lat"], row["lon"])

            # Sla Street View foto op (before)
            sv_path = stable_streetview_path(output_dir, row, i)
            streetview.save(sv_path, "JPEG", quality=90)
            streetview_paths[i] = str(sv_path)

            # Stap 1b: Pre-render kwaliteitscheck
            if quality_check and quality_checker is not None:
                print(f"           → Kwaliteitscheck...", end="", flush=True)
                if progress_callback:
                    progress_callback(i, total, f"[{i+1}/{total}] 🔍 Kwaliteitscheck: {adres[:40]}...")
                qc = quality_checker(streetview)
                if not qc["pass"]:
                    print(f" ❌ skip ({qc['type']}: {qc['reason']})")
                    render_paths[i] = ""
                    streetview_paths[i] = str(sv_path)
                    quality_results[i] = qc
                    extra_render_paths[i] = {}
                    skipped_quality += 1
                    _render_cost_state["renders_skipped_quality"] += 1
                    if progress_callback:
                        progress_callback(i + 1, total,
                            f"[{i+1}/{total}] ⏭️ {adres[:40]}... skip ({qc['type']})")
                    if i < total - 1:
                        time.sleep(REQUEST_DELAY)
                    continue
                print(f" ✅ ({qc['type']})")
                quality_results[i] = qc
            else:
                quality_results[i] = {"pass": True, "reason": "check uit"}

            # Stap 2: Hoofdrender (eventueel met auto-gekozen preset)
            file_preset_key = active_preset_key
            if row_preset_key:
                print(f"           → Auto-preset: {row_preset_key} ({row_preset_reden})")

            print(f"           → Render genereren...", end="", flush=True)
            if progress_callback:
                progress_callback(i, total, f"[{i+1}/{total}] 🎨 Render genereren: {adres[:40]}...")

            t0 = time.time()
            render = render_facade(streetview, prompt=row_prompt, size=size)
            elapsed = time.time() - t0
            print(f" ✅ ({elapsed:.1f}s)")

            # Schrijf met preset-specifieke naam zodat varianten naast elkaar kunnen
            render_path = stable_render_path(output_dir, row, i, file_preset_key)
            render.save(render_path, "JPEG", quality=95)
            render_paths[i] = str(render_path)
            streetview_paths[i] = str(sv_path)
            success += 1
            _render_cost_state["renders_done"] += 1
            _render_cost_state["estimated_cost_usd"] += COST_PER_RENDER_USD

            # Stap 3 (optioneel): multi-preset extra renders voor topklassen
            extra_paths_for_row = {}
            klasse = str(row.get("lead_klasse", ""))
            if (multi_preset_for_klassen and multi_presets
                    and klasse in multi_preset_for_klassen):
                for preset_key in multi_presets:
                    if preset_key not in FACADE_PRESETS:
                        continue
                    extra_path = output_dir / f"{stable_render_path(output_dir, row, i, preset_key).stem}_extra.jpg"
                    if extra_path.exists():
                        extra_paths_for_row[preset_key] = str(extra_path)
                        continue
                    extra_prompt = FACADE_PRESETS[preset_key]["prompt"]
                    print(f"           → Extra render ({preset_key})...", end="", flush=True)
                    try:
                        t0 = time.time()
                        extra_render = render_facade(streetview, prompt=extra_prompt, size=size)
                        extra_render.save(extra_path, "JPEG", quality=95)
                        extra_paths_for_row[preset_key] = str(extra_path)
                        _render_cost_state["renders_done"] += 1
                        _render_cost_state["estimated_cost_usd"] += COST_PER_RENDER_USD
                        print(f" ✅ ({time.time()-t0:.1f}s)")
                    except Exception as e:
                        print(f" ❌ {e}")
                    time.sleep(REQUEST_DELAY)
            extra_render_paths[i] = extra_paths_for_row

            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ✅ {adres[:40]}... ({elapsed:.0f}s)")

        except Exception as e:
            print(f"           → ❌ Fout: {e}")
            render_paths[i] = ""
            quality_results[i] = {"pass": False, "reason": f"fetch/render fout: {str(e)[:80]}"}
            extra_render_paths[i] = {}
            errors += 1
            # Log naar failed_renders.csv voor latere retry
            _log_failed_render(
                output_dir, i, adres,
                str(row.get("CAPAKEY", "") or ""),
                row.get("lat"), row.get("lon"),
                f"{type(e).__name__}: {str(e)}"
            )
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ❌ {adres[:40]}... fout")

        if i < total - 1:
            time.sleep(REQUEST_DELAY)

    df = df.copy()
    df["render_path"] = render_paths
    df["streetview_path"] = streetview_paths
    df["render_quality_pass"] = [q["pass"] for q in quality_results]
    df["render_quality_type"] = [q.get("type", "") for q in quality_results]
    df["render_quality_reason"] = [q.get("reason", "") for q in quality_results]
    if auto_preset:
        df["preset_auto"] = [a["key"] for a in auto_preset_results]
        df["preset_reden"] = [a["reden"] for a in auto_preset_results]

    # Multi-preset paden als extra kolommen
    if multi_preset_for_klassen and multi_presets:
        for preset_key in multi_presets:
            col_name = f"render_path_{preset_key}"
            df[col_name] = [extras.get(preset_key, "") for extras in extra_render_paths]

    elapsed_total = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  ✅ {success} renders gegenereerd, {errors} fouten, {skipped_quality} skip (kwaliteit)")
    print(f"  ⏱️  Totale tijd: {elapsed_total:.0f}s ({elapsed_total/max(total,1):.1f}s/render)")
    print(f"  💰 Geschatte renderkosten: ${_render_cost_state['estimated_cost_usd']:.2f}")
    print(f"  📁 Output: {output_dir}/")
    print(f"{'='*60}\n")

    return df


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Gevelrenovatie Render")
    parser.add_argument("--input", required=True, type=Path, help="Input CSV")
    parser.add_argument("--output-dir", type=Path, default=None, help="Map voor renders")
    parser.add_argument("--top", type=int, default=None, help="Top N leads")
    parser.add_argument("--klasse", action="append", default=None, help="Filter op klasse")
    parser.add_argument("--single", type=int, default=None, help="Render alleen rij N")
    parser.add_argument("--preset", choices=list(FACADE_PRESETS.keys()),
                        default=DEFAULT_PRESET, help="Renovatie type")
    parser.add_argument("--size", choices=["1024x1024", "1536x1024", "1024x1536"],
                        default=IMAGE_SIZE, help="Render formaat")
    parser.add_argument("--prompt", type=str, default=None, help="Custom prompt")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"❌ Niet gevonden: {args.input}")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("❌ OPENAI_API_KEY niet gevonden")
    if not os.environ.get("GOOGLE_API_KEY"):
        sys.exit("❌ GOOGLE_API_KEY niet gevonden")

    df = pd.read_csv(args.input, encoding="utf-8-sig")
    print(f"📊 {len(df)} leads ingelezen")

    if args.klasse and "lead_klasse" in df.columns:
        df = df[df["lead_klasse"].isin(args.klasse)].copy()
        print(f"   → Gefilterd op klasse {args.klasse}: {len(df)} leads")

    if args.single is not None:
        df = df.iloc[[args.single]].copy()

    if args.top:
        df = df.head(args.top).copy()

    output_dir = args.output_dir or HERE / "renders"
    preset = FACADE_PRESETS[args.preset]
    prompt = args.prompt or preset["prompt"]
    print(f"   → Renovatietype: {preset['label']}")

    result = process_renders(df, output_dir, prompt=prompt, size=args.size)

    output_csv = args.input.with_name(args.input.stem + "_with_renders.csv")
    result.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"📄 CSV met render-paden: {output_csv.name}")


if __name__ == "__main__":
    main()
