#!/usr/bin/env python3
"""
FacadePilot Flyer Generator
=============================
Genereert gepersonaliseerde before/after flyers als PDF voor gevelrenovatie.

Het verschil met PoolPilot:
  - Before = Street View foto (landscape), After = renovatie-render
  - Andere headlines, facts en argumenten (gevelrenovatie i.p.v. zwembad)
  - Landscape beeldformaat i.p.v. vierkant

Gebruik:
  python3 facadepilot_flyer.py --input scored_with_renders.csv --format a4
  python3 facadepilot_flyer.py --input scored_with_renders.csv --single 0
"""

import argparse
import asyncio
import base64
import io
import os
import sys
import time
from pathlib import Path

import pandas as pd
import qrcode
from jinja2 import Template
from PIL import Image

from facadepilot_keys import (
    first_existing,
    legacy_index_stem,
    legacy_streetview_candidates,
    output_stem,
    slugify,
    streetview_path as stable_streetview_path,
)

HERE = Path(__file__).parent.resolve()

# ─── CONFIG ──────────────────────────────────────────────────────────────────

DEFAULT_BUILDER = "Uw Gevelspecialist"
DEFAULT_TELEFOON = "0800 00 000"
DEFAULT_LANDING_URL = "facadepilot.be"


# ─── A4 FLYER TEMPLATE (inline — geen apart templatebestand nodig) ─────────

FLYER_A4_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 210mm; height: 297mm; }

body {
    font-family: 'Inter', sans-serif;
    background: #ffffff;
    color: #1a1a1a;
}

.page {
    width: 210mm;
    height: 297mm;
    padding: 12mm;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
}

.header {
    text-align: center;
    margin-bottom: 6mm;
}
.header h1 {
    font-size: 22pt;
    font-weight: 800;
    color: {{ accent_color | default('#2563eb') }};
    line-height: 1.2;
}
.header h2 {
    font-size: 11pt;
    font-weight: 400;
    color: #6b7280;
    margin-top: 2mm;
}

.address-badge {
    background: {{ accent_color | default('#2563eb') }};
    color: white;
    padding: 2mm 5mm;
    border-radius: 4mm;
    font-size: 10pt;
    font-weight: 600;
    text-align: center;
    margin-bottom: 5mm;
}

.images {
    display: flex;
    gap: 3mm;
    margin-bottom: 5mm;
}
.img-box {
    flex: 1;
    position: relative;
    border-radius: 3mm;
    overflow: hidden;
    border: 1px solid #e5e7eb;
}
.img-box img {
    width: 100%;
    height: auto;
    display: block;
}
.img-label {
    position: absolute;
    top: 2mm;
    left: 2mm;
    background: rgba(0,0,0,0.7);
    color: white;
    padding: 1mm 3mm;
    border-radius: 2mm;
    font-size: 8pt;
    font-weight: 600;
}
.img-label.after {
    background: {{ accent_color | default('#2563eb') }};
}

