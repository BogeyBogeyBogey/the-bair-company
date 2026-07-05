"""Build an auth-gated HomePilot live demo portal for Vercel.

The generated package keeps the large customer snapshot out of public static
JavaScript files. Browser access goes through serverless API endpoints that
verify a Supabase session and tenant membership before returning demo chunks.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATIC_FILES = ("index.html", "styles.css", "app.js")
PROPERTY_CHUNK_SIZE = 250
BRAIN_EDGE_CHUNK_SIZE = 1800


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def chunks(rows: list[Any], size: int) -> list[list[Any]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def safe_boardroom_placeholder() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HomePilot boardroom report</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: Inter, system-ui, sans-serif; background: #f7f8f5; color: #1f2526; }
    main { width: min(720px, calc(100vw - 32px)); background: #fff; border: 1px solid #d9dfdc; border-radius: 8px; padding: 28px; box-shadow: 0 18px 42px rgba(31,37,38,.11); }
    p { color: #64706d; line-height: 1.55; }
    a { display: inline-flex; min-height: 42px; align-items: center; border-radius: 6px; background: #23312c; color: #fff; padding: 0 14px; text-decoration: none; font-weight: 700; }
    .badge { display: inline-flex; border: 1px solid rgba(168,95,69,.34); border-radius: 6px; background: #fff7ed; color: #854d2d; padding: 7px 10px; font-size: 12px; font-weight: 800; text-transform: uppercase; }
  </style>
</head>
<body>
  <main>
    <div class="badge">Demo · synthetic data</div>
    <h1>Boardroom report is gated</h1>
    <p>This public route intentionally contains no customer snapshot or raw demo rows. Open the HomePilot portal and log in to review the DAW buyer-demo workspace.</p>
    <p>The Monday demo remains explicitly synthetic: generated records, illustrative funnel metrics, and no homeowner intent claims.</p>
    <a href="/">Open HomePilot portal</a>
  </main>
</body>
</html>
"""


def api_config_js(supabase_url: str, publishable_key: str, tenant_id: str) -> str:
    return f"""const SUPABASE_URL = process.env.SUPABASE_URL || {json.dumps(supabase_url)};
const SUPABASE_PUBLISHABLE_KEY = process.env.SUPABASE_PUBLISHABLE_KEY || {json.dumps(publishable_key)};
const HOMEPILOT_TENANT_ID = process.env.HOMEPILOT_TENANT_ID || {json.dumps(tenant_id)};

module.exports = {{
  SUPABASE_URL,
  SUPABASE_PUBLISHABLE_KEY,
  HOMEPILOT_TENANT_ID
}};
"""


def api_auth_js() -> str:
    return """const { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, HOMEPILOT_TENANT_ID } = require("./_config");

function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(payload));
}

function bearerToken(req) {
  const value = req.headers.authorization || req.headers.Authorization || "";
  const match = String(value).match(/^Bearer\\s+(.+)$/i);
  return match ? match[1] : "";
}

async function supabaseFetch(path, options = {}) {
  const headers = {
    apikey: SUPABASE_PUBLISHABLE_KEY,
    ...options.headers
  };
  return fetch(`${SUPABASE_URL}${path}`, { ...options, headers });
}

async function verifyAccess(req) {
  const token = bearerToken(req);
  if (!token) {
    const error = new Error("Missing bearer token");
    error.status = 401;
    throw error;
  }

  const userResponse = await supabaseFetch("/auth/v1/user", {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!userResponse.ok) {
    const error = new Error("Invalid Supabase session");
    error.status = 401;
    throw error;
  }
  const user = await userResponse.json();

  const membershipResponse = await supabaseFetch(`/rest/v1/homepilot_live_memberships?select=tenant_id,role,modules,partner_scope&tenant_id=eq.${encodeURIComponent(HOMEPILOT_TENANT_ID)}&limit=1`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json"
    }
  });
  if (!membershipResponse.ok) {
    const error = new Error("Membership check failed");
    error.status = 403;
    throw error;
  }
  const memberships = await membershipResponse.json();
  if (!Array.isArray(memberships) || memberships.length < 1) {
    const error = new Error("No tenant membership");
    error.status = 403;
    throw error;
  }

  return { user, membership: memberships[0] };
}

module.exports = { sendJson, supabaseFetch, verifyAccess };
"""


