#!/usr/bin/env python3
"""
FacadePilot Gevelrenovatie Render — Render Engine
=================================================
Genereert fotorealistische renovatie-renders van gevels
op basis van Google Street View foto's.

Workflow:
  1. Neem de gescoorde CSV als input
  2. Per lead: haal Street View foto op (of gebruik bestaande)
  3. Stuur foto + renovatie-prompt naar de ingestelde image-edit provider
  4. Sla de render op als before/after paar
  5. Voeg render-pad toe aan CSV

Vereist:
  - XAI_API_KEY in .env voor de standaard Render Engine-provider
  - OPENAI_API_KEY in .env alleen voor provider=openai
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

HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

# Cost tracker (module-level) — wordt door pipeline uitgelezen
_render_cost_state = {
    "renders_done": 0,
    "renders_skipped_quality": 0,
    "estimated_cost_usd": 0.0,
}
COST_PER_RENDER_USD = float(os.environ.get("FACADEPILOT_GROK_IMAGE_COST_USD", "0.22"))


def get_render_cost_state() -> dict:
    return dict(_render_cost_state)


def reset_render_cost_state():
    _render_cost_state.update({
        "renders_done": 0,
        "renders_skipped_quality": 0,
        "estimated_cost_usd": 0.0,
    })

# ─── FACADE PRESETS ─────────────────────────────────────────────────────────

# Consistentieregel die aan elk preset wordt toegevoegd
_RENOVATION_SCOPE_RULE = (
    "Belangrijk renovatiebereik: pas de gekozen gevelafwerking consequent toe op ALLE "
    "zichtbare buitenmuren die bij dezelfde woning horen: voorgevel, zijgevels, puntgevels, "
    "dakkapellen en schouwen. Als er een stenen omheining, lage muur of bakstenen pijler "
    "visueel en materieel bij de woning hoort, geef die dezelfde kleur/afwerking als de "
    "woning. Laat metalen hekwerk, poorten, straat, oprit en beplanting ongewijzigd. "
    "Behandel garagepoorten als buitenschrijnwerk: behoud hun exacte positie en vorm, maar "
    "geef ze dezelfde moderne, coherente kleur/afwerking als de voordeur en raamprofielen. "
)

# Strikte preservatie-instructie die aan elk preset wordt toegevoegd
_PRESERVE_RULE = (
    "STRIKT: behoud de EXACTE positie, grootte en aantal van alle ramen en deuren. "
    "Behoud ook exact het aantal, de positie en de grootte van garagepoorten. "
    "Verplaats NIETS. Verander alleen materiaal, kleur en afwerking van gevelvlakken "
    "en buitenschrijnwerk. De gevelindeling blijft 100% identiek. Verander NIET de "
    "dakvorm. Renoveer uitsluitend de aangeduide woning en de bijhorende zichtbare "
    "metselwerkdelen, NIET buurhuizen of losse bijgebouwen. Omgeving (straat, buren, "
    "beplanting, auto's) blijft volledig ongewijzigd. Voeg geen muren, lage tuinmuren, "
    "ramen, deuren, volumes, luifels, balkons, trappen, hekwerk, opritten of tuinindeling "
    "toe. Gebruik subtiele Belgische materiaal- en kleurtonen, geen plastic CGI-look, "
    "geen showroomlicht en geen willekeurige decoratieve vlakken. Fotorealistisch."
)

_WINDOW_SCOPE_RULE = (
    "Belangrijk renovatiebereik: verander uitsluitend het buitenschrijnwerk van de "
    "aangeduide woning: ramen, deuren, schuiframen, eventuele garagepoorten, screens "
    "en rolluiken waar logisch. Behoud gevelmateriaal, baksteen, crepi, dak, goten, "
    "straat, tuin, buren, oprit, auto's en beplanting volledig ongewijzigd. Maak het "
    "resultaat fotorealistisch als een afgewerkt geplaatst product, niet als vlakke "
    "kleurvlakken of conceptoverlay. Gebruik realistische profielen, glasreflecties, "
    "schaduw, dagkanten en plaatsingsdetails."
)

_WINDOW_PRESERVE_RULE = (
    "STRIKT: behoud de EXACTE positie, grootte, vorm en het aantal van alle ramen, "
    "deuren, schuiframen en garagepoorten. Verplaats NIETS en voeg geen extra ramen "
    "toe. Vervang alleen materiaal, kleur, profieltype en eventuele zonwering. "
    "Respecteer het perspectief en de bestaande lichtinval."
)

FACADE_PRESETS = {
    "moderne_crepi": {
        "label": "Moderne crépi-afwerking",
        "prompt": (
            "Renoveer ALLEEN de gevel van het centrale huis op de foto. Geef het een "
            "moderne uitstraling met een strakke witte crépi-afwerking. De bestaande "
            "ramen krijgen donkergrijze aluminium profielen, de bestaande voordeur "
            "en alle garagepoorten krijgen een moderne donkergrijze afwerking. "
            "Voeg subtiele buitenverlichting toe. "
            + _RENOVATION_SCOPE_RULE
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
            "afwerking en alle garagepoorten krijgen een bijpassende moderne afwerking. "
            "Voeg subtiele buitenverlichting toe. "
            + _RENOVATION_SCOPE_RULE
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
            "profielen. Alle garagepoorten krijgen een passende donkere moderne "
            "afwerking. Voeg designverlichting bij de voordeur toe. "
            + _RENOVATION_SCOPE_RULE
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
            "ingebouwde LED-verlichting. De bestaande ramen en garagepoorten krijgen "
            "minimale moderne donkere profielen/afwerking. "
            + _RENOVATION_SCOPE_RULE
            + _PRESERVE_RULE
        ),
        "afmeting": '150<span class="unit">m²</span>',
        "afmeting_label": "Totaalrenovatie",
        "prijs": 'vanaf <span class="unit">€50K</span>',
        "bouwtijd": '8–14<span class="unit">wk</span>',
    },
    "window_antraciet": {
        "label": "Antraciet ramen en deuren",
        "prompt": (
            "Vervang het bestaande buitenschrijnwerk door hoogwaardige antracietgrijze "
            "aluminium of PVC ramen en deuren met slanke moderne profielen. Geef ook "
            "zichtbare garagepoorten een coherente antraciet afwerking wanneer ze bij de "
            "woning horen. "
            + _WINDOW_SCOPE_RULE
            + _WINDOW_PRESERVE_RULE
        ),
        "afmeting": '18<span class="unit">m²</span>',
        "afmeting_label": "Raamoppervlak",
        "prijs": 'op <span class="unit">maat</span>',
        "bouwtijd": '2–4<span class="unit">wk</span>',
    },
    "window_wit": {
        "label": "Witte ramen en deuren",
        "prompt": (
            "Vervang het bestaande buitenschrijnwerk door frisse witte hoogwaardige ramen "
            "en deuren met nette realistische profielen, glasreflecties en afgewerkte "
            "dagkanten. Laat de woning herkenbaar en respecteer het bestaande karakter. "
            + _WINDOW_SCOPE_RULE
            + _WINDOW_PRESERVE_RULE
        ),
        "afmeting": '18<span class="unit">m²</span>',
        "afmeting_label": "Raamoppervlak",
        "prijs": 'op <span class="unit">maat</span>',
        "bouwtijd": '2–4<span class="unit">wk</span>',
    },
    "window_houtlook": {
        "label": "Houtlook of warme tint",
        "prompt": (
            "Vervang het bestaande buitenschrijnwerk door premium ramen en deuren in "
            "warme houtlook of zachte bronskleurige tint, met realistische textuur, "
            "glasreflecties en nette plaatsingsdetails. "
            + _WINDOW_SCOPE_RULE
            + _WINDOW_PRESERVE_RULE
        ),
        "afmeting": '18<span class="unit">m²</span>',
        "afmeting_label": "Raamoppervlak",
        "prijs": 'op <span class="unit">maat</span>',
        "bouwtijd": '2–4<span class="unit">wk</span>',
    },
    "window_screens": {
        "label": "Ramen met screens",
        "prompt": (
            "Vervang het buitenschrijnwerk door moderne ramen en deuren en voeg subtiele "
            "geïntegreerde screens toe bij grote of zongevoelige raamvlakken. Screens "
            "moeten als echte geplaatste zonwering ogen, met cassette/geleiders waar "
            "logisch en zonder de gevel te bedekken met platte vlakken. "
            + _WINDOW_SCOPE_RULE
            + _WINDOW_PRESERVE_RULE
        ),
        "afmeting": '18<span class="unit">m²</span>',
        "afmeting_label": "Ramen + screens",
        "prijs": 'op <span class="unit">maat</span>',
        "bouwtijd": '2–4<span class="unit">wk</span>',
    },
    "window_rolluiken": {
        "label": "Ramen met rolluiken",
        "prompt": (
            "Vervang het buitenschrijnwerk door nieuwe ramen en deuren en voeg discrete "
            "rolluiken toe waar dat logisch is. Rolluiken moeten realistisch geïntegreerd "
            "zijn, met passende kast/geleiders en schaduw, niet als egale kleurvlakken. "
            + _WINDOW_SCOPE_RULE
            + _WINDOW_PRESERVE_RULE
        ),
        "afmeting": '18<span class="unit">m²</span>',
        "afmeting_label": "Ramen + rolluiken",
        "prijs": 'op <span class="unit">maat</span>',
        "bouwtijd": '2–4<span class="unit">wk</span>',
    },
    "window_totaal": {
        "label": "Ramen deuren screens rolluiken",
        "prompt": (
            "Maak een complete buitenschrijnwerkrenovatie: nieuwe ramen, deuren, "
            "schuiframen, passende garagepoortafwerking en subtiele screens of rolluiken "
            "waar commercieel logisch. Kies een samenhangende hoogwaardige look die bij "
            "de woning past. "
            + _WINDOW_SCOPE_RULE
            + _WINDOW_PRESERVE_RULE
        ),
        "afmeting": '18<span class="unit">m²</span>',
        "afmeting_label": "Buitenschrijnwerk",
        "prijs": 'op <span class="unit">maat</span>',
        "bouwtijd": '2–4<span class="unit">wk</span>',
    },
}

DEFAULT_PRESET = "moderne_crepi"
DEFAULT_PROMPT = FACADE_PRESETS[DEFAULT_PRESET]["prompt"]

# Image-edit provider

# Gedeelde kostenbewaking (HomePilot). facadepilot_tracking bootstrapt sys.path.
try:
    import facadepilot_tracking  # noqa: F401  (sys.path bootstrap)
    from homepilot_shared.cost_guard import BudgetGuard, BudgetExceeded
except Exception:  # pragma: no cover
    BudgetGuard = None
    BudgetExceeded = RuntimeError

IMAGE_PROVIDER = os.environ.get("FACADEPILOT_IMAGE_PROVIDER", "xai").strip().lower()
XAI_IMAGE_MODEL = os.environ.get("FACADEPILOT_GROK_IMAGE_MODEL", "grok-imagine-image-quality")
OPENAI_IMAGE_MODEL = os.environ.get("FACADEPILOT_OPENAI_IMAGE_MODEL", "gpt-image-1.5")
IMAGE_MODEL = XAI_IMAGE_MODEL if IMAGE_PROVIDER in {"xai", "grok"} else OPENAI_IMAGE_MODEL
IMAGE_SIZE = "1536x1024"  # Landscape — past bij Street View formaat
RENDER_PROMPT_VERSION = "scope_v2"

REQUEST_DELAY = 1.0


# ─── STREET VIEW OPHALEN ───────────────────────────────────────────────────

def fetch_streetview_for_render(lat: float, lon: float, camera: dict | None = None) -> Image.Image:
    """Haal Street View foto op via de streetview module."""
    from facadepilot_streetview import fetch_streetview
    camera = camera or {}
    return fetch_streetview(
        lat,
        lon,
        heading=camera.get("heading"),
        pitch=int(camera.get("pitch", 5)),
        fov=int(camera.get("fov", 65)),
        strafe_m=float(camera.get("strafe_m", 0) or 0),
    )


def crop_to_target_box(img: Image.Image, target_box: dict | None) -> Image.Image:
    """Crop Street View to a manually selected normalized facade rectangle."""
    if not target_box:
        return img
    width, height = img.size
    x = max(0, min(width - 1, int(float(target_box.get("x", 0)) * width)))
    y = max(0, min(height - 1, int(float(target_box.get("y", 0)) * height)))
    w = max(1, int(float(target_box.get("w", 1)) * width))
    h = max(1, int(float(target_box.get("h", 1)) * height))
    right = max(x + 1, min(width, x + w))
    lower = max(y + 1, min(height, y + h))
    return img.crop((x, y, right, lower))


# ─── VOORFOTO ALS RENDER-INPUT (optioneel, achter env-vlag) ────────────────

def _maybe_use_voorfoto(row, streetview_img: Image.Image) -> Image.Image:
    """Gebruik een GOEDGEKEURDE voorfoto als render-input i.p.v. de ruwe foto.

    Alleen actief als FACADEPILOT_USE_VOORFOTO=1 (standaard UIT, tot Kristof
    de vlag omzet). Voorwaarden: de rij heeft een bestaand ``voorfoto_path``
    EN het item is goedgekeurd in de reviewpoort "voorfoto"
    (ReviewGate.is_approved op dezelfde key als facadepilot_voorfoto).
    In alle andere gevallen — of bij elke fout — ongewijzigd gedrag.
    """
    field_photo = str(row.get("field_photo_path", "") or "")
    if field_photo and field_photo.lower() != "nan":
        try:
            field_path = Path(field_photo)
            if field_path.exists():
                print("           → Eigen veldfoto als render-input")
                return Image.open(field_path).convert("RGB")
        except Exception as e:
            print(f"           ⚠ Veldfoto overgeslagen ({str(e)[:80]}) — "
                  f"Street View fallback")

    if os.environ.get("FACADEPILOT_USE_VOORFOTO") != "1":
        return streetview_img
    try:
        vf = str(row.get("voorfoto_path", "") or "")
        if not vf or vf.lower() == "nan" or not Path(vf).exists():
            return streetview_img
        from facadepilot_voorfoto import voorfoto_key
        from homepilot_shared.review_gate import ReviewGate
        gate = ReviewGate(pilot="facadepilot", project_dir=HERE,
                          gate="voorfoto")
        if not gate.is_approved(voorfoto_key(row)):
            return streetview_img
        print("           → Voorfoto (goedgekeurd) als render-input")
        return Image.open(vf).convert("RGB")
    except Exception as e:  # nooit de render blokkeren op de voorfoto-stap
        print(f"           ⚠ Voorfoto overgeslagen ({str(e)[:80]}) — "
              f"ruwe Street View gebruikt")
        return streetview_img


# ─── IMAGE EDIT RENDER ─────────────────────────────────────────────────────

def image_to_bytesio(img: Image.Image, fmt: str = "PNG") -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    buf.name = "streetview.png"
    return buf


def image_to_data_uri(img: Image.Image, max_side: int = 1536) -> str:
    render_img = img.convert("RGB").copy()
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    render_img.thumbnail((max_side, max_side), resample)
    buf = io.BytesIO()
    render_img.save(buf, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _xai_error_message(response: requests.Response) -> str:
    body = response.text[:600] if response.text else ""
    return f"xAI Images API {response.status_code}: {body}"


def _image_from_xai_payload(item: dict) -> Image.Image:
    b64_value = item.get("b64_json") or item.get("base64")
    if b64_value:
        out_bytes = base64.b64decode(b64_value)
        return Image.open(io.BytesIO(out_bytes)).convert("RGB")
    url = item.get("url")
    if url:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    raise ValueError("Geen afbeelding ontvangen van xAI")


def _render_facade_xai(streetview_img: Image.Image, prompt: str,
                       max_retries: int = 3) -> Image.Image:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("Render Engine API key ontbreekt. Voeg de provider-key toe aan .env om renders te maken.")

    endpoint = os.environ.get("FACADEPILOT_XAI_IMAGE_EDIT_URL", "https://api.x.ai/v1/images/edits")
    payload = {
        "model": XAI_IMAGE_MODEL,
        "prompt": prompt,
        "image": {
            "url": image_to_data_uri(streetview_img),
            "type": "image_url",
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_exc = None
    for attempt in range(max_retries):
        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=180)
            if response.status_code in {429} or response.status_code >= 500:
                if attempt < max_retries - 1:
                    backoff = 5 * (attempt + 1) if response.status_code == 429 else 2 ** (attempt + 1)
                    print(f"           ⚠ xAI API {response.status_code} (poging {attempt+1}/{max_retries}), "
                          f"retry over {backoff}s")
                    time.sleep(backoff)
                    continue
            if response.status_code >= 400:
                raise RuntimeError(_xai_error_message(response))
            data = response.json()
            items = data.get("data") or []
            if not items:
                raise ValueError("Geen data[] ontvangen van xAI")
            return _image_from_xai_payload(items[0])
        except requests.RequestException as e:
            last_exc = e
            if attempt < max_retries - 1:
                backoff = 2 ** (attempt + 1)
                print(f"           ⚠ xAI netwerk/timeout (poging {attempt+1}/{max_retries}), "
                      f"retry over {backoff}s: {str(e)[:80]}")
                time.sleep(backoff)
            else:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("xAI render_facade: max retries opgebruikt zonder fout")


def _render_facade_openai(streetview_img: Image.Image, prompt: str,
                          size: str = IMAGE_SIZE, max_retries: int = 3) -> Image.Image:
    """
    OpenAI image-edit provider.

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