.facts {
    display: flex;
    gap: 3mm;
    margin-bottom: 5mm;
}
.fact {
    flex: 1;
    text-align: center;
    padding: 3mm;
    background: #f9fafb;
    border-radius: 2mm;
    border: 1px solid #e5e7eb;
}
.fact .value {
    font-size: 16pt;
    font-weight: 700;
    color: {{ accent_color | default('#2563eb') }};
}
.fact .label {
    font-size: 7pt;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.arguments {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2mm;
    margin-bottom: 5mm;
}
.argument {
    display: flex;
    align-items: flex-start;
    gap: 2mm;
    padding: 2mm;
}
.argument .icon {
    font-size: 14pt;
    flex-shrink: 0;
}
.argument .text {
    font-size: 9pt;
    line-height: 1.3;
}
.argument .text strong {
    display: block;
    font-weight: 600;
}

.cta {
    background: {{ accent_color | default('#2563eb') }};
    color: white;
    padding: 5mm;
    border-radius: 3mm;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: auto;
}
.cta-text {
    font-size: 12pt;
    font-weight: 700;
}
.cta-sub {
    font-size: 9pt;
    opacity: 0.9;
}
.cta-right {
    display: flex;
    align-items: center;
    gap: 3mm;
}
.cta-right img {
    width: 20mm;
    height: 20mm;
}
.cta-info {
    text-align: right;
    font-size: 9pt;
}
</style>
</head>
<body>
<div class="page">
    <div class="header">
        <h1>{{ headline | default('Wat als uw gevel er zó uitzag?') }}</h1>
        <h2>{{ subheadline | default('Een persoonlijke simulatie voor uw woning') }}</h2>
    </div>

    <div class="address-badge">📍 {{ adres_kort }}</div>

    <div class="images">
        <div class="img-box">
            {% if aerial_path %}<img src="{{ aerial_path }}" alt="Huidige gevel">{% endif %}
            <div class="img-label">HUIDIGE GEVEL</div>
        </div>
        <div class="img-box">
            {% if render_path %}<img src="{{ render_path }}" alt="Na renovatie">{% endif %}
            <div class="img-label after">NA RENOVATIE</div>
        </div>
    </div>

    <div class="facts">
        <div class="fact">
            <div class="value">{{ facade_afmeting | default('100m²') }}</div>
            <div class="label">{{ facade_afmeting_label | default('Geveloppervlak') }}</div>
        </div>
        <div class="fact">
            <div class="value">{{ facade_prijs | default('vanaf €20K') }}</div>
            <div class="label">Indicatieprijs</div>
        </div>
        <div class="fact">
            <div class="value">{{ facade_bouwtijd | default('3–6 wk') }}</div>
            <div class="label">Bouwtijd</div>
        </div>
    </div>

    <div class="arguments">
        <div class="argument">
            <div class="icon">E</div>
            <div class="text"><strong>Lagere energievraag</strong>Buitenisolatie verhoogt comfort en kan het verbruik verlagen</div>
        </div>
        <div class="argument">
            <div class="icon">+</div>
            <div class="text"><strong>Meer comfort en uitstraling</strong>Een verzorgde gevel maakt uw woning aantrekkelijker</div>
        </div>
        <div class="argument">
            <div class="icon">€</div>
            <div class="text"><strong>Premies? Wij checken het</strong>Actuele voorwaarden verschillen per woning en inkomen</div>
        </div>
        <div class="argument">
            <div class="icon">✓</div>
            <div class="text"><strong>Uitstraling van nieuwbouw</strong>Geniet elke dag van een woning die er als nieuw uitziet</div>
        </div>
    </div>

    <div class="cta">
        <div>
            <div class="cta-text">Gratis offerte op maat?</div>
            <div class="cta-sub">Scan de QR-code of bel {{ builder_telefoon }}</div>
        </div>
        <div class="cta-right">
            {% if qr_path %}<img src="{{ qr_path }}" alt="QR">{% endif %}
            <div class="cta-info">
                <strong>{{ builder_naam }}</strong><br>
                {{ landing_url }}
            </div>
        </div>
    </div>
</div>
</body>
</html>"""


# ─── QR CODE ────────────────────────────────────────────────────────────────

def generate_qr_code(url: str, size: int = 200) -> str:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a1a", back_color="white")
    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def image_to_data_uri(img_path: str) -> str:
    path = Path(img_path)
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    suffix = path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64}"


# ─── TEMPLATE LOADING (extern met fallback) ───────────────────────────────

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Cache externe templates
_TPL_CACHE = {}


def _lighten_hex(hex_color: str, factor: float = 0.85) -> str:
    """Maak een hex-kleur lichter (voor argument-icoon achtergrond)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#f4ebe2"


FLYER_STYLES = ("premium", "design", "klassiek")


def select_style_for_row(row) -> str:
    """
    Auto-kies een flyer-stijl op basis van het huistype van de lead.

    Logica:
      - vrijstaand_ruim / halfopen_ruim + A+/A → design (modern statement)
      - rijwoning / stadswoning + oude buurt   → klassiek (atelier)
      - alles anders                            → premium (default)
    """
    huistype = str(row.get("huistype", "") or "").strip()
    klasse = str(row.get("lead_klasse", "") or "").strip()
    pct_oud = row.get("pct_pre_1990")
    try:
        pct_oud = float(pct_oud) if pct_oud is not None else 0.0
    except (TypeError, ValueError):
        pct_oud = 0.0

    if huistype in ("vrijstaand_ruim", "halfopen_ruim") and klasse in ("A+", "A"):
        return "design"
    if huistype in ("rijwoning", "stadswoning") and pct_oud >= 50:
        return "klassiek"
    return "premium"


def load_template(fmt: str, style: str = "premium") -> Template:
    """
    Laad de juiste flyer-template voor het formaat + stijl.

    Stijlen:
      - "premium" (default): warm taupe + Sora/Instrument Serif
      - "design":   brutalist editorial, donker, asymmetrisch (Archivo + Fraunces + JetBrains Mono)
      - "klassiek": atelier bourgeois, ivoor + bordeaux (Playfair + Lora)

    Probeert templates/flyer_a4{_style}.html, valt terug op de premium-versie
    als de stijl-variant ontbreekt, en uiteindelijk op de inline FLYER_A4_TEMPLATE.
    """
    fmt_lc = fmt.lower()
    style_lc = (style or "premium").lower()
    if style_lc not in FLYER_STYLES:
        style_lc = "premium"
    cache_key = f"{fmt_lc}__{style_lc}"
    if cache_key in _TPL_CACHE:
        return _TPL_CACHE[cache_key]

    # Bouw kandidaat-pad. "premium" = geen suffix.
    suffix = "" if style_lc == "premium" else f"_{style_lc}"
    if fmt_lc == "a5":
        candidates = [
            TEMPLATES_DIR / f"flyer_a5_rectoverso{suffix}.html",
            TEMPLATES_DIR / "flyer_a5_rectoverso.html",  # premium fallback
            TEMPLATES_DIR / f"flyer_a4{suffix}.html",     # a4 fallback (zelfde stijl)
            TEMPLATES_DIR / "flyer_a4.html",
        ]
    else:
        candidates = [
            TEMPLATES_DIR / f"flyer_a4{suffix}.html",
            TEMPLATES_DIR / "flyer_a4.html",
        ]

    tpl_str = None
    for cand in candidates:
        if cand.exists():
            tpl_str = cand.read_text(encoding="utf-8")
            print(f"   📄 Template ({style_lc}/{fmt_lc}): {cand.relative_to(Path(__file__).parent)}")
            break

    if tpl_str is None:
        print(f"   ⚠️  Geen externe template gevonden, fallback op inline")
        tpl_str = FLYER_A4_TEMPLATE

    tpl = Template(tpl_str)
    _TPL_CACHE[cache_key] = tpl
    return tpl


# ─── TEMPLATE RENDERING ────────────────────────────────────────────────────

def prepare_lead_variables(row: pd.Series, idx: int,
                           builder_naam: str, builder_telefoon: str,
                           landing_base_url: str, renders_dir: Path,
                           extra_vars: dict = None) -> dict:
    adres = str(row.get("adres", f"Adres {idx}"))
    adres_parts = adres.split(",")
    adres_kort = adres_parts[0].strip() if adres_parts else adres[:30]

    render_path_csv = str(row.get("render_path", ""))
    if render_path_csv and Path(render_path_csv).exists():
        explicit_sv = str(row.get("streetview_path", "") or "").strip()
        if explicit_sv and Path(explicit_sv).exists():
            sv_path = explicit_sv
        else:
            matched_sv = first_existing([
                stable_streetview_path(renders_dir, row, idx),
                *legacy_streetview_candidates(renders_dir, row, idx),
            ])
            sv_path = str(matched_sv) if matched_sv else ""
    else:
        stable_glob = sorted(Path(renders_dir).glob(f"{output_stem(row, idx)}_*_render.jpg"))
        legacy_glob = sorted(Path(renders_dir).glob(f"{legacy_index_stem(row, idx)}*_render.jpg"))
        matched_render = first_existing([*stable_glob, *legacy_glob])
        matched_sv = first_existing([
            stable_streetview_path(renders_dir, row, idx),
            *legacy_streetview_candidates(renders_dir, row, idx),
        ])
        render_path_csv = str(matched_render) if matched_render else ""
        sv_path = str(matched_sv) if matched_sv else ""

    render_uri = image_to_data_uri(render_path_csv)
    aerial_uri = image_to_data_uri(sv_path)

    explicit_landing = str(row.get("landing_url", "") or "").strip()
    if explicit_landing:
        if "src=" in explicit_landing:
            lead_url = explicit_landing
        else:
            lead_url = explicit_landing + ("&" if "?" in explicit_landing else "?") + "src=flyer"
    else:
        tracker_base = os.environ.get("FACADEPILOT_TRACKER_URL", landing_base_url or DEFAULT_LANDING_URL)
        tracker_base = tracker_base if tracker_base.startswith(("http://", "https://")) else f"https://{tracker_base}"
        capakey = str(row.get("CAPAKEY", "") or row.get("capakey", "") or "").strip()
        lead_slug = slugify(capakey) if capakey else f"row-{idx:03d}"
        niscode = str(row.get("niscode", "") or row.get("NISCODE", "") or "").strip()
        route_key = f"{niscode}-{lead_slug}" if niscode else lead_slug
        lead_url = f"{tracker_base.rstrip('/')}/r/{route_key}?src=flyer"
    qr_uri = generate_qr_code(lead_url)

    result = {
        "adres": adres,
        "adres_kort": adres_kort,
        "render_path": render_uri,
        "aerial_path": aerial_uri,
        "qr_path": qr_uri,
        "landing_url": lead_url,
        "builder_naam": builder_naam,
        "builder_telefoon": builder_telefoon,
        "lead_idx": idx,
    }
    if extra_vars:
        result.update(extra_vars)
    # Auto-bereken lichte tint van accent kleur (voor arg-icon achtergrond)
    if result.get("accent_color"):
        result.setdefault("accent_color_light", _lighten_hex(result["accent_color"], 0.85))
    return result


# ─── PDF GENERATIE ──────────────────────────────────────────────────────────

async def generate_flyers(df: pd.DataFrame, output_dir: Path,
                           formats: list, builder_naam: str,
                           builder_telefoon: str, landing_base_url: str,
                           renders_dir: Path, progress_callback=None,
                           extra_vars: dict = None,
                           flyer_style: str = "premium"):
    """
    flyer_style:
        "premium"  — warm taupe, default
        "design"   — brutalist editorial (donker, asymmetrisch)
        "klassiek" — atelier bourgeois (ivoor + bordeaux, gecentreerd)
        "auto"     — kies per lead op basis van huistype + lead_klasse + bouwjaar
    """
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(df)
    success = 0
    errors = 0

    print(f"\n📄 FacadePilot Flyer Generator — {total} leads")
    print(f"   Formaten: {', '.join(formats)}")
    print(f"   Output: {output_dir}/")
    print()

    t_start = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        for i, (idx, row) in enumerate(df.iterrows()):
            adres = str(row.get("adres", f"rij_{i}"))
            safe_name = output_stem(row, i)

            try:
                print(f"   [{i+1}/{total}] {adres[:50]}...", end="", flush=True)
                if progress_callback:
                    progress_callback(i, total, f"[{i+1}/{total}] 📄 {adres[:40]}...")

                variables = prepare_lead_variables(
                    row, i, builder_naam, builder_telefoon,
                    landing_base_url, renders_dir, extra_vars=extra_vars,
                )

                if not variables["render_path"]:
                    print(f" ⏭️ geen render")
                    continue

                t0 = time.time()

                # Bepaal stijl voor deze rij (auto vs vast)
                row_style = (
                    select_style_for_row(row)
                    if (flyer_style or "premium").lower() == "auto"
                    else flyer_style
                )

                for fmt in formats:
                    tpl = load_template(fmt, style=row_style)
                    html = tpl.render(**variables)
                    style_suffix = "" if row_style == "premium" else f"_{row_style}"
                    pdf_path = output_dir / f"{safe_name}_flyer_{fmt.upper()}{style_suffix}.pdf"
                    page = await browser.new_page()
                    await page.set_content(html, wait_until="networkidle")
                    await page.wait_for_timeout(1000)
                    await page.pdf(
                        path=str(pdf_path),
                        format=fmt.upper(),
                        print_background=True,
                        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    )
                    await page.close()

                elapsed = time.time() - t0
                print(f" ✅ ({elapsed:.1f}s)")
                success += 1

                if progress_callback:
                    progress_callback(i + 1, total, f"[{i+1}/{total}] ✅ {adres[:40]}...")

            except Exception as e:
                print(f" ❌ {e}")
                errors += 1

        await browser.close()

    elapsed_total = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  ✅ {success} flyers, {errors} fouten")
    print(f"  ⏱️  {elapsed_total:.0f}s totaal")
    print(f"  📁 {output_dir}/")
    print(f"{'='*60}\n")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Flyer Generator")
    parser.add_argument("--input", required=True, type=Path, help="Input CSV")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--format", choices=["a4", "a5", "both"], default="a4")
    parser.add_argument("--single", type=int, default=None)
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--builder-naam", default=DEFAULT_BUILDER)
    parser.add_argument("--builder-telefoon", default=DEFAULT_TELEFOON)
    parser.add_argument("--landing-url", default=DEFAULT_LANDING_URL)
    parser.add_argument("--renders-dir", type=Path, default=None)
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"❌ Niet gevonden: {args.input}")

    df = pd.read_csv(args.input, encoding="utf-8-sig")
    if args.single is not None:
        df = df.iloc[[args.single]].copy()
    if args.top:
        df = df.head(args.top).copy()

    formats = ["a4", "a5"] if args.format == "both" else [args.format]
    output_dir = args.output_dir or HERE / "flyers"
    renders_dir = args.renders_dir or HERE / "renders"

    asyncio.run(generate_flyers(
        df, output_dir, formats,
        builder_naam=args.builder_naam,
        builder_telefoon=args.builder_telefoon,
        landing_base_url=args.landing_url,
        renders_dir=renders_dir,
    ))


if __name__ == "__main__":
    main()