def api_login_js() -> str:
    return """const { HOMEPILOT_TENANT_ID } = require("./_config");
const { sendJson, supabaseFetch } = require("./_auth");

module.exports = async function handler(req, res) {
  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
    const email = String(body.email || "").trim();
    const password = String(body.password || "");
    if (!email || !password) return sendJson(res, 400, { error: "email_password_required" });

    const tokenResponse = await supabaseFetch("/auth/v1/token?grant_type=password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const tokenPayload = await tokenResponse.json();
    if (!tokenResponse.ok || !tokenPayload.access_token) {
      return sendJson(res, 401, { error: "invalid_login" });
    }

    const membershipResponse = await supabaseFetch(`/rest/v1/homepilot_live_memberships?select=tenant_id,role,modules,partner_scope&tenant_id=eq.${encodeURIComponent(HOMEPILOT_TENANT_ID)}&limit=1`, {
      headers: {
        Authorization: `Bearer ${tokenPayload.access_token}`,
        Accept: "application/json"
      }
    });
    const memberships = membershipResponse.ok ? await membershipResponse.json() : [];
    if (!Array.isArray(memberships) || memberships.length < 1) {
      return sendJson(res, 403, { error: "no_tenant_membership" });
    }

    return sendJson(res, 200, {
      access_token: tokenPayload.access_token,
      expires_in: tokenPayload.expires_in,
      token_type: tokenPayload.token_type || "bearer",
      user: { email: tokenPayload.user?.email || email },
      tenant: { id: HOMEPILOT_TENANT_ID },
      membership: memberships[0]
    });
  } catch (error) {
    return sendJson(res, 500, { error: "login_failed" });
  }
};
"""


def api_data_js(file_path: str) -> str:
    return f"""const fs = require("fs");
const path = require("path");
const {{ sendJson, verifyAccess }} = require("./_auth");

module.exports = async function handler(req, res) {{
  try {{
    await verifyAccess(req);
    const dataPath = path.join(process.cwd(), "api", "_data", {json.dumps(file_path)});
    return sendJson(res, 200, JSON.parse(fs.readFileSync(dataPath, "utf8")));
  }} catch (error) {{
    return sendJson(res, error.status || 500, {{ error: error.message || "request_failed" }});
  }}
}};
"""


def api_chunk_js(kind: str, folder: str, prefix: str, total_parts: int) -> str:
    return f"""const fs = require("fs");
const path = require("path");
const {{ sendJson, verifyAccess }} = require("./_auth");

module.exports = async function handler(req, res) {{
  try {{
    await verifyAccess(req);
    const rawPart = Number(req.query.part || 0);
    const part = Number.isInteger(rawPart) && rawPart >= 0 ? rawPart : 0;
    if (part >= {total_parts}) return sendJson(res, 404, {{ error: "part_not_found", kind: {json.dumps(kind)} }});
    const fileName = `{prefix}-${{String(part).padStart(3, "0")}}.json`;
    const dataPath = path.join(process.cwd(), "api", "_data", {json.dumps(folder)}, fileName);
    return sendJson(res, 200, JSON.parse(fs.readFileSync(dataPath, "utf8")));
  }} catch (error) {{
    return sendJson(res, error.status || 500, {{ error: error.message || "request_failed" }});
  }}
}};
"""


