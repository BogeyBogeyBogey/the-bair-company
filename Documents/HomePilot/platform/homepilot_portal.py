#!/usr/bin/env python3
"""
Build a deployable HomePilot customer portal bundle.

Customer packages prove tenant/module scoping. This module turns such a package
into an online-ready portal artifact with public dashboard assets, downloadable
tenant exports, disabled-by-default live Auth/RLS runtime config, security
headers, redirects, route map, and a deployment manifest. It deliberately does
not include secrets or privileged API keys.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_PUBLIC_FILES = ("index.html", "app.js", "styles.css", "dashboard-data.js", "live-config.js", "live-data.js")
REQUIRED_VIEW_MARKERS = {
    "executive": "data-view=\"executive\"",
    "trust": "data-view=\"trust\"",
    "database": "data-view=\"database\"",
    "map": "data-view=\"map\"",
    "second_brain": "data-view=\"brain\"",
}
SECRET_PATTERNS = {
    "service_role_key": re.compile(r"service[-_ ]?role[-_ ]?key", re.IGNORECASE),
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _copy_tree(source: Path, target: Path) -> list[str]:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return [str(path) for path in sorted(target.rglob("*")) if path.is_file()]


def _path_from_manifest(manifest: dict[str, Any], key: str) -> Path | None:
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    value = paths.get(key)
    return Path(value) if value else None


def _scan_public_files(public_dir: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(body):
                findings.append({
                    "file": str(path),
                    "pattern": label,
                })
    return findings


def _view_coverage(public_dir: Path) -> dict[str, bool]:
    html = (public_dir / "index.html").read_text(encoding="utf-8", errors="ignore") if (public_dir / "index.html").exists() else ""
    return {key: marker in html for key, marker in REQUIRED_VIEW_MARKERS.items()}


def render_headers(connect_src: str = "https://*.supabase.co") -> str:
    csp = "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        f"connect-src 'self' {connect_src}" if connect_src else "connect-src 'self'",
        "font-src 'self' data:",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])
    return "\n".join([
        "/*",
        f"  Content-Security-Policy: {csp}",
        "  X-Frame-Options: DENY",
        "  X-Content-Type-Options: nosniff",
        "  Referrer-Policy: no-referrer",
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()",
        "  Cross-Origin-Opener-Policy: same-origin",
        "",
    ])


def render_redirects() -> str:
    return "\n".join([
        "/ /index.html 200",
        "/property/* /index.html 200",
        "/database/* /index.html 200",
        "/brain/* /index.html 200",
        "",
    ])


def live_runtime_config(manifest: dict[str, Any], enabled_modules: list[str]) -> dict[str, Any]:
    return {
        "enabled": False,
        "supabaseUrl": "https://PROJECT.supabase.co",
        "supabaseAnonKey": "",
        "accessTokenStorageKey": "homepilot.customerJwt",
        "tenant": manifest.get("tenant", {}),
        "modules": enabled_modules,
        "views": {
            "propertyIntelligence": "homepilot_property_intelligence",
            "campaignMetrics": "homepilot_campaign_metrics",
            "secondBrainEdges": "homepilot_second_brain_edges",
        },
        "requiredCustomerAuth": "Supabase Auth customer JWT governed by HomePilot tenant/module RLS.",
        "browserCredentialPolicy": "Only the public anon key may be configured in browser assets.",
    }


def render_live_config_js(config: dict[str, Any]) -> str:
    return "window.HOMEPILOT_LIVE_CONFIG = " + json.dumps(config, indent=2, ensure_ascii=False) + ";\n"


def route_map(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    exports_path = _path_from_manifest(manifest, "exports")
    export_files = []
    if exports_path and exports_path.exists():
        export_files = [path.name for path in sorted(exports_path.glob("*.csv"))]
    return [
        {"path": "/", "type": "dashboard", "description": "Executive, trust, database, map, campaign, and second-brain portal."},
        {"path": "/dashboard-data.js", "type": "tenant_snapshot", "description": "Tenant/module-scoped static data snapshot."},
        {"path": "/live-config.js", "type": "runtime_config", "description": "Disabled-by-default customer Auth/RLS runtime configuration."},
        {"path": "/live-data.js", "type": "runtime_loader", "description": "Supabase PostgREST loader using public anon key plus customer JWT."},
        {"path": "/exports/", "type": "downloads", "description": "Customer-safe CSV exports.", "files": export_files},
    ]


def render_readme(portal: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Customer Portal Bundle",
        "",
        f"Created: {portal['created_at']}",
        f"Status: {portal['status']}",
        f"Tenant: {portal['tenant'].get('name')} ({portal['tenant'].get('id')})",
        f"Modules: {', '.join(portal['modules']) or 'none'}",
        "",
        "## What This Contains",
        "",
        "- `public/`: deployable dashboard assets and tenant-scoped data snapshot.",
        "- `public/exports/`: customer-safe CSV exports from the scoped package.",
        "- `public/live-config.js`: disabled-by-default runtime config for live customer Auth/RLS reads.",
        "- `public/live-data.js`: browser loader for Supabase PostgREST views using the customer JWT.",
        "- `_headers`: recommended static-host security headers.",
        "- `_redirects`: SPA-style redirects for static hosts.",
        "- `routes.json`: route and artifact map for operator review.",
        "- `portal_manifest.json`: machine-readable deployment evidence.",
        "",
        "## Production Notes",
        "",
        "- Deploy only after the package access audit is pass.",
        "- Keep privileged Supabase keys server-side only; this bundle contains no service-role key.",
        "- To enable live reads, set `enabled`, `supabaseUrl`, public anon key, and customer JWT handling in `public/live-config.js` after live RLS probes pass.",
        "- Dynamic Supabase reads require customer Auth JWTs and the live RLS probes in release evidence.",
        "",
    ]
    if portal["failures"]:
        lines += ["## Failures", ""]
        lines.extend(f"- {failure}" for failure in portal["failures"])
    if portal["warnings"]:
        lines += ["## Warnings", ""]
        lines.extend(f"- {warning}" for warning in portal["warnings"])
    lines.append("")
    return "\n".join(lines)


def build_portal_bundle(package_manifest_path: Path, out_dir: Path, connect_src: str = "https://*.supabase.co") -> dict[str, Any]:
    manifest = load_json(package_manifest_path)
    package_dir = package_manifest_path.parent
    dashboard_index = _path_from_manifest(manifest, "dashboard_index")
    if not dashboard_index:
        raise ValueError("Customer package manifest is missing paths.dashboard_index")
    dashboard_dir = dashboard_index.parent
    exports_dir = _path_from_manifest(manifest, "exports")

    out_dir.mkdir(parents=True, exist_ok=True)
    public_dir = out_dir / "public"
    copied_dashboard = _copy_tree(dashboard_dir, public_dir)
    copied_exports: list[str] = []
    if exports_dir and exports_dir.exists():
        copied_exports = _copy_tree(exports_dir, public_dir / "exports")

    headers_path = out_dir / "_headers"
    redirects_path = out_dir / "_redirects"
    routes_path = out_dir / "routes.json"
    portal_path = out_dir / "portal_manifest.json"
    readme_path = out_dir / "PORTAL_README.md"
    write_text(headers_path, render_headers(connect_src=connect_src))
    write_text(redirects_path, render_redirects())
    routes = route_map(manifest)
    write_json(routes_path, routes)
    access_audit = manifest.get("access_audit") if isinstance(manifest.get("access_audit"), dict) else {}
    audit_trail = manifest.get("audit_trail") if isinstance(manifest.get("audit_trail"), dict) else {}
    source_scope = manifest.get("source_scope") if isinstance(manifest.get("source_scope"), dict) else {}
    tenant_ids = source_scope.get("tenant_ids") if isinstance(source_scope.get("tenant_ids"), list) else []
    enabled_modules = source_scope.get("enabled_modules") if isinstance(source_scope.get("enabled_modules"), list) else manifest.get("modules", [])
    runtime_config = live_runtime_config(manifest, enabled_modules)
    runtime_config_path = public_dir / "live-config.js"
    runtime_template_path = public_dir / "live-config.example.json"
    write_text(runtime_config_path, render_live_config_js(runtime_config))
    write_json(runtime_template_path, runtime_config)

    missing_public = [filename for filename in REQUIRED_PUBLIC_FILES if not (public_dir / filename).exists()]
    views = _view_coverage(public_dir)
    missing_views = [view for view, present in views.items() if not present]
    secret_findings = _scan_public_files(public_dir)

    failures: list[str] = []
    warnings: list[str] = []
    if manifest.get("package_type") != "homepilot_customer_package":
        failures.append("Source manifest is not a homepilot_customer_package.")
    if missing_public:
        failures.append(f"Missing public files: {missing_public}")
    if missing_views:
        failures.append(f"Missing expected portal views: {missing_views}")
    if access_audit.get("status") != "pass":
        failures.append(f"Package access audit is {access_audit.get('status')!r}, expected pass.")
    if audit_trail.get("status") != "pass":
        failures.append(f"Package audit trail is {audit_trail.get('status')!r}, expected pass.")
    if len(tenant_ids) != 1:
        failures.append(f"Portal source must be scoped to exactly one tenant, got {tenant_ids}.")
    if not enabled_modules:
        failures.append("Portal source has no enabled modules.")
    if secret_findings:
        failures.append(f"Secret-like values found in public portal assets: {secret_findings}")
    if not copied_exports:
        warnings.append("No CSV exports were copied into the portal bundle.")

    live_runtime_status = "pass" if (
        runtime_config_path.exists()
        and runtime_template_path.exists()
        and (public_dir / "live-data.js").exists()
        and not runtime_config["enabled"]
        and runtime_config["modules"]
        and runtime_config["views"]
    ) else "fail"
    if live_runtime_status != "pass":
        failures.append("Live portal runtime config/loader is incomplete.")

    portal = {
        "portal_type": "homepilot_customer_portal_bundle",
        "created_at": utc_now(),
        "status": "pass" if not failures else "fail",
        "tenant": manifest.get("tenant", {}),
        "modules": enabled_modules,
        "source_package": {
            "manifest": str(package_manifest_path),
            "package_dir": str(package_dir),
            "access_audit_status": access_audit.get("status"),
            "audit_trail_status": audit_trail.get("status"),
        },
        "deployment": {
            "mode": "static_portal",
            "public_dir": str(public_dir),
            "headers": str(headers_path),
            "redirects": str(redirects_path),
            "dynamic_data_path": "public/live-data.js can replace the static snapshot after customer Auth and RLS proof.",
            "secrets_included": False,
        },
        "live_runtime": {
            "status": "ready_for_customer_auth_config" if live_runtime_status == "pass" else "action_required",
            "production_verified": False,
            "config": str(runtime_config_path),
            "template": str(runtime_template_path),
            "loader": str(public_dir / "live-data.js"),
            "auth_model": "Supabase anon key plus customer JWT; RLS remains enforced by PostgREST views.",
            "views": runtime_config["views"],
            "enabled_by_default": runtime_config["enabled"],
        },
        "checks": {
            "required_public_files": {"status": "pass" if not missing_public else "fail", "missing": missing_public},
            "expected_views": {"status": "pass" if not missing_views else "fail", "coverage": views, "missing": missing_views},
            "access_audit": {"status": access_audit.get("status")},
            "audit_trail": {"status": audit_trail.get("status")},
            "tenant_scope": {"status": "pass" if len(tenant_ids) == 1 else "fail", "tenant_ids": tenant_ids},
            "module_scope": {"status": "pass" if enabled_modules else "fail", "enabled_modules": enabled_modules},
            "secret_scan": {"status": "pass" if not secret_findings else "fail", "findings": secret_findings},
            "exports": {"status": "pass" if copied_exports else "warn", "files": copied_exports},
            "live_runtime": {"status": live_runtime_status, "config": str(runtime_config_path), "loader": str(public_dir / "live-data.js")},
        },
        "routes": routes,
        "paths": {
            "portal_manifest": str(portal_path),
            "readme": str(readme_path),
            "public_dir": str(public_dir),
            "headers": str(headers_path),
            "redirects": str(redirects_path),
            "routes": str(routes_path),
            "live_config": str(runtime_config_path),
            "live_config_template": str(runtime_template_path),
            "live_loader": str(public_dir / "live-data.js"),
        },
        "copied_files": {
            "dashboard": copied_dashboard,
            "exports": copied_exports,
        },
        "failures": failures,
        "warnings": warnings,
    }
    write_json(portal_path, portal)
    write_text(readme_path, render_readme(portal))
    return portal


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deployable HomePilot customer portal bundle")
    parser.add_argument("--package-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--connect-src", default="https://*.supabase.co")
    args = parser.parse_args()

    portal = build_portal_bundle(
        package_manifest_path=args.package_manifest,
        out_dir=args.out_dir,
        connect_src=args.connect_src,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": portal["status"],
        "tenant": portal["tenant"],
        "modules": portal["modules"],
        "portal_manifest": portal["paths"]["portal_manifest"],
        "public_dir": portal["paths"]["public_dir"],
        "failures": portal["failures"],
        "warnings": portal["warnings"],
    }, indent=2, ensure_ascii=False))
    if portal["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
