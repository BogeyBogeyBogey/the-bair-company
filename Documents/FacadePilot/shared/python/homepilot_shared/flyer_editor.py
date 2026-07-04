"""Shared flyer editor for HomePilot pilot dashboards.

The editor is intentionally add-on only: it reads campaign outputs and writes
manual work to flyer_edits/. It never mutates generated flyers, renders, or
lead CSV files.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import html
import io
import json
import mimetypes
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_BASE_URL = "https://facadepilot.be"
DEFAULT_PROFILE = {
    "naam": "Uw gevelspecialist",
    "telefoon": "0800 00 000",
    "email": "",
    "website": "facadepilot.be",
    "accent_color": "#3b5998",
    "logo": "",
    "logo_path": "",
    "claims": [
        "Voorstel op basis van uw woningfoto",
        "Premies en techniek na plaatsbezoek te bevestigen",
        "Gratis gevelcheck op afspraak",
    ],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    value = str(value or "").strip()
    try:
        from facadepilot_keys import slugify

        return slugify(value)
    except Exception:
        value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-")
        return value or "item"


def _safe_doc_id(value: str) -> str:
    doc_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "")).strip(".-")
    return doc_id[:120] or f"flyer-{int(time.time())}"


def _project_path(project_dir: Path, path_value: Any) -> Path | None:
    raw = str(path_value or "").strip()
    if not raw:
        return None
    if raw.startswith("/files/"):
        raw = raw[7:]
    path = Path(raw)
    if not path.is_absolute():
        path = project_dir / raw
    try:
        resolved = path.resolve()
        resolved.relative_to(project_dir.resolve())
    except Exception:
        return None
    return resolved if resolved.exists() and resolved.is_file() else None


def _file_url(project_dir: Path, path_value: Any) -> str:
    path = _project_path(project_dir, path_value)
    if not path:
        return ""
    rel = path.resolve().relative_to(project_dir.resolve()).as_posix()
    return f"/files/{rel}"


def _data_uri(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _append_src(url: str, source: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("src", source)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _normalise_profile(project_dir: Path, profile: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    merged = dict(DEFAULT_PROFILE)

    # Optional client profile overlay. This supports both a fixed active.json
    # file and an explicit env var without requiring a larger account system.
    client_profile_path = os.environ.get("FACADEPILOT_CLIENT_PROFILE", "").strip()
    candidates = []
    if client_profile_path:
        candidates.append(Path(client_profile_path))
    candidates.extend([
        project_dir / "client_profiles" / "active.json",
        project_dir / "client_profile.json",
    ])
    for candidate in candidates:
        if not candidate.is_absolute():
            candidate = project_dir / candidate
        if candidate.exists():
            try:
                loaded = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    merged.update({k: v for k, v in loaded.items() if v not in (None, "")})
                    break
            except Exception:
                pass

    if profile:
        merged.update({k: v for k, v in profile.items() if v not in (None, "")})

    if "website" not in merged or not merged.get("website"):
        merged["website"] = DEFAULT_PROFILE["website"]
    if "logo" not in merged:
        merged["logo"] = merged.get("logo_path", "")

    logo_path = _project_path(project_dir, merged.get("logo") or merged.get("logo_path"))
    if logo_path:
        merged["logo_url"] = _file_url(project_dir, logo_path)
        merged["logo_data_uri"] = _data_uri(logo_path)
    else:
        merged["logo_url"] = ""
        merged["logo_data_uri"] = ""

    claims = merged.get("claims")
    if isinstance(claims, str):
        claims = [part.strip() for part in re.split(r"[;\n]+", claims) if part.strip()]
    if not claims:
        claims = list(DEFAULT_PROFILE["claims"])
    merged["claims"] = claims[:5]

    warnings = []
    for key, label in [("naam", "naam"), ("telefoon", "telefoon"), ("website", "website")]:
        if not str(merged.get(key, "")).strip():
            warnings.append(f"Profiel mist {label}.")
    if not str(merged.get("accent_color", "")).strip():
        warnings.append("Profiel mist accentkleur.")
    if not merged.get("logo_url"):
        warnings.append("Geen logo gevonden; tekstlogo wordt gebruikt.")

    return merged, warnings


def _find_latest_csv(project_dir: Path) -> Path | None:
    patterns = [
        "*_with_renders.csv",
        "*with_renders*.csv",
        "*_scored*.csv",
        "facadepilot_leads_*.csv",
        "*.csv",
    ]
    seen: set[Path] = set()
    candidates: list[Path] = []
    for pattern in patterns:
        for path in project_dir.glob(pattern):
            if path.name.startswith(".") or path in seen:
                continue
            seen.add(path)
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _read_rows(csv_path: Path | None) -> list[dict[str, str]]:
    if not csv_path or not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _infer_niscode(project_dir: Path, capakey: str, default_niscode: str = "") -> str:
    if default_niscode:
        return default_niscode
    if not capakey:
        return ""
    slug = _slugify(capakey)
    landing_dir = project_dir / "landing"
    if not landing_dir.exists():
        return ""
    for html_path in landing_dir.glob(f"*/{slug}.html"):
        return html_path.parent.name
    return ""


def _landing_url_for_row(
    project_dir: Path,
    row: dict[str, Any],
    public_base_url: str,
    default_niscode: str = "",
    source: str = "flyer_editor",
) -> str:
    explicit = str(row.get("landing_url", "") or row.get("public_url", "") or "").strip()
    if explicit:
        return _append_src(explicit, source)
    capakey = str(row.get("CAPAKEY", "") or row.get("capakey", "") or "").strip()
    niscode = str(row.get("niscode", "") or row.get("NISCODE", "") or "").strip()
    niscode = niscode or _infer_niscode(project_dir, capakey, default_niscode)
    if not capakey or not niscode:
        return ""
    base = os.environ.get("FACADEPILOT_TRACKER_URL", public_base_url or DEFAULT_BASE_URL).strip()
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return f"{base.rstrip('/')}/r/{niscode}-{_slugify(capakey)}?src={source}"


def _variant_items(project_dir: Path, row: dict[str, Any]) -> list[dict[str, str]]:
    variants: list[dict[str, str]] = []
    streetview = _file_url(project_dir, row.get("streetview_path"))
    if streetview:
        variants.append({"key": "streetview", "label": "Voorfoto", "url": streetview})

    main_render = _file_url(project_dir, row.get("render_path"))
    if main_render:
        variants.append({"key": "render", "label": "Hoofdvoorstel", "url": main_render})

    for key, value in sorted(row.items()):
        if not key.startswith("render_path_") or key == "render_path":
            continue
        url = _file_url(project_dir, value)
        if url:
            label = key.replace("render_path_", "").replace("_", " ")
            variants.append({"key": key, "label": label.title(), "url": url})

    return variants


def _render_items_from_csv(
    project_dir: Path,
    csv_path: Path | None,
    public_base_url: str,
    default_niscode: str = "",
) -> list[dict[str, Any]]:
    items = []
    for idx, row in enumerate(_read_rows(csv_path)):
        capakey = str(row.get("CAPAKEY", "") or row.get("capakey", "") or "").strip()
        variants = _variant_items(project_dir, row)
        render_url = next((v["url"] for v in variants if v["key"] != "streetview"), "")
        if not variants and not render_url:
            continue
        landing_url = _landing_url_for_row(project_dir, row, public_base_url, default_niscode)
        items.append({
            "id": capakey or f"row-{idx:03d}",
            "capakey": capakey,
            "adres": str(row.get("adres", "") or row.get("address", "") or f"Lead {idx + 1}"),
            "niscode": str(row.get("niscode", "") or row.get("NISCODE", "") or default_niscode),
            "klasse": str(row.get("lead_klasse", "") or row.get("klasse", "")),
            "score": str(row.get("lead_score", "") or row.get("score", "")),
            "render": render_url,
            "streetview": next((v["url"] for v in variants if v["key"] == "streetview"), ""),
            "variants": variants,
            "landing_url": landing_url,
            "has_landing_url": bool(landing_url),
            "source_csv": csv_path.name if csv_path else "",
        })
    return items


def _render_items_from_files(project_dir: Path) -> list[dict[str, Any]]:
    renders_dir = project_dir / "renders"
    if not renders_dir.exists():
        return []
    items = []
    for idx, render_path in enumerate(sorted(renders_dir.glob("*_render.jpg"))):
        base = render_path.name.replace("_render.jpg", "")
        streetview = renders_dir / f"{base}_streetview.jpg"
        variants = []
        if streetview.exists():
            variants.append({"key": "streetview", "label": "Voorfoto", "url": _file_url(project_dir, streetview)})
        variants.append({"key": "render", "label": "Hoofdvoorstel", "url": _file_url(project_dir, render_path)})
        items.append({
            "id": base,
            "capakey": "",
            "adres": base.replace("_", " "),
            "niscode": "",
            "klasse": "",
            "score": "",
            "render": _file_url(project_dir, render_path),
            "streetview": _file_url(project_dir, streetview),
            "variants": variants,
            "landing_url": "",
            "has_landing_url": False,
            "source_csv": "renders/",
        })
    return items


def _flyer_items(project_dir: Path) -> list[dict[str, Any]]:
    flyers_dir = project_dir / "flyers"
    if not flyers_dir.exists():
        return []
    return [
        {
            "name": path.name,
            "url": _file_url(project_dir, path),
            "size_kb": round(path.stat().st_size / 1024),
            "mtime": int(path.stat().st_mtime),
        }
        for path in sorted(flyers_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


def _edited_items(project_dir: Path) -> list[dict[str, Any]]:
    edits_dir = project_dir / "flyer_edits"
    if not edits_dir.exists():
        return []
    items = []
    for path in sorted(edits_dir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append({
            "id": path.stem,
            "name": path.name,
            "kind": "export",
            "url": _file_url(project_dir, path),
            "mtime": int(path.stat().st_mtime),
        })
    draft_dir = edits_dir / "drafts"
    if draft_dir.exists():
        for path in sorted(draft_dir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
            items.append({
                "id": path.stem,
                "name": path.name,
                "kind": "draft",
                "url": _file_url(project_dir, path),
                "mtime": int(path.stat().st_mtime),
            })
    return items[:50]


def flyer_editor_payload(
    project_dir: Path,
    profile: dict[str, Any] | None = None,
    public_base_url: str = DEFAULT_BASE_URL,
    default_niscode: str = "",
) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    profile_data, warnings = _normalise_profile(project_dir, profile)
    csv_path = _find_latest_csv(project_dir)
    renders = _render_items_from_csv(project_dir, csv_path, public_base_url, default_niscode)
    if not renders:
        renders = _render_items_from_files(project_dir)
    return {
        "ok": True,
        "profile": profile_data,
        "profile_warnings": warnings,
        "renders": renders,
        "flyers": _flyer_items(project_dir),
        "edited": _edited_items(project_dir),
        "source_csv": csv_path.name if csv_path else "",
        "generated_at": _now_iso(),
        "guardrails": {
            "writes_only_to": "flyer_edits/",
            "requires_landing_url_for_pdf": True,
            "review_gate": "flyer_proof",
        },
    }


def generate_qr_data_uri(url: str, size: int = 220) -> str:
    if not str(url or "").strip():
        return ""
    try:
        from facadepilot_flyer import generate_qr_code

        return generate_qr_code(url, size=size)
    except Exception:
        import qrcode
        from PIL import Image

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1a1a1a", back_color="white")
        img = img.resize((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def flyer_editor_qr(
    project_dir: Path,
    capakey: str = "",
    url: str = "",
    profile: dict[str, Any] | None = None,
    public_base_url: str = DEFAULT_BASE_URL,
    default_niscode: str = "",
) -> dict[str, Any]:
    landing_url = str(url or "").strip()
    if not landing_url and capakey:
        payload = flyer_editor_payload(project_dir, profile, public_base_url, default_niscode)
        for item in payload.get("renders", []):
            if item.get("capakey") == capakey or item.get("id") == capakey:
                landing_url = item.get("landing_url", "")
                break
    if not landing_url:
        return {"ok": False, "error": "Geen landing-URL voor deze lead.", "landing_url": ""}
    return {"ok": True, "landing_url": landing_url, "data_uri": generate_qr_data_uri(landing_url)}


def _export_shell(stage_html: str, title: str = "Flyer export") -> str:
    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>{html.escape(title)}</title>
<style>
@page {{ size: 210mm 148mm; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ width: 210mm; min-height: 148mm; margin: 0; background: #fff; }}
body {{ font-family: Arial, sans-serif; color: #172033; }}
.fe-stage {{ width: 210mm !important; height: 148mm !important; transform: none !important; }}
.fe-page {{ width: 210mm !important; height: 148mm !important; }}
[contenteditable] {{ outline: none; }}
</style>
</head>
<body>
{stage_html}
</body>
</html>"""


