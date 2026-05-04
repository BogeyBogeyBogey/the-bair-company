#!/usr/bin/env python3
"""
FacadePilot Quality Check — Pre-render foto-validatie
=====================================================
Checkt met gpt-4o-mini vision of een Google Street View foto een
herkenbare voorgevel van een woning toont VOOR de dure GPT Image render.

Kosten:
  - gpt-4o-mini vision: ~$0.001 per check (low detail mode)
  - GPT Image 2 render: ~$0.10 per render
  → Eén bespaarde slechte render betaalt 100 checks.

Gebruik (vanuit render module):
    from facadepilot_quality_check import check_facade_quality
    result = check_facade_quality(streetview_image)
    if not result["pass"]:
        # skip render, log result["reason"]
"""

import base64
import io
import os
from pathlib import Path

from PIL import Image
from dotenv import load_dotenv

HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

# ─── CONFIG ─────────────────────────────────────────────────────────────────

QUALITY_MODEL = "gpt-4o-mini"
QUALITY_PROMPT = """Je bent een vastgoedfotograaf die beoordeelt of een Google Street View foto bruikbaar is voor een gevelrenovatie-mockup.

Bekijk de foto en bepaal of EEN herkenbare voorgevel van een Belgische rijwoning, halfopen of vrijstaande woning duidelijk in beeld is.

Antwoord STRIKT als JSON met deze velden:
{"pass": true/false, "type": "woning|garage|schuur|kantoor|leeg|onduidelijk|ander", "reason": "korte uitleg in 1 zin"}

Pass alleen als:
- Een gewone woongevel duidelijk centraal staat
- Geen forse obstructies (vrachtwagens vlak voor gevel, hekken, dichte begroeiing voor 80% van gevel)
- Geen bouwhekken of bouwwerf
- Geen industriegebouw, magazijn, garage of bijgebouw

Faal als:
- Geen woning zichtbaar
- Foto toont voornamelijk de straat, een bijgebouw, of een buurpand
- Gevel is grotendeels verborgen
- Het is duidelijk geen residentieel gebouw

Geef ALLEEN de JSON terug, niets anders."""

# Hard-fail types: alleen DEZE types blokkeren een render.
# "onduidelijk" en "ander" worden als pass behandeld (twijfelgeval = laat door).
# Filosofie: blokkeer alleen overduidelijke fouten, niet "ik weet het niet zeker".
HARD_FAIL_TYPES = {
    "garage",
    "schuur",
    "kantoor",
    "leeg",
    "industrie",
    "industrieel",
    "magazijn",
    "loods",
    "bouwwerf",
    "winkel",
}

# Cost tracker (module-level)
_cost_state = {
    "checks_done": 0,
    "checks_passed": 0,
    "checks_failed": 0,
    "estimated_cost_usd": 0.0,
}

# gpt-4o-mini vision (low detail) ~ $0.000150 per 1K tokens input + $0.0006 per 1K output
# Een check verbruikt ~150 input tokens + ~50 output tokens ≈ $0.00006
COST_PER_CHECK = 0.001  # conservatieve schatting incl. image tokens


def get_cost_state() -> dict:
    """Geef de huidige cost-stats terug."""
    return dict(_cost_state)


def reset_cost_state():
    """Reset de teller (per pipeline run)."""
    _cost_state.update({
        "checks_done": 0,
        "checks_passed": 0,
        "checks_failed": 0,
        "estimated_cost_usd": 0.0,
    })


# ─── IMAGE → BASE64 ────────────────────────────────────────────────────────

def _image_to_data_url(img: Image.Image, max_dim: int = 512) -> str:
    """Verklein + base64-encodeer afbeelding voor de vision API (low detail)."""
    img = img.copy()
    img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


# ─── KWALITEITSCHECK ───────────────────────────────────────────────────────

def check_facade_quality(streetview_img: Image.Image, timeout: int = 20) -> dict:
    """
    Check of een Street View foto bruikbaar is voor gevelrenovatie-render.

    Returns dict:
      {
        "pass": bool,
        "type": str,         # "woning" | "garage" | ...
        "reason": str,
        "raw": str,          # ruwe LLM output (debug)
        "cost_usd": float,
      }
    """
    import json
    from openai import OpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        # Geen key → fail-open: laat door, niet blokkeren
        return {
            "pass": True,
            "type": "skipped",
            "reason": "OPENAI_API_KEY ontbreekt — kwaliteitscheck overgeslagen",
            "raw": "",
            "cost_usd": 0.0,
        }

    data_url = _image_to_data_url(streetview_img)

    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model=QUALITY_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": QUALITY_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                    ],
                }
            ],
            temperature=0,
            max_tokens=120,
            timeout=timeout,
        )
        raw = response.choices[0].message.content.strip()

        # Strip eventuele markdown fences
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()

        parsed = json.loads(raw)
        ftype = str(parsed.get("type", "onduidelijk")).strip().lower()
        reason = str(parsed.get("reason", ""))[:200]
        # Override van model-verdict: alleen hard fail bij duidelijk
        # niet-residentiële types. "onduidelijk", "ander" en alles wat het
        # model niet expliciet als faaltype markeert wordt doorgelaten.
        if ftype in HARD_FAIL_TYPES:
            passed = False
            reason = f"hard fail ({ftype}): {reason}"
        else:
            passed = True
            if not bool(parsed.get("pass", False)):
                # Model zei nee, wij overrulen tot soft pass
                reason = f"soft pass ({ftype}): {reason}"

    except json.JSONDecodeError:
        # LLM gaf geen geldige JSON → fail-open (laat door)
        passed = True
        ftype = "unparseable"
        reason = f"JSON-parse mislukte (output: {raw[:80]})"
    except Exception as e:
        # API-fout → fail-open
        passed = True
        ftype = "api_error"
        reason = f"vision API-fout: {str(e)[:120]}"
        raw = ""

    # Cost-tracking
    _cost_state["checks_done"] += 1
    _cost_state["estimated_cost_usd"] += COST_PER_CHECK
    if passed:
        _cost_state["checks_passed"] += 1
    else:
        _cost_state["checks_failed"] += 1

    return {
        "pass": passed,
        "type": ftype,
        "reason": reason,
        "raw": raw if "raw" in dir() else "",
        "cost_usd": COST_PER_CHECK,
    }


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FacadePilot Quality Check")
    parser.add_argument("--image", required=True, type=Path, help="Pad naar JPG/PNG")
    args = parser.parse_args()

    if not args.image.exists():
        raise SystemExit(f"Niet gevonden: {args.image}")

    img = Image.open(args.image).convert("RGB")
    result = check_facade_quality(img)

    status = "✅ PASS" if result["pass"] else "❌ FAIL"
    print(f"{status} | type: {result['type']}")
    print(f"  reden: {result['reason']}")
    print(f"  kosten: ${result['cost_usd']:.4f}")
