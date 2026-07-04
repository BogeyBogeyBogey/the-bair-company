#!/usr/bin/env python3
"""
FacadePilot Landing Page Generator
====================================
Genereert per lead een statische HTML-landingpagina met:
  - Before/after slider (Street View origineel + AI render)
  - Persoonlijke aanhef ("Beste bewoner van [adres]")
  - Renovatie-info (preset label, indicatieprijs, bouwtijd)
  - Offerte-aanvraagformulier
  - Tracking via Supabase: scan-event + form_submit-event

Output: landing/{niscode}/{capakey-safe}.html
URL-pad: facadepilot.be/r/{niscode}-{capakey} (te uploaden naar Vercel/CDN)

Gebruik (als module):
    from facadepilot_landing import generate_landing_pages
    paths = generate_landing_pages(scored_df_with_renders, niscode="24107", ...)

Of CLI:
    python3 facadepilot_landing.py --csv leads_with_renders.csv --niscode 24107 \\
        --base-url https://facadepilot.be --builder "Bair Renovaties" --tel "0470..."
"""

import argparse
import base64
import html
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from facadepilot_keys import (
    first_existing,
    legacy_index_stem,
    legacy_streetview_candidates,
    output_stem,
    slugify,
    streetview_path as stable_streetview_path,
)

HERE = Path(__file__).parent.resolve()
load_dotenv(HERE / ".env")

DEFAULT_BASE_URL = "https://facadepilot.be"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
FORM_SUBMITS_TABLE = os.environ.get("FACADEPILOT_FORM_SUBMITS_TABLE", "form_submits")
PRIVACY_URL = os.environ.get("FACADEPILOT_PRIVACY_URL", "/privacybeleid.html")


# ─── HELPERS ───────────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    """capakey-safe slug voor filename / URL-pad."""
    return slugify(s)


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _find_render_path(row: pd.Series, index: int, renders_dir: Path) -> Path | None:
    explicit = str(row.get("render_path", "") or "").strip()
    if explicit and Path(explicit).exists():
        return Path(explicit)
    stable_glob = sorted(Path(renders_dir).glob(f"{output_stem(row, index)}_*_render.jpg"))
    legacy_glob = sorted(Path(renders_dir).glob(f"{legacy_index_stem(row, index)}*_render.jpg"))
    return first_existing([*stable_glob, *legacy_glob])


def _find_streetview_path(row: pd.Series, index: int, renders_dir: Path) -> Path | None:
    explicit = str(row.get("streetview_path", "") or "").strip()
    if explicit and Path(explicit).exists():
        return Path(explicit)
    return first_existing([
        stable_streetview_path(renders_dir, row, index),
        *legacy_streetview_candidates(renders_dir, row, index),
    ])