async def _html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1050, "height": 742}, device_scale_factor=1)
        await page.goto(html_path.as_uri(), wait_until="networkidle")
        await page.pdf(path=str(pdf_path), width="210mm", height="148mm", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        await browser.close()


def _submit_flyer_proof(project_dir: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    try:
        from homepilot_shared.review_gate import ReviewGate

        gate = ReviewGate(pilot="facadepilot", gate="flyer_proof")
        for method_name in ("submit", "add", "enqueue"):
            method = getattr(gate, method_name, None)
            if method:
                result = method(evidence)
                return {"ok": True, "mode": f"ReviewGate.{method_name}", "result": result}
    except Exception as exc:
        review_error = str(exc)
    else:
        review_error = "ReviewGate heeft geen ondersteunde submit-methode."

    queue_path = project_dir / "flyer_edits" / "review_queue.jsonl"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"gate": "flyer_proof", "created_at": _now_iso(), "evidence": evidence, "review_gate_error": review_error}, ensure_ascii=False) + "\n")
    return {"ok": False, "mode": "local_review_queue", "path": str(queue_path), "error": review_error}


def save_flyer_editor_export(project_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    stage_html = str(payload.get("html") or payload.get("stage_html") or "").strip()
    if not stage_html:
        return {"ok": False, "error": "Geen flyer-inhoud ontvangen."}

    lead = payload.get("lead") if isinstance(payload.get("lead"), dict) else {}
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    landing_url = str(payload.get("landing_url") or lead.get("landing_url") or "").strip()
    make_pdf = payload.get("make_pdf", True) is not False and str(payload.get("make_pdf", "true")).lower() != "false"
    draft = bool(payload.get("draft"))
    if make_pdf and not landing_url:
        return {"ok": False, "error": "PDF-export geblokkeerd: deze lead heeft geen landing-URL."}

    capakey = str(lead.get("capakey") or lead.get("id") or "flyer")
    doc_id = _safe_doc_id(str(payload.get("doc_id") or f"{_slugify(capakey)}-{int(time.time())}"))
    edits_dir = project_dir / "flyer_edits" / ("drafts" if draft else "")
    edits_dir.mkdir(parents=True, exist_ok=True)

    html_path = edits_dir / f"{doc_id}.html"
    pdf_path = edits_dir / f"{doc_id}.pdf"
    title = f"Flyer {lead.get('adres') or capakey}"
    html_path.write_text(_export_shell(stage_html, title=title), encoding="utf-8")

    meta = {
        "doc_id": doc_id,
        "draft": draft,
        "created_at": _now_iso(),
        "html_path": str(html_path),
        "pdf_path": str(pdf_path) if make_pdf else "",
        "source_adres": lead.get("adres", ""),
        "capakey": lead.get("capakey", ""),
        "landing_url": landing_url,
        "template": payload.get("template", "facade-a5-editor"),
        "profile_name": profile.get("naam", ""),
    }
    (edits_dir / f"{doc_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if make_pdf:
        try:
            asyncio.run(_html_to_pdf(html_path, pdf_path))
        except Exception as exc:
            return {"ok": False, "error": f"PDF-export mislukt: {exc}", "html_path": str(html_path)}

    review = None
    if make_pdf:
        review = _submit_flyer_proof(project_dir, meta)

    return {
        "ok": True,
        "doc_id": doc_id,
        "draft": draft,
        "html_path": str(html_path),
        "pdf_path": str(pdf_path) if make_pdf else "",
        "html_url": _file_url(project_dir, html_path),
        "pdf_url": _file_url(project_dir, pdf_path) if make_pdf and pdf_path.exists() else "",
        "review": review,
    }


def load_flyer_editor_draft(project_dir: Path, doc_id: str) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    safe = _safe_doc_id(doc_id)
    candidates = [
        project_dir / "flyer_edits" / "drafts" / f"{safe}.html",
        project_dir / "flyer_edits" / f"{safe}.html",
    ]
    for path in candidates:
        try:
            path.resolve().relative_to((project_dir / "flyer_edits").resolve())
        except Exception:
            continue
        if path.exists():
            meta_path = path.with_suffix(".json")
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            text = path.read_text(encoding="utf-8")
            match = re.search(r"<body[^>]*>(.*)</body>", text, flags=re.I | re.S)
            return {"ok": True, "doc_id": safe, "html": match.group(1).strip() if match else text, "meta": meta}
    return {"ok": False, "error": "Draft niet gevonden."}


def flyer_editor_html() -> str:
    return EDITOR_HTML


EDITOR_HTML = r"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<title>HomePilot Flyer-editor</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#101722;color:#e8eef8}
button,input,select{font:inherit}
.app{display:grid;grid-template-columns:300px minmax(620px,1fr) 280px;min-height:100vh}
.panel{background:#121c2a;border-right:1px solid rgba(255,255,255,.08);padding:18px;overflow:auto}
.panel.right{border-right:0;border-left:1px solid rgba(255,255,255,.08)}
.top{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:16px 20px;border-bottom:1px solid rgba(255,255,255,.08);background:#0d1520}
.brand h1{font-size:17px;margin:0}.brand p{margin:3px 0 0;color:#92a2b8;font-size:12px}
.toolbar{display:flex;gap:8px;align-items:center}
.btn{border:0;border-radius:8px;padding:10px 12px;background:#223147;color:#e8eef8;cursor:pointer;font-weight:700}
.btn:hover{background:#2d405c}.btn.primary{background:var(--accent,#3b5998);color:#fff}.btn.danger{background:#5b1d27;color:#ffd7dc}.btn:disabled{opacity:.45;cursor:not-allowed}
.status{padding:10px;border-radius:8px;background:rgba(255,255,255,.05);font-size:12px;color:#bdc8d9;margin-bottom:14px}
.status.warn{background:rgba(245,158,11,.13);color:#f8d48a}.status.good{background:rgba(34,197,94,.12);color:#9ce7b4}.status.bad{background:rgba(239,68,68,.14);color:#ffc1c1}
.section{margin:18px 0}.section h2{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#92a2b8;margin:0 0 10px}
.source{display:grid;grid-template-columns:58px 1fr;gap:10px;padding:9px;border-radius:8px;background:rgba(255,255,255,.045);margin-bottom:8px;cursor:pointer;border:1px solid transparent}
.source:hover,.source.active{border-color:var(--accent,#3b5998);background:rgba(59,89,152,.14)}
.source img{width:58px;height:42px;object-fit:cover;border-radius:5px;background:#0b111a}
.source strong{display:block;font-size:12px;line-height:1.25}.source span{display:block;color:#92a2b8;font-size:11px;margin-top:3px}
.canvas-wrap{overflow:auto;padding:28px;display:grid;place-items:center;min-height:calc(100vh - 66px);background:#e7ebf1}
.fe-stage{width:1050px;height:742px;background:#fff;color:#182130;box-shadow:0 24px 70px rgba(0,0,0,.22);position:relative;overflow:hidden;transform-origin:center}
.fe-page{position:absolute;inset:0;background:#f6f3ee}
.fe-band{position:absolute;left:0;top:0;width:360px;height:100%;background:var(--accent,#3b5998)}
.fe-logo{position:absolute;left:46px;top:42px;color:#fff;font-weight:900;font-size:30px;max-width:250px;line-height:1.05}
.fe-logo img{max-width:190px;max-height:70px;display:block}
.fe-kicker{position:absolute;left:46px;top:138px;color:rgba(255,255,255,.82);font-size:18px;max-width:255px}
.fe-title{position:absolute;left:405px;top:45px;font-size:48px;line-height:1.02;font-weight:900;letter-spacing:0;max-width:570px}
.fe-sub{position:absolute;left:405px;top:154px;font-size:21px;line-height:1.3;color:#526074;max-width:565px}
.fe-img{position:absolute;overflow:hidden;border-radius:8px;background:#d8dee8;border:1px solid rgba(0,0,0,.08)}
.fe-img img{width:100%;height:100%;object-fit:cover;display:block}
.fe-img.before{left:405px;top:235px;width:282px;height:215px}.fe-img.after{left:704px;top:235px;width:282px;height:215px}
.fe-label{position:absolute;left:12px;top:12px;background:rgba(0,0,0,.74);color:#fff;border-radius:999px;padding:5px 10px;font-size:14px;font-weight:800}
.fe-claims{position:absolute;left:405px;top:480px;width:385px;display:grid;gap:10px}
.fe-claim{display:flex;gap:10px;align-items:flex-start;font-size:18px;line-height:1.25}.fe-dot{width:12px;height:12px;margin-top:5px;border-radius:50%;background:var(--accent,#3b5998);flex:0 0 auto}
.fe-qr-wrap{position:absolute;right:52px;bottom:50px;width:158px;text-align:center}
.fe-qr{width:142px;height:142px;margin:0 auto 7px;background:#fff;border:2px solid #172033;border-radius:8px;display:grid;place-items:center;color:#172033;font-size:18px;font-weight:900;overflow:hidden}
.fe-qr img{width:100%;height:100%;display:block}.fe-qr.missing{border-color:#d02929;color:#d02929;background:#fff2f2;font-size:15px;padding:12px}
.fe-url{font-size:10px;color:#5d6878;word-break:break-word;line-height:1.2}
.fe-contact{position:absolute;left:46px;bottom:44px;color:#fff;font-size:22px;line-height:1.35;max-width:265px}
.fe-small{font-size:14px;color:rgba(255,255,255,.78)}
.prop{display:grid;gap:7px;margin-bottom:12px}.prop label{font-size:11px;color:#92a2b8;text-transform:uppercase;letter-spacing:.06em}.prop input,.prop select{width:100%;border:1px solid rgba(255,255,255,.12);background:#0d1520;color:#e8eef8;border-radius:8px;padding:9px}
.draft{padding:9px;border-radius:8px;background:rgba(255,255,255,.045);margin-bottom:8px;cursor:pointer}.draft:hover{background:rgba(255,255,255,.08)}.draft strong{font-size:12px}.draft span{display:block;font-size:11px;color:#92a2b8;margin-top:3px}
@media(max-width:1050px){.app{grid-template-columns:1fr}.panel{display:block;max-height:none}.panel.right{border-left:0;border-top:1px solid rgba(255,255,255,.08)}.canvas-wrap{padding:14px}.fe-stage{transform:scale(.62);margin:-130px -190px}}
</style>
</head>
<body>
<div class="app" id="app">
  <aside class="panel">
    <div class="section" style="margin-top:0">
      <h2>Profiel</h2>
      <div id="profileBox" class="status">Profiel laden...</div>
    </div>
    <div class="section">
      <h2>Bronnen</h2>
      <div id="sourceList"></div>
    </div>
    <div class="section">
      <h2>Verder werken aan</h2>
      <div id="draftList"></div>
    </div>
  </aside>
  <main>
    <div class="top">
      <div class="brand"><h1>Flyer-editor</h1><p>Handmatige varianten blijven apart in flyer_edits/</p></div>
      <div class="toolbar">
        <button class="btn" id="saveDraftBtn">Draft opslaan</button>
        <button class="btn primary" id="exportBtn">PDF exporteren</button>
        <button class="btn" onclick="location.href='/'">Dashboard</button>
      </div>
    </div>
    <div class="canvas-wrap">
      <div id="feStage" class="fe-stage"></div>
    </div>
  </main>
  <aside class="panel right">
    <div class="section" style="margin-top:0">
      <h2>Exportstatus</h2>
      <div id="exportStatus" class="status">Kies eerst een lead met render.</div>
    </div>
    <div class="section">
      <h2>Beeldbron</h2>
      <div class="prop"><label>Voorbeeldvariant</label><select id="variantSelect"></select></div>
    </div>
    <div class="section">
      <h2>Document</h2>
      <div class="prop"><label>Zoom</label><input id="zoom" type="range" min="50" max="110" value="82"></div>
      <div class="prop"><label>Accentkleur</label><input id="accentInput" type="color"></div>
    </div>
  </aside>
</div>
<script>
const state = { profile: {}, warnings: [], renders: [], edited: [], selected: null, qrOk: false, dirty: false, autosave: null };
const $ = (id) => document.getElementById(id);
function esc(s){ return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
function profileName(){ return state.profile.naam || 'Uw gevelspecialist'; }
function website(){ return state.profile.website || 'facadepilot.be'; }
function tel(){ return state.profile.telefoon || '0800 00 000'; }
function claimList(){ return (state.profile.claims && state.profile.claims.length ? state.profile.claims : ['Gratis gevelcheck op afspraak','Voorstel op basis van uw woningfoto','Techniek en premies na plaatsbezoek te bevestigen']).slice(0,3); }
async function loadAssets(){
  const r = await fetch('/api/flyer_editor_assets');
  const data = await r.json();
  state.profile = data.profile || {};
  state.warnings = data.profile_warnings || [];
  state.renders = data.renders || [];
  state.edited = data.edited || [];
  document.documentElement.style.setProperty('--accent', state.profile.accent_color || '#3b5998');
  $('accentInput').value = state.profile.accent_color || '#3b5998';
  renderProfile();
  renderSources();
  renderDrafts();
  if(state.renders[0]) selectLead(state.renders[0].id);
}
function renderProfile(){
  const box = $('profileBox');
  box.className = state.warnings.length ? 'status warn' : 'status good';
  box.innerHTML = `<strong>Profiel: ${esc(profileName())}</strong><br>${esc(tel())}<br>${esc(website())}` + (state.warnings.length ? `<br><br>${state.warnings.map(esc).join('<br>')}` : '');
}
function renderSources(){
  const list = $('sourceList');
  if(!state.renders.length){ list.innerHTML = `<div class="status warn">Nog geen renders gevonden. Draai eerst render + landing, of plaats een CSV met render_path in deze map.</div>`; return; }
  list.innerHTML = state.renders.map(item => `
    <div class="source ${state.selected && state.selected.id === item.id ? 'active' : ''}" onclick="selectLead('${esc(item.id)}')">
      <img src="${esc(item.render || item.streetview || '')}" alt="">
      <div><strong>${esc(item.adres || item.id)}</strong><span>${esc(item.klasse || 'lead')} ${item.has_landing_url ? 'met landing-URL' : 'zonder landing-URL'}</span></div>
    </div>`).join('');
}
function renderDrafts(){
  const list = $('draftList');
  if(!state.edited.length){ list.innerHTML = `<div class="status">Nog geen drafts of exports.</div>`; return; }
  list.innerHTML = state.edited.map(item => `<div class="draft" onclick="openDraft('${esc(item.id)}')"><strong>${esc(item.name)}</strong><span>${esc(item.kind)}</span></div>`).join('');
}
async function selectLead(id){
  const item = state.renders.find(x => x.id === id);
  if(!item) return;
  state.selected = item;
  state.qrOk = false;
  renderSources();
  buildTemplate(item);
  renderVariantOptions(item);
  await loadQr(item);
  markDirty(false);
}
function buildTemplate(item){
  const before = item.streetview || item.render || '';
  const after = item.render || item.streetview || '';
  const logo = state.profile.logo_url ? `<img src="${esc(state.profile.logo_url)}" alt="${esc(profileName())}">` : esc(profileName());
  $('feStage').innerHTML = `
    <div class="fe-page">
      <div class="fe-band"></div>
      <div class="fe-logo fe-text" contenteditable="true">${logo}</div>
      <div class="fe-kicker fe-text" contenteditable="true">Persoonlijke gevelcheck voor</div>
      <div class="fe-contact fe-text" contenteditable="true"><strong>${esc(tel())}</strong><br><span class="fe-small">${esc(website())}</span></div>
      <div class="fe-title fe-text" contenteditable="true">Wat als uw gevel er zo uitzag?</div>
      <div class="fe-sub fe-text" contenteditable="true">${esc(item.adres || 'Deze woning')} krijgt een concreet voorstel met beeld, aanpak en opvolging.</div>
      <div class="fe-img before"><img src="${esc(before)}" alt=""><div class="fe-label">Nu</div></div>
      <div class="fe-img after"><img id="afterImg" src="${esc(after)}" alt=""><div class="fe-label">Voorstel</div></div>
      <div class="fe-claims">${claimList().map(c => `<div class="fe-claim fe-text" contenteditable="true"><span class="fe-dot"></span><span>${esc(c)}</span></div>`).join('')}</div>
      <div class="fe-qr-wrap"><div id="qrBox" class="fe-qr">QR</div><div id="qrLabel" class="fe-url"></div></div>
    </div>`;
  bindStage();
  updateExportStatus();
}
function bindStage(){
  $('feStage').querySelectorAll('[contenteditable]').forEach(el => el.addEventListener('input', () => markDirty(true)));
}
function renderVariantOptions(item){
  const sel = $('variantSelect');
  sel.innerHTML = (item.variants || []).filter(v => v.key !== 'streetview').map(v => `<option value="${esc(v.url)}">${esc(v.label)}</option>`).join('');
  sel.onchange = () => { const img = $('afterImg'); if(img && sel.value){ img.src = sel.value; markDirty(true); } };
}
async function loadQr(item){
  const box = $('qrBox');
  const label = $('qrLabel');
  box.className = 'fe-qr';
  box.textContent = 'QR laden';
  label.textContent = '';
  const qs = item.capakey ? `capakey=${encodeURIComponent(item.capakey)}` : `url=${encodeURIComponent(item.landing_url || '')}`;
  const r = await fetch('/api/flyer_editor_qr?' + qs);
  const data = await r.json();
  if(data.ok){
    state.qrOk = true;
    item.landing_url = data.landing_url;
    box.innerHTML = `<img src="${data.data_uri}" alt="QR">`;
    label.textContent = data.landing_url;
  } else {
    state.qrOk = false;
    box.className = 'fe-qr missing';
    box.textContent = 'GEEN LANDING-URL';
    label.textContent = data.error || 'Export geblokkeerd';
  }
  updateExportStatus();
}
function updateExportStatus(message){
  const status = $('exportStatus');
  if(message){ status.className = message.ok ? 'status good' : 'status bad'; status.innerHTML = message.text; return; }
  if(!state.selected){ status.className='status'; status.textContent='Kies eerst een lead met render.'; return; }
  if(!state.qrOk){ status.className='status bad'; status.textContent='PDF-export geblokkeerd tot deze lead een landing-URL heeft.'; return; }
  status.className='status good'; status.textContent='Scanbare QR gekoppeld. Klaar voor PDF-export en flyer-proof review.';
}
function markDirty(value=true){ state.dirty = value; }
async function saveDraft(){
  if(!$('feStage').innerHTML.trim()) return;
  const result = await postExport({draft:true, make_pdf:false});
  if(result.ok){ markDirty(false); updateExportStatus({ok:true,text:'Draft opgeslagen.'}); await loadAssets(); }
  else updateExportStatus({ok:false,text:esc(result.error || 'Draft opslaan mislukt.')});
}
async function exportPdf(){
  if(!state.selected) return updateExportStatus({ok:false,text:'Kies eerst een lead.'});
  if(!state.qrOk) return updateExportStatus({ok:false,text:'PDF-export geblokkeerd: geen landing-URL.'});
  updateExportStatus({ok:true,text:'PDF wordt gemaakt...'});
  const result = await postExport({draft:false, make_pdf:true});
  if(result.ok){
    markDirty(false);
    const link = result.pdf_url ? `<br><a style="color:#9cc3ff" href="${esc(result.pdf_url)}" target="_blank">Open PDF</a>` : '';
    updateExportStatus({ok:true,text:'PDF-export klaar. Aangemeld voor flyer-proof review.' + link});
    await loadAssets();
  } else updateExportStatus({ok:false,text:esc(result.error || 'PDF-export mislukt.')});
}
async function postExport(options){
  const body = {
    html: $('feStage').innerHTML,
    draft: !!options.draft,
    make_pdf: options.make_pdf !== false,
    lead: state.selected || {},
    profile: state.profile,
    landing_url: state.selected ? state.selected.landing_url : '',
    template: 'facade-a5-editor'
  };
  const r = await fetch('/api/flyer_editor_export', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  return await r.json();
}
async function openDraft(id){
  if(state.dirty && !confirm('Er zijn onopgeslagen wijzigingen. Draft laden?')) return;
  const r = await fetch('/api/flyer_editor_draft?id=' + encodeURIComponent(id));
  const data = await r.json();
  if(!data.ok) return updateExportStatus({ok:false,text:esc(data.error || 'Draft niet gevonden.')});
  $('feStage').innerHTML = data.html;
  bindStage();
  markDirty(false);
  updateExportStatus({ok:true,text:'Draft geladen.'});
}
$('saveDraftBtn').addEventListener('click', saveDraft);
$('exportBtn').addEventListener('click', exportPdf);
$('zoom').addEventListener('input', e => $('feStage').style.transform = `scale(${Number(e.target.value)/100})`);
$('accentInput').addEventListener('input', e => { document.documentElement.style.setProperty('--accent', e.target.value); state.profile.accent_color = e.target.value; markDirty(true); });
window.addEventListener('beforeunload', e => { if(state.dirty){ e.preventDefault(); e.returnValue=''; }});
window.addEventListener('keydown', e => { if(e.key === 'Escape' && state.dirty){ if(confirm('Wijzigingen zijn als draft op te slaan. Nu opslaan?')) saveDraft(); }});
state.autosave = setInterval(() => { if(state.dirty) saveDraft(); }, 10000);
loadAssets();
</script>
</body>
</html>"""