def render_facade(streetview_img: Image.Image, prompt: str = DEFAULT_PROMPT,
                  size: str = IMAGE_SIZE, max_retries: int = 3) -> Image.Image:
    """
    Stuur een bronfoto naar de ingestelde image-edit provider.

    Stuur de bronfoto naar de geconfigureerde Render Engine-provider.
    """
    if IMAGE_PROVIDER in {"openai", "gpt", "gpt-image"}:
        return _render_facade_openai(streetview_img, prompt=prompt, size=size, max_retries=max_retries)
    return _render_facade_xai(streetview_img, prompt=prompt, max_retries=max_retries)


def submit_render_review(*, key: str, render_path, source_path, preset: str,
                         prompt_version: str = RENDER_PROMPT_VERSION,
                         address: str = "") -> None:
    """Zet een afgewerkte render in de reviewpoort "render" (HITL stap 3).

    Zelfde plek in de keten als de Fase A-kostenlog: direct na een geslaagde
    render. Defensief: een falende submit mag een render-run nooit breken.
    De wachtrij verschijnt in het Review-gedeelte van het dashboard.
    """
    try:
        import facadepilot_tracking  # noqa: F401  (sys.path bootstrap)
        from homepilot_shared.review_gate import ReviewGate
        gate = ReviewGate(pilot="facadepilot", project_dir=HERE, gate="render")
        gate.submit(key=str(key), payload={
            "render_path": str(render_path),
            "source_path": str(source_path),
            "preset": preset,
            "prompt_version": prompt_version,
            "address": address,
        })
    except Exception as exc:  # reviewpoort mag de render nooit blokkeren
        print(f"           ⚠ reviewpoort render: submit faalde ({str(exc)[:80]})")


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
        met de beeldcheck. Faalt de check → render wordt overgeslagen
        (bespaart ~$0.10 per slechte foto).
    multi_preset_for_klassen : list[str] of None
        Bij welke lead_klassen extra renders moeten gemaakt worden, bv.
        ["A+"] om alleen topkandidaten meerdere stijlen te tonen.
        None betekent: voor alle gerenderde woningen.
    multi_presets : list[str] of None
        Lijst van preset-keys (uit FACADE_PRESETS) die extra gerenderd
        moeten worden. Bv.
        ["moderne_crepi", "baksteen_rejoint", "totaalrenovatie"]
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        from facadepilot_lead_review import apply_review_filter
        before_review = len(df)
        df = apply_review_filter(df)
        if len(df) != before_review:
            print(f"  🗺️ Lead-review filter: {len(df)}/{before_review} leads naar render")
    except Exception as e:
        print(f"  ⚠ Lead-review filter overgeslagen: {e}")

    render_paths = []
    quality_results = []     # (pass: bool, reason: str)
    extra_render_paths = []  # dict met preset_key -> path voor multi-preset rijen

    total = len(df)
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
    print(f"   Quality check: {'AAN (beeldcheck)' if quality_check else 'UIT'}")
    print(f"   Auto-preset:   {'AAN (per lead)' if auto_preset else 'UIT (vaste preset)'}")
    if multi_presets:
        doelgroep = (
            f"voor klassen {multi_preset_for_klassen}"
            if multi_preset_for_klassen else
            "voor alle renderleads"
        )
        print(f"   Multi-preset: {multi_presets} {doelgroep}")
    print(f"   Output: {output_dir}/")
    print()

    auto_preset_results = []  # voor logging in CSV

    # ── Kostenbewaking vóór de run (raming + budgetstop) ───────────────
    if BudgetGuard is not None and total:
        _guard = BudgetGuard(pilot="facadepilot", project_dir=Path(__file__).parent)
        _geschat = _guard.check(total, model=IMAGE_MODEL, size=size)
        print(f"   💶 Geschatte kost (max): €{_geschat:.2f} voor {total} renders "
              f"(budget €{_guard.budget_eur:.0f})")
    else:
        _guard = None

    t_start = time.time()

    for i, (idx, row) in enumerate(df.iterrows()):
        adres = str(row.get("adres", f"rij_{i}"))
        capakey = str(row.get("CAPAKEY", "") or "")
        safe_name = f"{i:03d}_{adres[:35].replace(' ', '_').replace(',', '').replace('/', '_')}"
        try:
            from facadepilot_lead_review import camera_for
            camera = camera_for(capakey)
        except Exception:
            camera = {}

        # Bepaal welke preset_key we voor de hoofdrender gebruiken (voor filename)
        # — bij auto_preset wordt dit per rij overschreven verderop
        active_preset_key = preset_key

        # Skip alleen renders met dezelfde promptversie; oude renders mogen opnieuw.
        existing_render = output_dir / f"{safe_name}_{active_preset_key}_{RENDER_PROMPT_VERSION}_render.jpg"
        field_photo_for_cache = str(row.get("field_photo_path", "") or "")
        if existing_render.exists() and not camera and not multi_presets and not field_photo_for_cache:
            print(f"   [{i+1}/{total}] {adres[:50]}... ⏭️ al gerenderd ({existing_render.name})")
            submit_render_review(
                key=f"{safe_name}_{active_preset_key}",
                render_path=existing_render,
                source_path=output_dir / f"{safe_name}_streetview.jpg",
                preset=active_preset_key, address=adres)
            render_paths.append(str(existing_render))
            quality_results.append({"pass": True, "reason": "cached"})
            extra_render_paths.append({})
            success += 1
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ⏭️ {adres[:40]}... (al gerenderd)")
            continue

        try:
            # Stap 1: bronbeeld voorbereiden
            print(f"   [{i+1}/{total}] {adres[:50]}...")
            field_photo = str(row.get("field_photo_path", "") or "")
            field_path = Path(field_photo) if field_photo and field_photo.lower() != "nan" else None
            if progress_callback:
                source_label = "eigen veldfoto" if field_path and field_path.exists() else "Street View"
                progress_callback(i, total, f"[{i+1}/{total}] 📸 Bronbeeld ({source_label}): {adres[:40]}...")

            if field_path and field_path.exists():
                streetview = Image.open(field_path).convert("RGB")
                print("           → Eigen veldfoto gebruiken; Street View ophalen overgeslagen")
            else:
                streetview_full = fetch_streetview_for_render(row["lat"], row["lon"], camera=camera)
                streetview = crop_to_target_box(streetview_full, camera.get("target_box"))

                # Voorfoto-stap: alleen bij FACADEPILOT_USE_VOORFOTO=1 én een
                # goedgekeurde voorfoto wordt die de render-input (zie helper).
                streetview = _maybe_use_voorfoto(row, streetview)

            # Sla Street View foto op (before)
            sv_path = output_dir / f"{safe_name}_streetview.jpg"
            streetview.save(sv_path, "JPEG", quality=90)

            # Stap 1b: Pre-render kwaliteitscheck
            if quality_check and quality_checker is not None:
                print(f"           → Kwaliteitscheck...", end="", flush=True)
                if progress_callback:
                    progress_callback(i, total, f"[{i+1}/{total}] 🔍 Kwaliteitscheck: {adres[:40]}...")
                qc = quality_checker(streetview)
                if not qc["pass"]:
                    print(f" ❌ skip ({qc['type']}: {qc['reason']})")
                    render_paths.append("")
                    quality_results.append(qc)
                    extra_render_paths.append({})
                    skipped_quality += 1
                    _render_cost_state["renders_skipped_quality"] += 1
                    if progress_callback:
                        progress_callback(i + 1, total,
                            f"[{i+1}/{total}] ⏭️ {adres[:40]}... skip ({qc['type']})")
                    if i < total - 1:
                        time.sleep(REQUEST_DELAY)
                    continue
                print(f" ✅ ({qc['type']})")
                quality_results.append(qc)
            else:
                quality_results.append({"pass": True, "reason": "check uit"})

            # Stap 2: Hoofdrender (eventueel met auto-gekozen preset)
            row_prompt = prompt
            row_preset_key = None
            row_preset_reden = ""
            file_preset_key = preset_key  # voor filename
            if auto_preset and preset_selector is not None:
                row_preset_key, row_preset_reden = preset_selector(row)
                if row_preset_key in FACADE_PRESETS:
                    row_prompt = FACADE_PRESETS[row_preset_key]["prompt"]
                    file_preset_key = row_preset_key
                    print(f"           → Auto-preset: {row_preset_key} ({row_preset_reden})")

            if camera.get("target_box"):
                row_prompt += (
                    " De afbeelding is manueel bijgesneden tot de volledige geselecteerde gevelzone. "
                    "Behandel alle zichtbare aan elkaar grenzende woningen in deze uitsnede als één gezamenlijk gevelproject."
                )

            render_path = output_dir / f"{safe_name}_{file_preset_key}_{RENDER_PROMPT_VERSION}_render.jpg"
            if render_path.exists() and not camera:
                print(f"           → Hoofdrender: cache ({render_path.name})")
                elapsed = 0
            else:
                print(f"           → Render genereren...", end="", flush=True)
                if progress_callback:
                    progress_callback(i, total, f"[{i+1}/{total}] 🎨 Render genereren: {adres[:40]}...")

                t0 = time.time()
                render = render_facade(streetview, prompt=row_prompt, size=size)
                elapsed = time.time() - t0
                print(f" ✅ ({elapsed:.1f}s)")
                render.save(render_path, "JPEG", quality=95)
                if _guard is not None:
                    _guard.log(address=adres,
                               cost_eur=_guard.unit_cost(model=IMAGE_MODEL, size=size),
                               model=IMAGE_MODEL, size=size)
                _render_cost_state["renders_done"] += 1
                _render_cost_state["estimated_cost_usd"] += COST_PER_RENDER_USD
            auto_preset_results.append({"key": row_preset_key or "", "reden": row_preset_reden})

            # Reviewpoort "render" (HITL): zelfde hook-plek als de kostenlog.
            submit_render_review(
                key=f"{safe_name}_{file_preset_key}",
                render_path=render_path, source_path=sv_path,
                preset=file_preset_key, address=adres)

            # Schrijf met preset-specifieke naam zodat varianten naast elkaar kunnen
            render_paths.append(str(render_path))
            success += 1

            # Stap 3 (optioneel): extra renders voor vergelijking per afwerking
            extra_paths_for_row = {}
            klasse = str(row.get("lead_klasse", ""))
            if multi_presets and (not multi_preset_for_klassen or klasse in multi_preset_for_klassen):
                for variant_key in multi_presets:
                    if variant_key not in FACADE_PRESETS:
                        continue
                    variant_path = output_dir / f"{safe_name}_{variant_key}_{RENDER_PROMPT_VERSION}_render.jpg"
                    if variant_key == file_preset_key:
                        extra_paths_for_row[variant_key] = str(render_path)
                        continue
                    if variant_path.exists() and not camera:
                        extra_paths_for_row[variant_key] = str(variant_path)
                        continue
                    extra_prompt = FACADE_PRESETS[variant_key]["prompt"]
                    if camera.get("target_box"):
                        extra_prompt += (
                            " De afbeelding is manueel bijgesneden tot de volledige geselecteerde gevelzone. "
                            "Behandel alle zichtbare aan elkaar grenzende woningen in deze uitsnede als één gezamenlijk gevelproject."
                        )
                    print(f"           → Extra render ({variant_key})...", end="", flush=True)
                    try:
                        t0 = time.time()
                        extra_render = render_facade(streetview, prompt=extra_prompt, size=size)
                        extra_render.save(variant_path, "JPEG", quality=95)
                        if _guard is not None:
                            _guard.log(address=adres,
                                       cost_eur=_guard.unit_cost(model=IMAGE_MODEL, size=size),
                                       model=IMAGE_MODEL, size=size, note="variant")
                        extra_paths_for_row[variant_key] = str(variant_path)
                        _render_cost_state["renders_done"] += 1
                        _render_cost_state["estimated_cost_usd"] += COST_PER_RENDER_USD
                        submit_render_review(
                            key=f"{safe_name}_{variant_key}",
                            render_path=variant_path, source_path=sv_path,
                            preset=variant_key, address=adres)
                        print(f" ✅ ({time.time()-t0:.1f}s)")
                    except Exception as e:
                        print(f" ❌ {e}")
                    time.sleep(REQUEST_DELAY)
            extra_render_paths.append(extra_paths_for_row)

            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ✅ {adres[:40]}... ({elapsed:.0f}s)")

        except Exception as e:
            print(f"           → ❌ Fout: {e}")
            render_paths.append("")
            quality_results.append({"pass": False, "reason": f"fetch/render fout: {str(e)[:80]}"})
            extra_render_paths.append({})
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
    df["render_quality_pass"] = [q["pass"] for q in quality_results]
    df["render_quality_type"] = [q.get("type", "") for q in quality_results]
    df["render_quality_reason"] = [q.get("reason", "") for q in quality_results]
    if auto_preset and auto_preset_results:
        # Pad naar lengte van df
        while len(auto_preset_results) < len(df):
            auto_preset_results.append({"key": "", "reden": ""})
        df["preset_auto"] = [a["key"] for a in auto_preset_results[:len(df)]]
        df["preset_reden"] = [a["reden"] for a in auto_preset_results[:len(df)]]

    # Multi-preset paden als extra kolommen
    if multi_presets:
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
    provider = IMAGE_PROVIDER
    if provider in {"openai", "gpt", "gpt-image"}:
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("❌ OPENAI_API_KEY niet gevonden voor provider=openai")
    elif not os.environ.get("XAI_API_KEY"):
        sys.exit("❌ Render Engine API key niet gevonden")
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
