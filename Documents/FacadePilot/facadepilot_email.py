#!/usr/bin/env python3
"""
FacadePilot E-mail Flyer Generator
====================================
Genereert per lead een mail-veilige HTML-flyer (table-based, inline styles).

Werkt op alle gangbare e-mailclients (Gmail, Outlook, Apple Mail).
Afbeeldingen worden geëmbed als CID (multipart/related) of als data: URI
afhankelijk van de gebruikte verzendmethode.

Output: emails/{niscode}/{slug}.html  (te gebruiken in mail-templates)
        emails/{niscode}/{slug}.eml   (kant-en-klaar mailbestand)

Gebruik:
    from facadepilot_email import generate_emails
    generate_emails(df, niscode="24107", output_dir=...,
                    builder_naam="...", landing_base_url="https://facadepilot.be")
"""

import argparse
import base64
import re
import sys
from email.message import EmailMessage
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent.resolve()


# ─── HELPERS ───────────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", str(s)).strip("-")
    return s or "lead"


def _image_to_data_uri(path: Path) -> str:
    if not path or not Path(path).exists():
        return ""
    suffix = Path(path).suffix.lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png"}.get(suffix.lstrip("."), "image/jpeg")
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ─── HTML TEMPLATE (mail-safe, table-based, inline styles) ────────────────

EMAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f1f5f9">
  <tr>
    <td align="center" style="padding:24px 12px">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 4px 16px rgba(15,23,42,0.08)">

        <!-- Header met accent kleur -->
        <tr>
          <td style="background:{accent};padding:22px 28px;color:#ffffff">
            <div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.85;margin-bottom:6px">{builder_naam}</div>
            <div style="font-size:22px;font-weight:700;line-height:1.25">Uw gevel kan er <span style="text-decoration:underline">zo</span> uitzien</div>
          </td>
        </tr>

        <!-- Persoonlijke aanhef -->
        <tr>
          <td style="padding:24px 28px 8px 28px;font-size:15px;line-height:1.6;color:#334155">
            Beste bewoner van <strong style="color:#0f172a">{adres}</strong>,<br><br>
            We hebben een persoonlijk renovatievoorstel gemaakt voor uw woning. Hieronder ziet u uw huidige gevel naast een fotorealistische impressie van het resultaat na renovatie.
          </td>
        </tr>

        <!-- Before/After zij-aan-zij (twee kolommen) -->
        <tr>
          <td style="padding:14px 28px">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td width="49%" valign="top" style="padding-right:6px">
                  <div style="background:#0f172a;color:#fff;font-size:10px;font-weight:600;padding:4px 8px;border-radius:6px 6px 0 0;text-transform:uppercase;letter-spacing:0.5px">Nu</div>
                  <img src="{before_img}" alt="Huidige gevel" width="100%" style="display:block;width:100%;height:auto;border:0;border-radius:0 0 8px 8px">
                </td>
                <td width="49%" valign="top" style="padding-left:6px">
                  <div style="background:{accent};color:#fff;font-size:10px;font-weight:600;padding:4px 8px;border-radius:6px 6px 0 0;text-transform:uppercase;letter-spacing:0.5px">Na renovatie</div>
                  <img src="{after_img}" alt="Renovatie-voorstel" width="100%" style="display:block;width:100%;height:auto;border:0;border-radius:0 0 8px 8px">
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Facts -->
        <tr>
          <td style="padding:14px 28px">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f8fafc;border-radius:10px">
              <tr>
                <td width="33%" align="center" style="padding:14px 6px">
                  <div style="font-size:18px;font-weight:700;color:{accent}">{afmeting_num}</div>
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px">{afmeting_label}</div>
                </td>
                <td width="33%" align="center" style="padding:14px 6px;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0">
                  <div style="font-size:18px;font-weight:700;color:{accent}">{prijs_num}</div>
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px">Indicatieprijs</div>
                </td>
                <td width="33%" align="center" style="padding:14px 6px">
                  <div style="font-size:18px;font-weight:700;color:{accent}">{bouwtijd_num}</div>
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px">Bouwtijd</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td style="padding:18px 28px 22px 28px" align="center">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="background:{accent};border-radius:10px">
                  <a href="{landing_url}" style="display:inline-block;padding:14px 28px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;font-family:inherit">
                    Bekijk uw voorstel & vraag offerte →
                  </a>
                </td>
              </tr>
            </table>
            <div style="font-size:12px;color:#64748b;margin-top:10px">Volledig vrijblijvend</div>
          </td>
        </tr>

        <!-- Korte uitleg -->
        <tr>
          <td style="padding:0 28px 22px 28px;font-size:13px;color:#64748b;line-height:1.6">
            <strong style="color:#0f172a">Hoe werkt het?</strong><br>
            U klikt op de link, bekijkt het voorstel met before/after-slider, en vult uw contactgegevens in als u interesse heeft. Wij bellen u binnen 1 werkdag op voor een gratis plaatsbezoek en een exacte offerte.
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:18px 28px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;line-height:1.6">
            <strong style="color:#0f172a">{builder_naam}</strong><br>
            Tel: <a href="tel:{builder_tel_clean}" style="color:{accent};text-decoration:none">{builder_tel}</a>{builder_email_html}
            <div style="margin-top:10px;font-size:11px;color:#94a3b8">
              Render gegenereerd met AI op basis van een Google Street View foto. Indicatieprijzen zijn richtprijzen — exacte offerte volgt na plaatsbezoek.<br>
              Geen interesse? <a href="mailto:{builder_email}?subject=Geen%20interesse" style="color:#94a3b8">Mail ons</a> en we halen u uit onze lijst.
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