def auth_live_js(default_email: str) -> str:
    return f"""(() => {{
  const TOKEN_KEY = "homepilot.daw.accessToken";
  const DEFAULT_EMAIL = {json.dumps(default_email)};

  function el(tag, attrs = {{}}, children = []) {{
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {{
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else node.setAttribute(key, value);
    }});
    children.forEach((child) => node.appendChild(child));
    return node;
  }}

  function injectStyles() {{
    const style = el("style", {{ text: `
      .live-auth-overlay {{ position: fixed; inset: 0; z-index: 9999; display: grid; place-items: center; background: rgba(247,248,245,.96); color: #1f2526; }}
      .live-auth-card {{ width: min(460px, calc(100vw - 32px)); background: #fff; border: 1px solid #d9dfdc; border-radius: 8px; padding: 24px; box-shadow: 0 18px 42px rgba(31,37,38,.14); }}
      .live-auth-card h2 {{ margin: 10px 0 6px; font-size: 24px; }}
      .live-auth-card p {{ margin: 0 0 16px; color: #64706d; line-height: 1.45; }}
      .live-auth-card label {{ display: grid; gap: 6px; margin: 12px 0; font-size: 13px; font-weight: 760; }}
      .live-auth-card input {{ min-height: 42px; border: 1px solid #d9dfdc; border-radius: 6px; padding: 0 12px; font: inherit; }}
      .live-auth-card button {{ min-height: 42px; border: 0; border-radius: 6px; background: #23312c; color: #fff; padding: 0 14px; font: inherit; font-weight: 780; cursor: pointer; }}
      .live-auth-badge {{ display: inline-flex; border: 1px solid rgba(168,95,69,.34); border-radius: 6px; background: #fff7ed; color: #854d2d; padding: 7px 10px; font-size: 12px; font-weight: 800; text-transform: uppercase; }}
      .live-auth-error {{ min-height: 20px; color: #9f1239; font-size: 13px; font-weight: 700; }}
      .live-auth-status {{ margin-top: 12px; color: #64706d; font-size: 13px; }}
      .live-logout-btn {{ border: 1px solid #d9dfdc; background: #fff; color: #1f2526; min-height: 42px; padding: 0 12px; border-radius: 6px; font: inherit; font-weight: 760; }}
    ` }});
    document.head.appendChild(style);
  }}

  function overlay() {{
    const form = el("form");
    const error = el("div", {{ class: "live-auth-error" }});
    const status = el("div", {{ class: "live-auth-status", text: "Data loads only after Supabase login and tenant membership verification." }});
    const email = el("input", {{ type: "email", autocomplete: "email", value: DEFAULT_EMAIL }});
    const password = el("input", {{ type: "password", autocomplete: "current-password", placeholder: "Password" }});
    const submit = el("button", {{ type: "submit", text: "Log in" }});
    form.append(
      el("label", {{ text: "Email" }}, [email]),
      el("label", {{ text: "Password" }}, [password]),
      submit,
      error,
      status
    );
    const card = el("div", {{ class: "live-auth-card" }}, [
      el("div", {{ class: "live-auth-badge", text: "DAW demo · synthetic data" }}),
      el("h2", {{ text: "HomePilot live portal" }}),
      el("p", {{ text: "This buyer-review workspace is gated. The dataset is synthetic and contains no homeowner intent claims." }}),
      form
    ]);
    const root = el("div", {{ class: "live-auth-overlay" }}, [card]);
    document.body.appendChild(root);
    return {{ root, form, error, status, email, password, submit }};
  }}

  async function apiJson(url, options = {{}}) {{
    const response = await fetch(url, {{
      ...options,
      headers: {{
        "Content-Type": "application/json",
        ...(options.headers || {{}})
      }}
    }});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Request failed: ${{response.status}}`);
    return payload;
  }}

  async function authJson(url) {{
    const token = localStorage.getItem(TOKEN_KEY);
    return apiJson(url, {{ headers: {{ Authorization: `Bearer ${{token}}` }} }});
  }}

  async function loadPortal(status) {{
    status.textContent = "Verifying session...";
    await authJson("/api/session");
    status.textContent = "Loading manifest...";
    const manifest = await authJson("/api/manifest");
    const core = await authJson("/api/snapshot-core");

    const properties = [];
    for (let part = 0; part < manifest.properties.parts; part += 1) {{
      status.textContent = `Loading property chunk ${{part + 1}}/${{manifest.properties.parts}}...`;
      const chunk = await authJson(`/api/properties?part=${{part}}`);
      properties.push(...chunk.rows);
    }}

    const brainNodes = await authJson("/api/brain-nodes");
    const brainEdges = [];
    for (let part = 0; part < manifest.brain.edge_parts; part += 1) {{
      status.textContent = `Loading graph chunk ${{part + 1}}/${{manifest.brain.edge_parts}}...`;
      const chunk = await authJson(`/api/brain-edges?part=${{part}}`);
      brainEdges.push(...chunk.rows);
    }}

    const snapshot = {{
      ...core,
      properties,
      brain: {{
        ...(core.brain || {{}}),
        nodes: brainNodes.rows || [],
        edges: brainEdges
      }}
    }};
    window.HOMEPILOT_LIVE_SNAPSHOT = snapshot;
    if (typeof window.HOMEPILOT_APPLY_DASHBOARD_DATA === "function") {{
      window.HOMEPILOT_APPLY_DASHBOARD_DATA(snapshot);
    }}
    status.textContent = "Ready.";
    addLogout();
  }}

  async function login(email, password) {{
    const payload = await apiJson("/api/login", {{
      method: "POST",
      body: JSON.stringify({{ email, password }})
    }});
    localStorage.setItem(TOKEN_KEY, payload.access_token);
    return payload;
  }}

  function addLogout() {{
    if (document.getElementById("liveLogoutBtn")) return;
    const actions = document.querySelector(".topbar-actions");
    if (!actions) return;
    const button = el("button", {{ id: "liveLogoutBtn", class: "live-logout-btn", type: "button", text: "Logout" }});
    button.addEventListener("click", () => {{
      localStorage.removeItem(TOKEN_KEY);
      window.location.reload();
    }});
    actions.appendChild(button);
  }}

  async function start() {{
    injectStyles();
    const ui = overlay();
    ui.form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      ui.error.textContent = "";
      ui.submit.disabled = true;
      try {{
        await login(ui.email.value, ui.password.value);
        await loadPortal(ui.status);
        ui.root.remove();
      }} catch (error) {{
        ui.error.textContent = error.message || "Login failed";
      }} finally {{
        ui.submit.disabled = false;
      }}
    }});

    if (localStorage.getItem(TOKEN_KEY)) {{
      try {{
        await loadPortal(ui.status);
        ui.root.remove();
      }} catch (error) {{
        localStorage.removeItem(TOKEN_KEY);
        ui.error.textContent = "Please log in again.";
      }}
    }}
  }}

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
}})();
"""