def _image_to_data_uri(path: Path) -> str:
    """Embed afbeelding als data: URI zodat de landingpagina volledig
    self-contained is (geen externe dependencies, geen broken links)."""
    if not path or not Path(path).exists():
        return ""
    suffix = Path(path).suffix.lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp"}.get(suffix.lstrip("."), "image/jpeg")
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ─── HTML TEMPLATE ────────────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Uw gevelrenovatie — {adres}</title>
<meta name="description" content="Persoonlijk renovatievoorstel voor {adres}. Zie hoe uw gevel eruit kan zien.">
<meta name="robots" content="noindex,nofollow">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:linear-gradient(180deg,#f8fafc,#eef2f7);color:#0f172a;min-height:100vh;line-height:1.55}}
.container{{max-width:760px;margin:0 auto;padding:24px 18px 60px}}
header{{text-align:center;margin-bottom:32px}}
.brand{{display:inline-block;font-size:13px;font-weight:600;color:{accent};letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}}
h1{{font-size:30px;font-weight:700;letter-spacing:-0.5px;line-height:1.2;margin-bottom:10px}}
h1 b{{color:{accent}}}
.subtitle{{font-size:15px;color:#475569;max-width:560px;margin:0 auto}}

.slider-wrap{{position:relative;margin:28px 0 24px;border-radius:14px;overflow:hidden;box-shadow:0 8px 28px rgba(15,23,42,0.18);aspect-ratio:3/2;background:#0f172a}}
.slider-img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;user-select:none;-webkit-user-drag:none}}
.slider-img.after{{clip-path:inset(0 0 0 50%)}}
.slider-handle{{position:absolute;top:0;bottom:0;left:50%;width:3px;background:#fff;cursor:ew-resize;box-shadow:0 0 12px rgba(0,0,0,0.5);transform:translateX(-50%)}}
.slider-handle::after{{content:"";position:absolute;top:50%;left:50%;width:42px;height:42px;background:#fff;border-radius:50%;transform:translate(-50%,-50%);box-shadow:0 4px 14px rgba(0,0,0,0.3);background-image:url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="%23{accent_hex}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 3 12 9 6"/><polyline points="15 18 21 12 15 6"/></svg>');background-position:center;background-repeat:no-repeat}}
.slider-label{{position:absolute;top:12px;background:rgba(15,23,42,0.85);color:#fff;font-size:11px;font-weight:600;padding:5px 10px;border-radius:14px;letter-spacing:0.5px;text-transform:uppercase}}
.slider-label.now{{left:14px}}
.slider-label.future{{right:14px;background:{accent}}}

.facts{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:26px 0}}
.fact{{background:#fff;border-radius:12px;padding:14px;text-align:center;box-shadow:0 2px 8px rgba(15,23,42,0.06)}}
.fact-num{{font-size:20px;font-weight:700;color:{accent}}}
.fact-label{{font-size:11px;color:#64748b;margin-top:3px;text-transform:uppercase;letter-spacing:0.5px}}

.cta-card{{background:#fff;border-radius:16px;padding:26px 22px;box-shadow:0 6px 22px rgba(15,23,42,0.10);margin:32px 0}}
.cta-card h2{{font-size:19px;font-weight:700;margin-bottom:16px}}
.form-row{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}}
@media(max-width:520px){{.form-row{{grid-template-columns:1fr}}}}
.field input,.field select,.field textarea{{width:100%;padding:11px 13px;border:1px solid #e2e8f0;border-radius:9px;font-size:14px;font-family:inherit;background:#fff}}
.field input:focus,.field select:focus,.field textarea:focus{{outline:none;border-color:{accent};box-shadow:0 0 0 3px {accent}25}}
.field label{{display:block;font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600}}
.field{{margin-bottom:10px}}
.consent{{display:flex;gap:8px;align-items:flex-start;font-size:12px;color:#64748b;margin:10px 0 4px}}
.consent input{{margin-top:2px}}
.btn{{width:100%;padding:14px;background:{accent};color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;margin-top:10px;transition:transform .15s,box-shadow .15s}}
.btn:hover{{transform:translateY(-1px);box-shadow:0 6px 20px {accent}55}}
.btn:disabled{{opacity:.5;cursor:not-allowed;transform:none}}
.success{{display:none;text-align:center;padding:24px;background:#dcfce7;border-radius:10px;color:#166534;font-weight:600}}
.success.show{{display:block}}
.error{{display:none;margin-top:12px;padding:14px;background:#fee2e2;border-radius:10px;color:#991b1b;font-size:13px;font-weight:600}}
.error.show{{display:block}}

.footer{{text-align:center;font-size:12px;color:#64748b;margin-top:36px;line-height:1.7}}
.footer b{{color:#0f172a}}
.footer a{{color:{accent};text-decoration:none}}
.privacy{{font-size:11px;color:#94a3b8;margin-top:14px}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">{builder_naam}</div>
    <h1>Uw gevel kan er <b>zo</b> uitzien</h1>
    <div class="subtitle">Persoonlijk renovatievoorstel voor <b>{adres}</b>. Sleep de lijn om het verschil te zien.</div>
  </header>

  <div class="slider-wrap" id="sliderWrap">
    <img src="{before_img}" class="slider-img before" alt="Huidige gevel">
    <img src="{after_img}" class="slider-img after" id="afterImg" alt="Renovatie-voorstel">
    <div class="slider-handle" id="sliderHandle"></div>
    <div class="slider-label now">Nu</div>
    <div class="slider-label future">Na renovatie</div>
  </div>

  <div class="facts">
    <div class="fact">
      <div class="fact-num">{afmeting_num}</div>
      <div class="fact-label">{afmeting_label}</div>
    </div>
    <div class="fact">
      <div class="fact-num">{prijs_num}</div>
      <div class="fact-label">Indicatieprijs</div>
    </div>
    <div class="fact">
      <div class="fact-num">{bouwtijd_num}</div>
      <div class="fact-label">Bouwtijd</div>
    </div>
  </div>

  <div class="cta-card">
    <h2>Vrijblijvende offerte op maat</h2>
    <form id="offerteForm">
      <div class="form-row">
        <div class="field">
          <label>Naam</label>
          <input type="text" name="naam" required>
        </div>
        <div class="field">
          <label>Telefoon</label>
          <input type="tel" name="telefoon" required>
        </div>
      </div>
      <div class="field">
        <label>E-mail</label>
        <input type="email" name="email" required>
      </div>
      <div class="field">
        <label>Vraag of opmerking <span style="color:#94a3b8;text-transform:none;font-weight:400">(optioneel)</span></label>
        <textarea name="opmerking" rows="3" placeholder="Bv. wanneer wilt u starten? Welke afwerking ziet u zitten?"></textarea>
      </div>
      <label class="consent">
        <input type="checkbox" name="consent" value="ja" required>
        <span>Ik ga akkoord dat {builder_naam} mij contacteert over deze gevelcheck. Zie <a href="{privacy_url}" target="_blank" rel="noopener">privacybeleid</a>.</span>
      </label>
      <button type="submit" class="btn" id="submitBtn">Vraag mijn vrijblijvende offerte</button>
    </form>
    <div class="success" id="successMsg">
      ✓ Bedankt! We bellen u binnen 1 werkdag op<br>
      <span style="font-weight:400;font-size:13px;color:#15803d">{builder_naam} • {builder_tel}</span>
    </div>
    <div class="error" id="errorMsg">
      Er ging iets mis bij het versturen. Bel ons rechtstreeks op <a href="tel:{builder_tel_clean}">{builder_tel}</a>.
    </div>
  </div>

  <div class="footer">
    <b>{builder_naam}</b><br>
    Tel: <a href="tel:{builder_tel_clean}" onclick="logEvent('call_click','src=' + FORM_SOURCE)">{builder_tel}</a>{builder_email_html}
    <div class="privacy">
      Render gegenereerd met AI op basis van een Google Street View foto. <br>
      Indicatieprijzen zijn richtprijzen — exacte offerte volgt na plaatsbezoek.<br>
      Geen interesse? <a href="mailto:{builder_email}?subject=Geen%20interesse%20in%20gevelrenovatie">Stuur een mail</a> en we nemen u uit onze lijst.
    </div>
  </div>
</div>

<script>
// Embedded lead context (voor analytics)
const LEAD = {{
  capakey: "{capakey}",
  niscode: "{niscode}",
  klasse: "{klasse}"
}};
const SB_URL = "{supabase_url}";
const SB_KEY = "{supabase_anon_key}";
const FORM_TABLE = "{form_submits_table}";
const FORM_SOURCE = new URLSearchParams(window.location.search).get('src') || "{source}";

// ─── BEFORE/AFTER SLIDER ─────────────────────────────────────────────
(function() {{
  const wrap = document.getElementById('sliderWrap');
  const handle = document.getElementById('sliderHandle');
  const after = document.getElementById('afterImg');
  let dragging = false;
  function setPct(pct) {{
    pct = Math.max(2, Math.min(98, pct));
    handle.style.left = pct + '%';
    after.style.clipPath = 'inset(0 0 0 ' + pct + '%)';
  }}
  function onMove(clientX) {{
    const rect = wrap.getBoundingClientRect();
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setPct(pct);
  }}
  handle.addEventListener('mousedown', e => {{ dragging = true; e.preventDefault(); }});
  document.addEventListener('mouseup', () => dragging = false);
  document.addEventListener('mousemove', e => {{ if (dragging) onMove(e.clientX); }});
  // Touch
  handle.addEventListener('touchstart', e => {{ dragging = true; }}, {{passive:true}});
  document.addEventListener('touchend', () => dragging = false);
  document.addEventListener('touchmove', e => {{ if (dragging && e.touches[0]) onMove(e.touches[0].clientX); }}, {{passive:true}});
  // Click op de wrap = sla daar de slider naartoe
  wrap.addEventListener('click', e => {{
    if (e.target === handle) return;
    onMove(e.clientX);
  }});
}})();

// ─── ANALYTICS via Supabase ──────────────────────────────────────────
async function logEvent(event, detail) {{
  if (!SB_URL || !SB_KEY) return;
  try {{
    await fetch(SB_URL + '/rest/v1/lead_events', {{
      method: 'POST',
      headers: {{
        'apikey': SB_KEY,
        'Authorization': 'Bearer ' + SB_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
      }},
      body: JSON.stringify({{
        capakey: LEAD.capakey,
        event: event,
        detail: detail || '',
        user_agent: navigator.userAgent.substring(0, 200)
      }})
    }});
  }} catch (e) {{ /* analytics mag conversie nooit blokkeren */ }}
}}

async function storeFormSubmit(data) {{
  if (!SB_URL || !SB_KEY || !FORM_TABLE) {{
    throw new Error('contact_backend_not_configured');
  }}
  const payload = {{
    capakey: LEAD.capakey,
    niscode: LEAD.niscode,
    source: FORM_SOURCE,
    naam: data.naam || '',
    telefoon: data.telefoon || '',
    email: data.email || '',
    opmerking: data.opmerking || '',
    consent: data.consent === 'ja',
    page_url: window.location.href,
    user_agent: navigator.userAgent.substring(0, 200)
  }};
  const response = await fetch(SB_URL + '/rest/v1/' + FORM_TABLE, {{
    method: 'POST',
    headers: {{
      'apikey': SB_KEY,
      'Authorization': 'Bearer ' + SB_KEY,
      'Content-Type': 'application/json',
      'Prefer': 'return=minimal'
    }},
    body: JSON.stringify(payload)
  }});
  if (!response.ok) {{
    throw new Error('contact_backend_failed_' + response.status);
  }}
}}

// Log scan = page load
logEvent('scan', 'klasse=' + LEAD.klasse + ';src=' + FORM_SOURCE);

// ─── FORM SUBMIT ─────────────────────────────────────────────────────
document.getElementById('offerteForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const btn = document.getElementById('submitBtn');
  const error = document.getElementById('errorMsg');
  error.classList.remove('show');
  btn.disabled = true;
  btn.textContent = 'Versturen...';
  const data = {{}};
  new FormData(e.target).forEach((v, k) => data[k] = v);
  try {{
    await storeFormSubmit(data);
    await logEvent('form_submit', 'stored=' + FORM_TABLE + ';src=' + FORM_SOURCE);
    e.target.style.display = 'none';
    document.getElementById('successMsg').classList.add('show');
  }} catch (err) {{
    await logEvent('form_submit_failed', String(err && err.message ? err.message : err).substring(0, 120));
    error.classList.add('show');
    btn.disabled = false;
    btn.textContent = 'Vraag mijn vrijblijvende offerte';
  }}
}});
</script>
</body>
</html>
"""


# ─── GENERATOR ─────────────────────────────────────────────────────────────

def _strip_unit_html(s: str) -> tuple:
    """Splits '100<span class="unit">m²</span>' → ('100', 'm²')."""
    if not s:
        return ("", "")
    import re
    m = re.match(r'(\d[\d\.,]*)<span[^>]*>([^<]+)</span>', s)
    if m:
        return (m.group(1), m.group(2))
    # fallback: alles tot eerste niet-cijfer
    digits = re.match(r'^([^<]+?)(\s*[a-zA-Z€]+)?$', s)
    if digits:
        return (digits.group(1).strip(), (digits.group(2) or "").strip())
    return (s, "")


def generate_landing_pages(df: pd.DataFrame,
                           niscode: str,
                           output_dir: Path,
                           renders_dir: Path,
                           builder_naam: str = "Uw Gevelrenoveerder",
                           builder_telefoon: str = "0800 00 000",
                           builder_email: str = "info@example.com",
                           accent_color: str = "#3b5998",
                           base_url: str = DEFAULT_BASE_URL,
                           facade_preset: dict = None,
                           progress_callback=None) -> list:
    """
    Genereer per lead een statische HTML-landingpagina.

    Returns: list van dicts met capakey, file_path, public_url
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Default preset-info (kan via FACADE_PRESETS overruled worden)
    preset_defaults = {
        "afmeting": "100m²",
        "afmeting_label": "Geveloppervlak",
        "prijs": "vanaf €20K",
        "bouwtijd": "3–6wk",
    }
    preset = facade_preset or preset_defaults

    afmeting_num, _ = _strip_unit_html(preset.get("afmeting", "100m²"))
    afmeting_label = preset.get("afmeting_label", "Geveloppervlak")
    prijs_num, _ = _strip_unit_html(preset.get("prijs", "vanaf €20K"))
    bouwtijd_num, _ = _strip_unit_html(preset.get("bouwtijd", "3–6wk"))

    accent_hex = accent_color.lstrip("#")
    builder_tel_clean = "".join(c for c in builder_telefoon if c.isdigit() or c == "+")

    safe_builder_email = _escape(builder_email)
    builder_email_html = (f"<br>E-mail: <a href='mailto:{safe_builder_email}'>{safe_builder_email}</a>"
                          if builder_email else "")

    results = []
    total = len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        capakey = str(row.get("CAPAKEY", "") or row.get("capakey", "")).strip()
        if not capakey:
            continue

        adres = str(row.get("adres", "uw woning"))
        klasse = str(row.get("lead_klasse", ""))
        # Vind de render + streetview foto
        render_path = _find_render_path(row, i, renders_dir)
        sv_path = _find_streetview_path(row, i, renders_dir)

        # Skip als geen render
        if not render_path:
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ⏭️ {adres[:40]} (geen render)")
            continue

        before_uri = _image_to_data_uri(sv_path) if sv_path and sv_path.exists() else ""
        after_uri = _image_to_data_uri(render_path)

        slug = _slugify(capakey)
        filename = f"{slug}.html"
        file_path = output_dir / filename

        html = TEMPLATE.format(
            adres=_escape(adres),
            capakey=_escape(capakey),
            niscode=_escape(niscode),
            klasse=_escape(klasse),
            accent=accent_color,
            accent_hex=accent_hex,
            before_img=before_uri or after_uri,  # fallback als geen sv
            after_img=after_uri,
            afmeting_num=_escape(afmeting_num),
            afmeting_label=_escape(afmeting_label),
            prijs_num=_escape(prijs_num),
            bouwtijd_num=_escape(bouwtijd_num),
            builder_naam=_escape(builder_naam),
            builder_tel=_escape(builder_telefoon),
            builder_tel_clean=builder_tel_clean,
            builder_email=_escape(builder_email),
            builder_email_html=builder_email_html,
            supabase_url=SUPABASE_URL,
            supabase_anon_key=SUPABASE_ANON_KEY,
            form_submits_table=FORM_SUBMITS_TABLE,
            privacy_url=_escape(PRIVACY_URL),
            source="qr",
        )

        file_path.write_text(html, encoding="utf-8")

        public_url = f"{base_url.rstrip('/')}/r/{niscode}-{slug}?src=qr"
        results.append({
            "capakey": capakey,
            "file_path": str(file_path),
            "public_url": public_url,
            "slug": slug,
            "filename": filename,
        })

        if progress_callback:
            progress_callback(i + 1, total, f"[{i+1}/{total}] ✅ {adres[:40]}")

    return results


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot Landing Page Generator")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--niscode", required=True, type=str)
    parser.add_argument("--renders-dir", type=Path, default=HERE / "renders")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--builder", default="Uw Gevelrenoveerder")
    parser.add_argument("--tel", default="0800 00 000")
    parser.add_argument("--email", default="")
    parser.add_argument("--accent", default="#3b5998")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"Niet gevonden: {args.csv}")

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    output_dir = args.output_dir or (HERE / "landing" / args.niscode)

    results = generate_landing_pages(
        df, args.niscode, output_dir, args.renders_dir,
        builder_naam=args.builder,
        builder_telefoon=args.tel,
        builder_email=args.email,
        accent_color=args.accent,
        base_url=args.base_url,
    )

    print(f"\n✅ {len(results)} landingpagina's gegenereerd in {output_dir}/")
    for r in results[:5]:
        print(f"  {r['filename']} -> {r['public_url']}")
    if len(results) > 5:
        print(f"  ... en {len(results) - 5} meer")


if __name__ == "__main__":
    main()
