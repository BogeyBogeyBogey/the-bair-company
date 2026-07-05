#!/usr/bin/env python3
"""
HomePilot local QA runner.

This is intentionally dependency-light. It verifies the contracts that matter
before a pilot import, demo dashboard, or customer review build is shipped:

- platform Python files compile
- unit/contract tests pass
- client JavaScript parses when Node is available
- dashboard SQL contains tenant/module-safe read views
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent

PYTHON_FILES = [
    HERE / "homepilot_account_access.py",
    HERE / "homepilot_customer_access_verification.py",
    HERE / "homepilot_platform.py",
    HERE / "homepilot_api_contract.py",
    HERE / "homepilot_pilot_csv.py",
    HERE / "homepilot_processing_register.py",
    HERE / "homepilot_store.py",
    HERE / "homepilot_sync.py",
    HERE / "homepilot_territory_plan.py",
    HERE / "homepilot_visual_intelligence.py",
    HERE / "homepilot_entitlements.py",
    HERE / "homepilot_enrichment.py",
    HERE / "homepilot_enrichment_refresh.py",
    HERE / "homepilot_metric_access.py",
    HERE / "homepilot_snapshot.py",
    HERE / "homepilot_access_audit.py",
    HERE / "homepilot_audit_trail.py",
    HERE / "homepilot_benchmarks.py",
    HERE / "homepilot_campaign_learning.py",
    HERE / "homepilot_compliance.py",
    HERE / "homepilot_customer_brief.py",
    HERE / "homepilot_customer_package.py",
    HERE / "homepilot_data_dictionary.py",
    HERE / "homepilot_data_quality.py",
    HERE / "homepilot_deployment.py",
    HERE / "homepilot_demo_room.py",
    HERE / "homepilot_due_diligence.py",
    HERE / "homepilot_export.py",
    HERE / "homepilot_onboarding.py",
    HERE / "homepilot_opportunity_dossier.py",
    HERE / "homepilot_ops_status.py",
    HERE / "homepilot_monitoring.py",
    HERE / "homepilot_preflight.py",
    HERE / "homepilot_portal.py",
    HERE / "homepilot_source_ledger.py",
    HERE / "homepilot_recovery.py",
    HERE / "homepilot_release_pack.py",
    HERE / "homepilot_responses.py",
    HERE / "homepilot_retention.py",
    HERE / "homepilot_roi_forecast.py",
    HERE / "homepilot_privacy.py",
    HERE / "homepilot_rls_probe.py",
    HERE / "homepilot_fixture_cleanup.py",
    HERE / "homepilot_healthcheck.py",
    HERE / "homepilot_hosting.py",
    HERE / "homepilot_integrations.py",
    HERE / "homepilot_integration_sync.py",
    HERE / "homepilot_live_fixture.py",
    HERE / "homepilot_launch.py",
    HERE / "homepilot_readiness.py",
    HERE / "homepilot_release_audit.py",
    HERE / "homepilot_qa.py",
]

JS_FILES = [
    HOME_ROOT / "client" / "app.js",
    HOME_ROOT / "client" / "sample-data.js",
    HOME_ROOT / "client" / "dashboard-data.js",
    HOME_ROOT / "client" / "live-config.js",
    HOME_ROOT / "client" / "live-data.js",
]

REQUIRED_SQL_MARKERS = [
    "with (security_invoker = true)",
    "homepilot_has_tenant_access",
    "homepilot_has_module_access",
    "homepilot_property_intelligence",
    "homepilot_property_export",
    "homepilot_campaign_metrics",
    "homepilot_module_metrics",
    "homepilot_metrics_for_customer",
    "homepilot_second_brain_edges",
]


def check_python_compile() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for file_path in PYTHON_FILES:
            py_compile.compile(str(file_path), cfile=str(tmp_path / f"{file_path.stem}.pyc"), doraise=True)
    print("python_compile ok")


def run_unittests() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(HERE)
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(HOME_ROOT / "tests")],
        cwd=HOME_ROOT,
        env=env,
        check=True,
    )
    print("contract_tests ok")


def check_js() -> None:
    node = shutil.which("node")
    if not node:
        print("js_check skipped: node not found")
        return
    subprocess.run([node, "--check", *map(str, JS_FILES)], cwd=HOME_ROOT, check=True)
    print("js_check ok")


def check_sql_contracts() -> None:
    sql = (HERE / "dashboard_views.sql").read_text(encoding="utf-8").lower()
    missing = [marker for marker in REQUIRED_SQL_MARKERS if marker not in sql]
    if missing:
        raise AssertionError(f"dashboard_views.sql missing markers: {missing}")
    print("sql_contracts ok")


def main() -> None:
    check_python_compile()
    run_unittests()
    check_js()
    check_sql_contracts()
    print("homepilot_qa ok")


if __name__ == "__main__":
    main()