# ─── GENERATOR ─────────────────────────────────────────────────────────────

def _strip_unit_html(s: str) -> tuple:
    if not s:
        return ("", "")
    m = re.match(r'(\d[\d\.,]*)<span[^>]*>([^<]+)</span>', s)
    if m:
        return (m.group(1), m.group(2))
    return (s, "")


def generate_emails(df: pd.DataFrame,
                    niscode: str,
                    output_dir: Path,
                    renders_dir: Path,
                    builder_naam: str = "Uw Gevelrenoveerder",
                    builder_telefoon: str = "0800 00 000",
                    builder_email: str = "info@example.com",
                    accent_color: str = "#3b5998",
                    landing_base_url: str = "https://facadepilot.be",
                    facade_preset: dict = None,
                    progress_callback=None,
                    write_eml: bool = True) -> list:
    """
    Genereer per lead een HTML-mail (en optioneel een .eml bestand klaar voor verzending).

    Returns: list van dicts met capakey, html_path, eml_path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    preset = facade_preset or {
        "afmeting": "100m²", "afmeting_label": "Geveloppervlak",
        "prijs": "vanaf €20K", "bouwtijd": "3–6wk",
    }
    afmeting_num, _ = _strip_unit_html(preset.get("afmeting", "100m²"))
    afmeting_label = preset.get("afmeting_label", "Geveloppervlak")
    prijs_num, _ = _strip_unit_html(preset.get("prijs", "vanaf €20K"))
    bouwtijd_num, _ = _strip_unit_html(preset.get("bouwtijd", "3–6wk"))

    builder_tel_clean = "".join(c for c in builder_telefoon if c.isdigit() or c == "+")
    builder_email_html = (f"<br>E-mail: <a href='mailto:{builder_email}' style='color:{accent_color};text-decoration:none'>{builder_email}</a>"
                          if builder_email else "")

    results = []
    total = len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        capakey = str(row.get("CAPAKEY", "") or row.get("capakey", "")).strip()
        if not capakey:
            continue

        adres = str(row.get("adres", "uw woning"))
        safe_name = f"{i:03d}_{adres[:35].replace(' ', '_').replace(',', '').replace('/', '_')}"
        render_path = renders_dir / f"{safe_name}_render.jpg"
        sv_path = renders_dir / f"{safe_name}_streetview.jpg"

        if not render_path.exists():
            if progress_callback:
                progress_callback(i + 1, total, f"[{i+1}/{total}] ⏭️ {adres[:40]} (geen render)")
            continue

        # Voor mail: data URIs werken in de meeste clients (behalve oudere Outlook).
        # Voor productie zou je naar een CID-attachement of CDN-hosted image moeten.
        before_uri = _image_to_data_uri(sv_path) if sv_path.exists() else ""
        after_uri = _image_to_data_uri(render_path)

        landing_url = f"{landing_base_url.rstrip('/')}/r/{niscode}-{i:03d}"
        subject = f"Uw gevel renoveren — persoonlijk voorstel voor {adres}"

        html = EMAIL_TEMPLATE.format(
            subject=subject,
            adres=adres.replace('"', '&quot;'),
            accent=accent_color,
            before_img=before_uri or after_uri,
            after_img=after_uri,
            afmeting_num=afmeting_num,
            afmeting_label=afmeting_label,
            prijs_num=prijs_num,
            bouwtijd_num=bouwtijd_num,
            landing_url=landing_url,
            builder_naam=builder_naam.replace('"', '&quot;'),
            builder_tel=builder_telefoon,
            builder_tel_clean=builder_tel_clean,
            builder_email=builder_email,
            builder_email_html=builder_email_html,
        )

        slug = _slugify(capakey)
        html_path = output_dir / f"{slug}.html"
        html_path.write_text(html, encoding="utf-8")

        eml_path = None
        if write_eml:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"{builder_naam} <{builder_email or 'noreply@example.com'}>"
            msg["To"] = "{{ recipient_email }}"  # Mail-merge placeholder
            # Plain text fallback
            msg.set_content(
                f"Beste bewoner van {adres},\n\n"
                f"We hebben een persoonlijk renovatievoorstel gemaakt voor uw woning.\n"
                f"Bekijk het voorstel hier: {landing_url}\n\n"
                f"Met vriendelijke groet,\n{builder_naam}\n{builder_telefoon}"
            )
            msg.add_alternative(html, subtype="html")
            eml_path = output_dir / f"{slug}.eml"
            eml_path.write_bytes(bytes(msg))

        results.append({
            "capakey": capakey,
            "html_path": str(html_path),
            "eml_path": str(eml_path) if eml_path else None,
            "subject": subject,
            "landing_url": landing_url,
        })

        if progress_callback:
            progress_callback(i + 1, total, f"[{i+1}/{total}] ✅ {adres[:40]}")

    return results


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FacadePilot E-mail Flyer Generator")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--niscode", required=True)
    parser.add_argument("--renders-dir", type=Path, default=HERE / "renders")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--builder", default="Uw Gevelrenoveerder")
    parser.add_argument("--tel", default="0800 00 000")
    parser.add_argument("--email", default="")
    parser.add_argument("--accent", default="#3b5998")
    parser.add_argument("--landing-base-url", default="https://facadepilot.be")
    parser.add_argument("--no-eml", action="store_true", help="Sla geen .eml bestanden op")
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"Niet gevonden: {args.csv}")

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    output_dir = args.output_dir or (HERE / "emails" / args.niscode)

    results = generate_emails(
        df, args.niscode, output_dir, args.renders_dir,
        builder_naam=args.builder,
        builder_telefoon=args.tel,
        builder_email=args.email,
        accent_color=args.accent,
        landing_base_url=args.landing_base_url,
        write_eml=not args.no_eml,
    )

    print(f"\n✅ {len(results)} e-mails gegenereerd in {output_dir}/")
    for r in results[:3]:
        print(f"  {Path(r['html_path']).name} -> {r['subject'][:60]}")


if __name__ == "__main__":
    main()