def package_json() -> str:
    return """{
  "private": true,
  "scripts": {
    "check": "node -e \\"const fs=require('fs'); const m=JSON.parse(fs.readFileSync('api/_data/manifest.json','utf8')); if(!m.dataset.synthetic||!m.properties.total||!m.properties.parts) process.exit(1); console.log('live package ok', m.properties.total, 'properties');\\""
  }
}
"""


def vercel_json() -> str:
    return """{
  "functions": {
    "api/*.js": {
      "includeFiles": "api/_data/**"
    }
  },
  "headers": [
    {
      "source": "/api/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "no-store" }
      ]
    },
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" }
      ]
    }
  ],
  "rewrites": [
    { "source": "/app", "destination": "/index.html" }
  ]
}
"""


def build_live_portal(
    customer_package: Path,
    out_dir: Path,
    supabase_url: str,
    publishable_key: str,
    tenant_id: str,
    default_email: str,
) -> dict[str, Any]:
    dashboard_dir = customer_package / "dashboard"
    snapshot_path = customer_package / "data" / "dashboard_snapshot.json"
    snapshot = read_json(snapshot_path)
    properties = list(snapshot.get("properties") or [])
    brain = dict(snapshot.get("brain") or {})
    brain_nodes = list(brain.get("nodes") or [])
    brain_edges = list(brain.get("edges") or [])
    property_chunks = chunks(properties, PROPERTY_CHUNK_SIZE)
    edge_chunks = chunks(brain_edges, BRAIN_EDGE_CHUNK_SIZE)

    if out_dir.exists():
      shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for filename in STATIC_FILES:
        shutil.copy2(dashboard_dir / filename, out_dir / filename)

    index_path = out_dir / "index.html"
    index_html = index_path.read_text(encoding="utf-8")
    if "./auth-live.js" not in index_html:
        index_html = index_html.replace('  <script src="./app.js"></script>', '  <script src="./app.js"></script>\n  <script src="./auth-live.js"></script>')
    write_text(index_path, index_html)

    write_text(out_dir / "dashboard-data.js", "window.HOMEPILOT_DASHBOARD = null;\n")
    write_text(out_dir / "sample-data.js", "window.HOMEPILOT_SAMPLE = null;\n")
    write_text(out_dir / "live-config.js", "window.HOMEPILOT_LIVE_CONFIG = { enabled: true, mode: 'api-gated' };\n")
    write_text(out_dir / "live-data.js", "window.HOMEPILOT_LIVE_SNAPSHOT = null;\n")
    write_text(out_dir / "auth-live.js", auth_live_js(default_email=default_email))
    write_text(out_dir / "boardroom-report.html", safe_boardroom_placeholder())
    write_text(out_dir / "package.json", package_json())
    write_text(out_dir / "vercel.json", vercel_json())

    public_data_dir = out_dir / "data"
    public_data_dir.mkdir()
    write_text(public_data_dir / "README.txt", "No customer snapshot is served from static /data in this live portal. Use authenticated /api endpoints.\n")

    core = dict(snapshot)
    core["properties"] = []
    core["brain"] = {**brain, "nodes": [], "edges": []}
    data_dir = out_dir / "api" / "_data"
    write_json(data_dir / "core.json", core)

    for index, rows in enumerate(property_chunks):
        write_json(data_dir / "properties" / f"properties-{index:03d}.json", {"part": index, "rows": rows})
    write_json(data_dir / "brain" / "nodes.json", {"rows": brain_nodes})
    for index, rows in enumerate(edge_chunks):
        write_json(data_dir / "brain" / f"edges-{index:03d}.json", {"part": index, "rows": rows})

    manifest = {
        "created_at": utc_now(),
        "tenant": snapshot.get("tenant", {}),
        "dataset": {
            "synthetic": True,
            "safe_for_demo": True,
            "label": "DAW buyer-review demo",
            "note": "Generated records are fictional and must not be presented as homeowner intent or real campaign results.",
        },
        "properties": {
            "total": len(properties),
            "chunk_size": PROPERTY_CHUNK_SIZE,
            "parts": len(property_chunks),
        },
        "brain": {
            "nodes": len(brain_nodes),
            "edges": len(brain_edges),
            "edge_chunk_size": BRAIN_EDGE_CHUNK_SIZE,
            "edge_parts": len(edge_chunks),
        },
    }
    write_json(data_dir / "manifest.json", manifest)

    api_dir = out_dir / "api"
    write_text(api_dir / "_config.js", api_config_js(supabase_url, publishable_key, tenant_id))
    write_text(api_dir / "_auth.js", api_auth_js())
    write_text(api_dir / "login.js", api_login_js())
    write_text(api_dir / "session.js", """const { sendJson, verifyAccess } = require("./_auth");

module.exports = async function handler(req, res) {
  try {
    const access = await verifyAccess(req);
    return sendJson(res, 200, {
      user: { email: access.user.email },
      membership: access.membership
    });
  } catch (error) {
    return sendJson(res, error.status || 500, { error: error.message || "request_failed" });
  }
};
""")
    write_text(api_dir / "manifest.js", api_data_js("manifest.json"))
    write_text(api_dir / "snapshot-core.js", api_data_js("core.json"))
    write_text(api_dir / "brain-nodes.js", api_data_js("brain/nodes.json"))
    write_text(api_dir / "properties.js", api_chunk_js("properties", "properties", "properties", len(property_chunks)))
    write_text(api_dir / "brain-edges.js", api_chunk_js("brain_edges", "brain", "edges", len(edge_chunks)))

    return {
        "status": "pass",
        "out_dir": str(out_dir),
        "tenant_id": tenant_id,
        "properties": len(properties),
        "property_parts": len(property_chunks),
        "brain_nodes": len(brain_nodes),
        "brain_edges": len(brain_edges),
        "brain_edge_parts": len(edge_chunks),
        "paths": {
            "index": str(out_dir / "index.html"),
            "manifest": str(data_dir / "manifest.json"),
            "boardroom_placeholder": str(out_dir / "boardroom-report.html"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build auth-gated Vercel package for HomePilot DAW demo")
    parser.add_argument("--customer-package", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--supabase-url", required=True)
    parser.add_argument("--publishable-key", required=True)
    parser.add_argument("--tenant-id", default="daw-belgium-crepi-network")
    parser.add_argument("--default-email", default="daw-demo@facadepilot.be")
    args = parser.parse_args()
    result = build_live_portal(
        customer_package=args.customer_package,
        out_dir=args.out_dir,
        supabase_url=args.supabase_url,
        publishable_key=args.publishable_key,
        tenant_id=args.tenant_id,
        default_email=args.default_email,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
