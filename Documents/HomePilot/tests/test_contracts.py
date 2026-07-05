from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path


HOME_ROOT = Path(__file__).resolve().parents[1]
PLATFORM = HOME_ROOT / "platform"
sys.path.insert(0, str(PLATFORM))

from homepilot_access_audit import build_access_audit  # noqa: E402
from homepilot_account_access import build_account_access_pack, build_account_access_plan, parse_invitee  # noqa: E402
from homepilot_api_contract import build_api_contract, build_api_contract_pack  # noqa: E402
from homepilot_audit_trail import build_audit_event, build_audit_trail_report, build_customer_package_audit_events  # noqa: E402
from homepilot_autoresearch import build_autoresearch_pack  # noqa: E402
from homepilot_benchmarks import build_benchmark_rows, validate_benchmark_rows  # noqa: E402
from homepilot_boardroom_report import build_boardroom_report, build_boardroom_report_pack  # noqa: E402
from homepilot_campaign_learning import build_campaign_learning_pack, build_campaign_learning_report  # noqa: E402
from homepilot_campaign_segmentation_autoresearch import build_campaign_segmentation_autoresearch_pack  # noqa: E402
from homepilot_compliance import build_compliance_report  # noqa: E402
from homepilot_customer_access_verification import build_customer_access_verification, load_account_access_plan  # noqa: E402
from homepilot_customer_brief import build_customer_brief, build_customer_brief_pack  # noqa: E402
from homepilot_customer_package import build_customer_package  # noqa: E402
from homepilot_data_platform_blueprint import build_data_platform_blueprint_pack  # noqa: E402
from homepilot_data_dictionary import build_data_dictionary, build_data_dictionary_pack  # noqa: E402
from homepilot_data_quality import build_data_quality_report  # noqa: E402
from homepilot_deployment import build_deployment_manifest, build_deployment_pack  # noqa: E402
from homepilot_demo_room import build_demo_payload, build_demo_room  # noqa: E402
from homepilot_due_diligence import build_due_diligence_pack, scan_generated_files  # noqa: E402
from homepilot_enrichment import build_enrichment_pack, build_enrichment_plan  # noqa: E402
from homepilot_enrichment_refresh import build_enrichment_refresh_pack  # noqa: E402
from homepilot_entitlements import filter_payload_for_entitlements  # noqa: E402
from homepilot_export import build_export_bundle  # noqa: E402
from homepilot_fixture_cleanup import build_fixture_cleanup_plan  # noqa: E402
from homepilot_first_campaign_import_plan import build_first_campaign_import_plan  # noqa: E402
from homepilot_first_campaign_input_validation import build_first_campaign_input_validation  # noqa: E402
from homepilot_first_wave_launch_gate import build_first_wave_launch_gate  # noqa: E402
from homepilot_healthcheck import build_healthcheck_report, check_env_template  # noqa: E402
from homepilot_hosting import build_hosting_pack  # noqa: E402
from homepilot_integration_sync import build_integration_sync_pack  # noqa: E402
from homepilot_integrations import build_integration_pack  # noqa: E402
from homepilot_intelligence_lab import build_intelligence_lab_pack  # noqa: E402
from homepilot_launch import SupabaseAuthAdmin, run_live_rls_launch  # noqa: E402
from homepilot_lead_autoresearch import build_lead_autoresearch_pack, build_lead_priority_recommendation  # noqa: E402
from homepilot_live_fixture import build_live_fixture, build_module_payload  # noqa: E402
from homepilot_live_launch_request import build_live_launch_request_pack  # noqa: E402
from homepilot_live_credential_handoff import build_live_credential_handoff_pack  # noqa: E402
from homepilot_live_portal_pack import build_live_portal  # noqa: E402
from homepilot_live_proof_evidence_vault import build_live_proof_evidence_vault_pack  # noqa: E402
from homepilot_live_proof_plan import build_live_proof_plan_pack  # noqa: E402
from homepilot_live_readiness import build_live_readiness_report  # noqa: E402
from homepilot_live_schema_verification import (  # noqa: E402
    EXPECTED_FUNCTIONS,
    EXPECTED_POLICIES,
    EXPECTED_TABLE_COLUMNS,
    EXPECTED_VIEW_COLUMNS,
    build_schema_verification_report,
    evaluate_live_metadata,
)
from homepilot_metric_access import build_product_access_matrix, filter_metrics_for_surface  # noqa: E402
from homepilot_message_strategy_autoresearch import build_message_strategy_autoresearch_pack  # noqa: E402
from homepilot_market_readiness import build_market_readiness_pack  # noqa: E402
from homepilot_module_readiness_matrix import build_module_readiness_matrix_pack  # noqa: E402
from homepilot_customer_view_catalog import build_customer_view_catalog_pack  # noqa: E402
from homepilot_monitoring import build_monitoring_pack  # noqa: E402
from homepilot_onboarding import build_onboarding_payload, summarize_onboarding_payload  # noqa: E402
from homepilot_open_intelligence import build_open_intelligence, build_open_intelligence_pack  # noqa: E402
from homepilot_outcome_import_validation import build_outcome_import_validation_pack  # noqa: E402
from homepilot_outcome_measurement_contract import build_outcome_measurement_contract_pack  # noqa: E402
from homepilot_partner_cutdown import build_partner_cutdown_pack, filter_payload_for_partner  # noqa: E402
from homepilot_partner_assignment_autoresearch import build_partner_assignment_autoresearch_pack  # noqa: E402
from homepilot_partner_access_reconciliation import build_partner_access_reconciliation_pack  # noqa: E402
from homepilot_partner_auth_mapping import build_partner_auth_mapping_pack  # noqa: E402
from homepilot_customer_signoff_reconciliation import build_customer_signoff_reconciliation_pack  # noqa: E402
from homepilot_public_data_reconciliation import build_public_data_reconciliation_pack  # noqa: E402
from homepilot_opportunity_dossier import build_opportunity_dossier, build_opportunity_dossier_pack  # noqa: E402
from homepilot_ops_status import build_ops_status_pack  # noqa: E402
from homepilot_preflight import build_preflight_report  # noqa: E402
from homepilot_pilot_csv import convert_pilot_csv  # noqa: E402
from homepilot_platform import PILOT_MODULES, canonical_campaign_id, canonical_tenant_id  # noqa: E402
from homepilot_portal import build_portal_bundle  # noqa: E402
from homepilot_production_cutover import build_production_cutover  # noqa: E402
from homepilot_production_proof import build_production_proof_pack  # noqa: E402
from homepilot_processing_register import build_processing_register, build_processing_register_pack  # noqa: E402
from homepilot_privacy import build_export_log_record, build_property_delete_plan  # noqa: E402
from homepilot_readiness import build_readiness_pack  # noqa: E402
from homepilot_recovery import build_backup_manifest, build_import_rollback_plan, build_recovery_pack  # noqa: E402
from homepilot_release_audit import build_release_audit  # noqa: E402
from homepilot_release_pack import build_release_evidence_bundle  # noqa: E402
from homepilot_responses import merge_response_rows  # noqa: E402
from homepilot_retention import build_retention_report  # noqa: E402
from homepilot_rls_probe import ProbeEndpoint, evaluate_rows, load_probe_config, probe_identity, write_template  # noqa: E402
from homepilot_roi_forecast import build_roi_forecast, build_roi_forecast_pack  # noqa: E402
from homepilot_snapshot import build_dashboard_snapshot, write_dashboard_js  # noqa: E402
from homepilot_source_ledger import build_source_ledger, build_source_ledger_pack  # noqa: E402
from homepilot_sql_apply_plan import build_sql_apply_plan_pack  # noqa: E402
from homepilot_store import validate_payload  # noqa: E402
from homepilot_territory_plan import build_territory_plan, build_territory_plan_pack  # noqa: E402
from homepilot_visual_intelligence import build_visual_intelligence_pack, build_visual_scale_fixture  # noqa: E402


def base_payload() -> dict:
    tenant_id = canonical_tenant_id("tenant_a")
    facade_campaign = canonical_campaign_id(tenant_id, "facadepilot", "camp_facade")
    window_campaign = canonical_campaign_id(tenant_id, "windowpilot", "camp_window")
    return {
        "campaigns": [
            {"id": facade_campaign, "tenant_id": tenant_id, "name": "Facade campaign", "module_key": "facadepilot"},
            {"id": window_campaign, "tenant_id": tenant_id, "name": "Window campaign", "module_key": "windowpilot"},
        ],
        "properties": [
            {
                "id": "prop_1",
                "tenant_id": tenant_id,
                "address": "Teststraat 1",
                "city": "Leuven",
                "lat": 50.88,
                "lon": 4.7,
                "property_type": "halfopen",
                "tags": ["pre-1990"],
                "core": {},
            }
        ],
        "assessments": [
            {
                "id": "asmt_facade",
                "tenant_id": tenant_id,
                "property_id": "prop_1",
                "module_key": "facadepilot",
                "score": 82,
                "grade": "A+",
                "confidence": 0.86,
                "metrics": {"facade_preset": "Crepi insulation", "median_income": 42000},
                "evidence": [{"type": "streetview", "value": "street.jpg"}],
            },
            {
                "id": "asmt_window",
                "tenant_id": tenant_id,
                "property_id": "prop_1",
                "module_key": "windowpilot",
                "score": 91,
                "grade": "A+",
                "confidence": 0.81,
                "metrics": {"replacement_urgency": "Old glazing", "estimated_value": 36000},
                "evidence": [{"type": "render", "value": "window.jpg"}],
            },
        ],
        "campaign_targets": [
            {
                "tenant_id": tenant_id,
                "campaign_id": facade_campaign,
                "property_id": "prop_1",
                "module_key": "facadepilot",
                "status": "sent",
                "priority_score": 82,
                "priority_grade": "A+",
                "metadata": {"objections": ["too expensive"]},
            },
            {
                "tenant_id": tenant_id,
                "campaign_id": window_campaign,
                "property_id": "prop_1",
                "module_key": "windowpilot",
                "status": "responded",
                "priority_score": 91,
                "priority_grade": "A+",
                "metadata": {"next_action": "Call about glazing"},
            },
        ],
        "interactions": [
            {
                "tenant_id": tenant_id,
                "property_id": "prop_1",
                "campaign_id": facade_campaign,
                "module_key": "facadepilot",
                "interaction_type": "flyer_sent",
                "response_status": "none",
                "detail": "Facade flyer sent",
                "occurred_at": "2026-06-01T10:00:00Z",
            },
            {
                "tenant_id": tenant_id,
                "property_id": "prop_1",
                "campaign_id": window_campaign,
                "module_key": "windowpilot",
                "interaction_type": "call",
                "response_status": "interested",
                "detail": "Asked about window price",
                "occurred_at": "2026-06-02T10:00:00Z",
            },
        ],
    }


class PlatformContractTests(unittest.TestCase):

    def _write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})

    def _customer_input_template_pack(self) -> dict:
        templates = [
            {
                "key": "partner_roster_template",
                "file_name": "PARTNER_ROSTER_TEMPLATE.csv",
                "fields": [
                    "partner_id",
                    "partner_name",
                    "legal_company_name",
                    "region",
                    "cities_or_postcodes",
                    "language",
                    "capacity_per_month",
                    "service_categories",
                    "primary_contact_name",
                    "primary_contact_email_or_secret_channel_ref",
                    "portal_role",
                    "escalation_owner",
                    "partner_scope_notes",
                    "status",
                ],
            },
            {
                "key": "territory_assignment_template",
                "file_name": "TERRITORY_ASSIGNMENT_TEMPLATE.csv",
                "fields": [
                    "partner_id",
                    "region",
                    "cities_or_postcodes",
                    "included_postcodes",
                    "excluded_postcodes",
                    "capacity_cap",
                    "overlap_rule",
                    "fallback_owner",
                    "assignment_priority",
                    "notes",
                    "status",
                ],
            },
            {
                "key": "property_source_template",
                "file_name": "PROPERTY_SOURCE_TEMPLATE.csv",
                "fields": [
                    "source_file_name",
                    "source_owner",
                    "tenant_id",
                    "module_key",
                    "allowed_modules",
                    "address_column",
                    "postcode_column",
                    "city_column",
                    "source_provenance",
                    "refresh_date",
                    "dedupe_rule",
                    "public_data_used",
                    "contact_basis_source",
                    "import_status",
                ],
            },
            {
                "key": "suppression_list_template",
                "file_name": "SUPPRESSION_LIST_TEMPLATE.csv",
                "fields": [
                    "suppression_id",
                    "source_owner",
                    "match_type",
                    "property_or_hash_reference",
                    "postcode",
                    "city",
                    "module_key",
                    "reason",
                    "opt_out_method",
                    "effective_from",
                    "delete_after",
                    "notes",
                ],
            },
            {
                "key": "message_approval_template",
                "file_name": "MESSAGE_APPROVAL_TEMPLATE.csv",
                "fields": [
                    "message_variant",
                    "language",
                    "module_key",
                    "channel",
                    "partner_branding_allowed",
                    "claim_summary",
                    "prohibited_claims_checked",
                    "cta",
                    "opt_out_wording",
                    "marketing_owner",
                    "legal_owner",
                    "approval_status",
                    "approved_at",
                    "notes",
                ],
            },
            {
                "key": "partner_capacity_template",
                "file_name": "PARTNER_CAPACITY_TEMPLATE.csv",
                "fields": [
                    "partner_id",
                    "capacity_per_month",
                    "appointment_slots_per_week",
                    "response_sla_hours",
                    "accepted_statuses",
                    "rejection_reasons_allowed",
                    "feedback_cadence",
                    "escalation_owner",
                    "capacity_status",
                    "notes",
                ],
            },
        ]
        return {"pack_type": "homepilot_customer_input_template_pack", "templates": templates}

    def _write_complete_customer_input_files(self, inputs: Path, template_pack: dict) -> list[str]:
        template_fields = {template["file_name"]: template["fields"] for template in template_pack["templates"]}
        partner_ids = [f"partner-{index:02d}" for index in range(1, 11)]
        self._write_csv(
            inputs / "PARTNER_ROSTER_TEMPLATE.csv",
            template_fields["PARTNER_ROSTER_TEMPLATE.csv"],
            [
                {
                    "partner_id": partner_id,
                    "partner_name": f"DAW Renovator {index:02d}",
                    "legal_company_name": f"DAW Renovator {index:02d} BV",
                    "region": "Flanders",
                    "cities_or_postcodes": f"{2000 + index}",
                    "language": "nl",
                    "capacity_per_month": "120",
                    "service_categories": "facade insulation; crepi",
                    "primary_contact_name": "secure_channel_reference_only",
                    "primary_contact_email_or_secret_channel_ref": f"secret://daw/partner/{partner_id}/contact",
                    "portal_role": "partner_renovator",
                    "escalation_owner": "DAW partner manager",
                    "partner_scope_notes": "assigned_records_only",
                    "status": "confirmed",
                }
                for index, partner_id in enumerate(partner_ids, start=1)
            ],
        )
        self._write_csv(
            inputs / "TERRITORY_ASSIGNMENT_TEMPLATE.csv",
            template_fields["TERRITORY_ASSIGNMENT_TEMPLATE.csv"],
            [
                {
                    "partner_id": partner_id,
                    "region": "Flanders",
                    "cities_or_postcodes": f"City {index:02d}",
                    "included_postcodes": str(2000 + index),
                    "excluded_postcodes": "",
                    "capacity_cap": "120",
                    "overlap_rule": "nearest_partner_then_capacity",
                    "fallback_owner": "DAW network manager",
                    "assignment_priority": str(index),
                    "notes": "approved first wave territory",
                    "status": "approved",
                }
                for index, partner_id in enumerate(partner_ids, start=1)
            ],
        )
        self._write_csv(
            inputs / "PROPERTY_SOURCE_TEMPLATE.csv",
            template_fields["PROPERTY_SOURCE_TEMPLATE.csv"],
            [{
                "source_file_name": "daw_facadepilot_wave1_properties.csv",
                "source_owner": "DAW data owner",
                "tenant_id": "daw-belgium",
                "module_key": "facadepilot",
                "allowed_modules": "facadepilot",
                "address_column": "address",
                "postcode_column": "postcode",
                "city_column": "city",
                "source_provenance": "customer-approved property list",
                "refresh_date": "2026-07-01",
                "dedupe_rule": "normalized_address_postcode_city",
                "public_data_used": "none_until_approved",
                "contact_basis_source": "approved legal review",
                "import_status": "ready_for_import",
            }],
        )
        self._write_csv(
            inputs / "SUPPRESSION_LIST_TEMPLATE.csv",
            template_fields["SUPPRESSION_LIST_TEMPLATE.csv"],
            [{
                "suppression_id": "sup-001",
                "source_owner": "DAW legal/privacy owner",
                "match_type": "property_id_or_hash",
                "property_or_hash_reference": "hash-or-property-id-001",
                "postcode": "2000",
                "city": "Antwerpen",
                "module_key": "facadepilot",
                "reason": "do_not_contact",
                "opt_out_method": "customer suppression workflow",
                "effective_from": "2026-07-01",
                "delete_after": "2027-07-01",
                "notes": "hash-only suppression evidence",
            }],
        )
        self._write_csv(
            inputs / "MESSAGE_APPROVAL_TEMPLATE.csv",
            template_fields["MESSAGE_APPROVAL_TEMPLATE.csv"],
            [{
                "message_variant": "energy_savings",
                "language": "nl",
                "module_key": "facadepilot",
                "channel": "direct_mail",
                "partner_branding_allowed": "yes_after_partner_approval",
                "claim_summary": "opportunity for facade insulation review",
                "prohibited_claims_checked": "no homeowner intent; no guaranteed savings",
                "cta": "book consult or request more info",
                "opt_out_wording": "customer-approved opt-out text",
                "marketing_owner": "DAW marketing owner",
                "legal_owner": "DAW legal/privacy owner",
                "approval_status": "approved",
                "approved_at": "2026-07-01T09:00:00Z",
                "notes": "opportunity language only",
            }],
        )
        self._write_csv(
            inputs / "PARTNER_CAPACITY_TEMPLATE.csv",
            template_fields["PARTNER_CAPACITY_TEMPLATE.csv"],
            [
                {
                    "partner_id": partner_id,
                    "capacity_per_month": "120",
                    "appointment_slots_per_week": "8",
                    "response_sla_hours": "24",
                    "accepted_statuses": "responded; appointment; customer",
                    "rejection_reasons_allowed": "out_of_area; no_capacity; duplicate; customer_unreachable",
                    "feedback_cadence": "weekly",
                    "escalation_owner": "DAW partner manager",
                    "capacity_status": "confirmed",
                    "notes": "first wave capacity confirmed",
                }
                for partner_id in partner_ids
            ],
        )
        return partner_ids

    def test_first_campaign_input_validation_marks_complete_inputs_blocked_until_live_proof(self) -> None:
        template_pack = self._customer_input_template_pack()
        template_fields = {template["file_name"]: template["fields"] for template in template_pack["templates"]}
        partner_ids = [f"partner-{index:02d}" for index in range(1, 11)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            self._write_csv(
                inputs / "PARTNER_ROSTER_TEMPLATE.csv",
                template_fields["PARTNER_ROSTER_TEMPLATE.csv"],
                [
                    {
                        "partner_id": partner_id,
                        "partner_name": f"DAW Renovator {index:02d}",
                        "legal_company_name": f"DAW Renovator {index:02d} BV",
                        "region": "Flanders",
                        "cities_or_postcodes": f"{2000 + index}",
                        "language": "nl",
                        "capacity_per_month": "120",
                        "service_categories": "facade insulation; crepi",
                        "primary_contact_name": "secure_channel_reference_only",
                        "primary_contact_email_or_secret_channel_ref": f"secret://daw/partner/{partner_id}/contact",
                        "portal_role": "partner_renovator",
                        "escalation_owner": "DAW partner manager",
                        "partner_scope_notes": "assigned_records_only",
                        "status": "confirmed",
                    }
                    for index, partner_id in enumerate(partner_ids, start=1)
                ],
            )
            self._write_csv(
                inputs / "TERRITORY_ASSIGNMENT_TEMPLATE.csv",
                template_fields["TERRITORY_ASSIGNMENT_TEMPLATE.csv"],
                [
                    {
                        "partner_id": partner_id,
                        "region": "Flanders",
                        "cities_or_postcodes": f"City {index:02d}",
                        "included_postcodes": str(2000 + index),
                        "excluded_postcodes": "",
                        "capacity_cap": "120",
                        "overlap_rule": "nearest_partner_then_capacity",
                        "fallback_owner": "DAW network manager",
                        "assignment_priority": str(index),
                        "notes": "approved first wave territory",
                        "status": "approved",
                    }
                    for index, partner_id in enumerate(partner_ids, start=1)
                ],
            )
            self._write_csv(
                inputs / "PROPERTY_SOURCE_TEMPLATE.csv",
                template_fields["PROPERTY_SOURCE_TEMPLATE.csv"],
                [{
                    "source_file_name": "daw_facadepilot_wave1_properties.csv",
                    "source_owner": "DAW data owner",
                    "tenant_id": "daw-belgium",
                    "module_key": "facadepilot",
                    "allowed_modules": "facadepilot",
                    "address_column": "address",
                    "postcode_column": "postcode",
                    "city_column": "city",
                    "source_provenance": "customer-approved property list",
                    "refresh_date": "2026-07-01",
                    "dedupe_rule": "normalized_address_postcode_city",
                    "public_data_used": "none_until_approved",
                    "contact_basis_source": "approved legal review",
                    "import_status": "ready_for_import",
                }],
            )
            self._write_csv(
                inputs / "SUPPRESSION_LIST_TEMPLATE.csv",
                template_fields["SUPPRESSION_LIST_TEMPLATE.csv"],
                [{
                    "suppression_id": "sup-001",
                    "source_owner": "DAW legal/privacy owner",
                    "match_type": "property_id_or_hash",
                    "property_or_hash_reference": "hash-or-property-id-001",
                    "postcode": "2000",
                    "city": "Antwerpen",
                    "module_key": "facadepilot",
                    "reason": "do_not_contact",
                    "opt_out_method": "customer suppression workflow",
                    "effective_from": "2026-07-01",
                    "delete_after": "2027-07-01",
                    "notes": "hash-only suppression evidence",
                }],
            )
            self._write_csv(
                inputs / "MESSAGE_APPROVAL_TEMPLATE.csv",
                template_fields["MESSAGE_APPROVAL_TEMPLATE.csv"],
                [{
                    "message_variant": "energy_savings",
                    "language": "nl",
                    "module_key": "facadepilot",
                    "channel": "direct_mail",
                    "partner_branding_allowed": "yes_after_partner_approval",
                    "claim_summary": "opportunity for facade insulation review",
                    "prohibited_claims_checked": "no homeowner intent; no guaranteed savings",
                    "cta": "book consult or request more info",
                    "opt_out_wording": "customer-approved opt-out text",
                    "marketing_owner": "DAW marketing owner",
                    "legal_owner": "DAW legal/privacy owner",
                    "approval_status": "approved",
                    "approved_at": "2026-07-01T09:00:00Z",
                    "notes": "opportunity language only",
                }],
            )
            self._write_csv(
                inputs / "PARTNER_CAPACITY_TEMPLATE.csv",
                template_fields["PARTNER_CAPACITY_TEMPLATE.csv"],
                [
                    {
                        "partner_id": partner_id,
                        "capacity_per_month": "120",
                        "appointment_slots_per_week": "8",
                        "response_sla_hours": "24",
                        "accepted_statuses": "responded; appointment; customer",
                        "rejection_reasons_allowed": "out_of_area; no_capacity; duplicate; customer_unreachable",
                        "feedback_cadence": "weekly",
                        "escalation_owner": "DAW partner manager",
                        "capacity_status": "confirmed",
                        "notes": "first wave capacity confirmed",
                    }
                    for partner_id in partner_ids
                ],
            )

            report = build_first_campaign_input_validation(
                out_dir=root / "validation",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="validation-test",
                expected_partner_count=10,
                live_proof_ready=False,
            )
            markdown = (root / "validation" / "FIRST_CAMPAIGN_INPUT_VALIDATION.md").read_text(encoding="utf-8")
            issues_csv = (root / "validation" / "FIRST_CAMPAIGN_INPUT_ISSUES.csv").read_text(encoding="utf-8")

        gates = {gate["key"]: gate for gate in report["gates"]}
        self.assertEqual(report["status"], "customer_inputs_ready")
        self.assertEqual(report["first_wave_decision"], "blocked_until_live_proof")
        self.assertEqual(report["summary"]["partner_count"], 10)
        self.assertEqual(report["summary"]["blockers"], 1)
        self.assertEqual(gates["customer_inputs_complete"]["status"], "pass")
        self.assertEqual(gates["partner_scope_ready"]["status"], "pass")
        self.assertEqual(gates["contact_basis_and_suppression"]["status"], "pass")
        self.assertEqual(gates["message_and_claim_approval"]["status"], "pass")
        self.assertEqual(gates["partner_capacity_confirmed"]["status"], "pass")
        self.assertEqual(gates["live_access_proof"]["status"], "blocked")
        self.assertIn("blocked_until_live_proof", markdown)
        self.assertIn("live_proof_missing", issues_csv)

    def test_first_campaign_import_plan_stages_partner_campaigns_without_live_writes(self) -> None:
        template_pack = self._customer_input_template_pack()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            self._write_complete_customer_input_files(inputs, template_pack)
            validation = build_first_campaign_input_validation(
                out_dir=root / "validation",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="import-plan-test",
                expected_partner_count=10,
                live_proof_ready=False,
            )
            plan = build_first_campaign_import_plan(
                out_dir=root / "plan",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="import-plan-test",
                expected_partner_count=10,
                live_proof_ready=False,
                validation_report=validation,
            )
            live_plan = build_first_campaign_import_plan(
                out_dir=root / "live-plan",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="import-plan-test",
                expected_partner_count=10,
                live_proof_ready=True,
            )
            markdown = (root / "plan" / "FIRST_CAMPAIGN_IMPORT_PLAN.md").read_text(encoding="utf-8")
            staging_rows = (root / "plan" / "FIRST_CAMPAIGN_STAGING_ROWS.csv").read_text(encoding="utf-8")
            plan_text = (root / "plan" / "first_campaign_import_plan.json").read_text(encoding="utf-8")

        self.assertEqual(plan["status"], "staging_plan_ready_import_blocked")
        self.assertEqual(plan["import_decision"], "blocked_until_live_proof")
        self.assertEqual(plan["first_wave_decision"], "blocked_until_live_proof")
        self.assertEqual(plan["summary"]["partner_scope_records"], 10)
        self.assertEqual(plan["summary"]["campaign_records"], 10)
        self.assertEqual(plan["summary"]["property_source_runs"], 1)
        self.assertFalse(plan["summary"]["raw_contact_values_written"])
        self.assertFalse(plan["summary"]["secret_values_written"])
        self.assertTrue(plan["guardrails"]["non_mutating_plan"])
        self.assertTrue(plan["guardrails"]["no_database_writes"])
        self.assertIn("homepilot_campaigns", plan["database_contract"]["planned_tables"])
        self.assertIn("homepilot_campaign_targets", plan["database_contract"]["deferred_until_property_file_parse"])
        self.assertEqual(plan["property_source_runs"][0]["refresh_date"], "2026-07-01")
        self.assertEqual(plan["campaign_records"][0]["module_key"], "facadepilot")
        self.assertEqual(plan["campaign_records"][0]["status"], "planned_review")
        self.assertEqual(plan["partner_scope_records"][0]["contact_reference_status"], "secret_reference_present")
        uuid.UUID(plan["campaign_records"][0]["campaign_id_candidate"])
        self.assertIn("HomePilot First Campaign Import Plan", markdown)
        self.assertIn("This plan does not write to Supabase", markdown)
        self.assertIn("homepilot_campaigns", staging_rows)
        self.assertIn("blocked_until_live_proof", staging_rows)
        self.assertNotIn("secret://daw", plan_text)
        self.assertNotIn("@", plan_text)
        self.assertEqual(live_plan["status"], "ready_for_live_import_review")
        self.assertEqual(live_plan["first_wave_decision"], "ready_for_first_wave_review")

    def test_first_wave_launch_gate_blocks_until_live_proof_and_customer_go(self) -> None:
        template_pack = self._customer_input_template_pack()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            self._write_complete_customer_input_files(inputs, template_pack)
            validation = build_first_campaign_input_validation(
                out_dir=root / "validation",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="launch-gate-test",
                expected_partner_count=10,
                live_proof_ready=False,
            )
            import_plan = build_first_campaign_import_plan(
                out_dir=root / "plan",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="launch-gate-test",
                expected_partner_count=10,
                live_proof_ready=False,
                validation_report=validation,
            )
            gate = build_first_wave_launch_gate(
                out_dir=root / "gate",
                input_validation=validation,
                import_plan=import_plan,
                live_readiness={"status": "action_required"},
                release_label="launch-gate-test",
                customer_go_no_go_ready=False,
            )
            live_validation = build_first_campaign_input_validation(
                out_dir=root / "live-validation",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="launch-gate-test",
                expected_partner_count=10,
                live_proof_ready=True,
            )
            live_import_plan = build_first_campaign_import_plan(
                out_dir=root / "live-plan",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="launch-gate-test",
                expected_partner_count=10,
                live_proof_ready=True,
                validation_report=live_validation,
            )
            ready_gate = build_first_wave_launch_gate(
                out_dir=root / "ready-gate",
                input_validation=live_validation,
                import_plan=live_import_plan,
                live_readiness={"status": "ready"},
                schema_verification={"production_verified": True, "status": "pass"},
                launch_report={"production_verified": True, "status": "pass"},
                customer_access_report={"production_verified": True, "status": "pass"},
                release_label="launch-gate-test",
                customer_go_no_go_ready=True,
                customer_go_no_go_reference="signed://daw/first-wave-go",
            )
            markdown = (root / "gate" / "FIRST_WAVE_LAUNCH_GATE.md").read_text(encoding="utf-8")
            checklist = (root / "gate" / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv").read_text(encoding="utf-8")

        gate_by_key = {row["key"]: row for row in gate["gates"]}
        ready_by_key = {row["key"]: row for row in ready_gate["gates"]}
        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["launch_decision"], "blocked_until_live_proof_and_customer_go_no_go")
        self.assertFalse(gate["launch_authorized"])
        self.assertEqual(gate["summary"]["campaign_records"], 10)
        self.assertEqual(gate["summary"]["staging_rows"], 23)
        self.assertTrue(gate["guardrails"]["non_mutating_gate"])
        self.assertTrue(gate["guardrails"]["no_outreach_without_launch_authorized"])
        self.assertEqual(gate_by_key["customer_inputs"]["status"], "pass")
        self.assertEqual(gate_by_key["staging_plan"]["status"], "pass")
        self.assertEqual(gate_by_key["source_suppression_message"]["status"], "pass")
        self.assertEqual(gate_by_key["public_data_approval"]["status"], "pass")
        self.assertFalse(gate_by_key["public_data_approval"]["blocks_launch"])
        self.assertEqual(gate_by_key["live_proof"]["status"], "blocked")
        self.assertEqual(gate_by_key["customer_go_no_go"]["status"], "blocked")
        self.assertIn("HomePilot First Wave Launch Gate", markdown)
        self.assertIn("blocked_until_live_proof_and_customer_go_no_go", markdown)
        self.assertIn("customer_go_no_go", checklist)
        self.assertEqual(ready_gate["status"], "ready")
        self.assertEqual(ready_gate["launch_decision"], "ready_for_first_wave_launch")
        self.assertTrue(ready_gate["launch_authorized"])
        self.assertTrue(all(row["status"] == "pass" for row in ready_gate["gates"]))
        self.assertEqual(ready_by_key["customer_go_no_go"]["evidence"], "signed://daw/first-wave-go")

    def test_partner_auth_mapping_requires_real_auth_users_before_memberships(self) -> None:
        template_pack = self._customer_input_template_pack()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            self._write_complete_customer_input_files(inputs, template_pack)
            validation = build_first_campaign_input_validation(
                out_dir=root / "validation",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="partner-auth-test",
                expected_partner_count=10,
                live_proof_ready=False,
            )
            import_plan = build_first_campaign_import_plan(
                out_dir=root / "plan",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="partner-auth-test",
                expected_partner_count=10,
                live_proof_ready=False,
                validation_report=validation,
            )
            gate = build_first_wave_launch_gate(
                out_dir=root / "gate",
                input_validation=validation,
                import_plan=import_plan,
                live_readiness={"status": "action_required"},
                release_label="partner-auth-test",
                customer_go_no_go_ready=False,
            )
            mapping_required = build_partner_auth_mapping_pack(
                out_dir=root / "mapping-required",
                import_plan=import_plan,
                launch_gate=gate,
                release_label="partner-auth-test",
                expected_partner_count=10,
            )
            live_validation = build_first_campaign_input_validation(
                out_dir=root / "live-validation",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="partner-auth-test",
                expected_partner_count=10,
                live_proof_ready=True,
            )
            live_import_plan = build_first_campaign_import_plan(
                out_dir=root / "live-plan",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="partner-auth-test",
                expected_partner_count=10,
                live_proof_ready=True,
                validation_report=live_validation,
            )
            ready_gate = build_first_wave_launch_gate(
                out_dir=root / "ready-gate",
                input_validation=live_validation,
                import_plan=live_import_plan,
                live_readiness={"status": "ready"},
                schema_verification={"production_verified": True, "status": "pass"},
                launch_report={"production_verified": True, "status": "pass"},
                customer_access_report={"production_verified": True, "status": "pass"},
                release_label="partner-auth-test",
                customer_go_no_go_ready=True,
                customer_go_no_go_reference="signed://daw/first-wave-go",
            )
            mapping_csv = root / "partner_auth_mapping_completed.csv"
            self._write_csv(
                mapping_csv,
                ["partner_id", "partner_name", "role", "supabase_user_id", "auth_email_ref", "mapping_status", "notes"],
                [
                    {
                        "partner_id": partner["partner_id"],
                        "partner_name": partner["partner_name"],
                        "role": "partner_renovator",
                        "supabase_user_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"homepilot:{partner['partner_id']}")),
                        "auth_email_ref": f"secret://daw/auth/{partner['partner_id']}",
                        "mapping_status": "customer_it_confirmed",
                        "notes": "synthetic test mapping",
                    }
                    for partner in live_import_plan["partner_scope_records"]
                ],
            )
            ready_mapping = build_partner_auth_mapping_pack(
                out_dir=root / "mapping-ready",
                import_plan=live_import_plan,
                launch_gate=ready_gate,
                mapping_csv_path=mapping_csv,
                release_label="partner-auth-test",
                expected_partner_count=10,
            )
            required_markdown = (root / "mapping-required" / "PARTNER_AUTH_MAPPING.md").read_text(encoding="utf-8")
            required_template = (root / "mapping-required" / "PARTNER_AUTH_MAPPING_TEMPLATE.csv").read_text(encoding="utf-8")
            required_issues = (root / "mapping-required" / "PARTNER_AUTH_MAPPING_ISSUES.csv").read_text(encoding="utf-8")
            required_sql = (root / "mapping-required" / "PARTNER_MEMBERSHIP_REVIEW.sql").read_text(encoding="utf-8")
            ready_sql = (root / "mapping-ready" / "PARTNER_MEMBERSHIP_REVIEW.sql").read_text(encoding="utf-8")

        self.assertEqual(mapping_required["status"], "mapping_required")
        self.assertEqual(mapping_required["sql_mode"], "comment_only_mapping_required")
        self.assertEqual(mapping_required["summary"]["expected_partner_count"], 10)
        self.assertEqual(mapping_required["summary"]["mapped_partner_count"], 0)
        self.assertEqual(mapping_required["summary"]["executable_statement_count"], 0)
        self.assertTrue(mapping_required["guardrails"]["non_mutating_pack"])
        self.assertTrue(mapping_required["guardrails"]["launch_authorized_required_before_membership_sql"])
        self.assertFalse(mapping_required["guardrails"]["raw_contact_values_written"])
        self.assertIn("HomePilot Partner Auth Mapping", required_markdown)
        self.assertIn("supabase_user_id", required_template)
        self.assertIn("supabase_user_id_missing", required_issues)
        self.assertIn("No executable membership SQL is generated", required_sql)
        self.assertNotIn("insert into public.homepilot_memberships", required_sql.lower())
        self.assertEqual(ready_mapping["status"], "ready_for_membership_sql_review")
        self.assertEqual(ready_mapping["summary"]["mapped_partner_count"], 10)
        self.assertGreater(ready_mapping["summary"]["executable_statement_count"], 0)
        self.assertIn("insert into public.homepilot_memberships", ready_sql.lower())
        self.assertNotIn("@", json.dumps(ready_mapping))

    def test_partner_access_reconciliation_requires_mapping_membership_and_customer_probe_alignment(self) -> None:
        tenant_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        partners = [
            ("renotec-antwerp", str(uuid.uuid5(uuid.NAMESPACE_URL, "homepilot:renotec-antwerp"))),
            ("crepi-limburg", str(uuid.uuid5(uuid.NAMESPACE_URL, "homepilot:crepi-limburg"))),
        ]
        partner_auth_mapping = {
            "status": "ready_for_membership_sql_review",
            "summary": {
                "expected_partner_count": 2,
                "mapped_partner_count": 2,
                "blockers": 0,
                "executable_statement_count": 2,
            },
            "expected_partners": [
                {"partner_id": partner_id, "partner_name": partner_id.replace("-", " ").title(), "source": "test"}
                for partner_id, _ in partners
            ],
            "mapping_rows": [
                {
                    "partner_id": partner_id,
                    "partner_name": partner_id.replace("-", " ").title(),
                    "supabase_user_id": user_id,
                    "uuid_status": "valid",
                }
                for partner_id, user_id in partners
            ],
        }
        account_access_plan = {
            "status": "pass",
            "review_status": "ready",
            "membership_rows": [
                {"tenant_id": tenant_id, "user_id": user_id, "role": "manager", "partner_id": partner_id}
                for partner_id, user_id in partners
            ],
        }
        customer_access = {
            "status": "pass",
            "production_verified": True,
            "identities": [
                {
                    "label": partner_id.replace("-", "_"),
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "role": "manager",
                    "access_scope": "partner",
                    "partner_id": partner_id,
                    "modules": ["facadepilot"],
                }
                for partner_id, user_id in partners
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = build_partner_access_reconciliation_pack(
                Path(tmp),
                partner_auth_mapping=partner_auth_mapping,
                account_access_plan=account_access_plan,
                customer_access_verification=customer_access,
                release_label="partner-reconcile-test",
            )
            markdown = Path(report["paths"]["partner_access_reconciliation_markdown"]).read_text(encoding="utf-8")
            matrix = Path(report["paths"]["partner_access_reconciliation_matrix"]).read_text(encoding="utf-8")
            issues = Path(report["paths"]["partner_access_reconciliation_issues"]).read_text(encoding="utf-8")

        self.assertEqual(report["status"], "partner_access_reconciled")
        self.assertTrue(report["production_ready"])
        self.assertEqual(report["summary"]["fully_reconciled_partner_count"], 2)
        self.assertEqual(report["summary"]["blockers"], 0)
        self.assertTrue(report["guardrails"]["no_supabase_writes"])
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Partner Access Reconciliation", markdown)
        self.assertIn("renotec-antwerp", matrix)
        self.assertIn("matched", matrix)
        self.assertIn("issue_key", issues)
        self.assertNotIn("@example.com", json.dumps(report).lower() + markdown.lower() + matrix.lower())

    def test_public_data_reconciliation_blocks_import_without_dataset_approvals_or_live_proof(self) -> None:
        public_register = {
            "status": "buyer_review_public_data_ready",
            "sources": [
                {
                    "source": "BeSt Addresses",
                    "publisher": "FPS BOSA",
                    "recommended_status": "approved_for_review",
                    "licence_or_terms": "CC BY 4.0",
                },
                {
                    "source": "OpenStreetMap",
                    "publisher": "OpenStreetMap contributors",
                    "recommended_status": "legal_review_required",
                    "licence_or_terms": "ODbL",
                },
            ],
        }
        public_data_intake = {
            "status": "approval_required",
            "production_import_decision": "blocked_until_dataset_approvals_and_live_proof",
            "dataset_approvals": [
                {
                    "source": "BeSt Addresses",
                    "approval_status": "dataset_level_approval_required",
                    "production_import_decision": "do_not_import_yet",
                    "data_category": "official_address_reference",
                    "storage_target": "homepilot_source_runs; homepilot_geographies",
                },
                {
                    "source": "OpenStreetMap",
                    "approval_status": "legal_review_required",
                    "production_import_decision": "do_not_import_yet",
                    "data_category": "odbl_review_required",
                    "storage_target": "homepilot_source_runs; homepilot_public_features",
                },
            ],
        }
        import_plan = {
            "property_source_runs": [
                {"source_key": "daw-source", "public_data_used": "none_until_approved"}
            ]
        }
        first_wave_gate = {
            "summary": {"live_proof_ready": False},
            "gates": [
                {"key": "public_data_approval", "status": "pass", "blocks_launch": False}
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = build_public_data_reconciliation_pack(
                Path(tmp),
                public_register=public_register,
                public_data_intake=public_data_intake,
                first_campaign_import_plan=import_plan,
                first_wave_launch_gate=first_wave_gate,
                release_label="public-data-test",
            )
            markdown = Path(report["paths"]["public_data_reconciliation_markdown"]).read_text(encoding="utf-8")
            matrix = Path(report["paths"]["public_data_reconciliation_matrix"]).read_text(encoding="utf-8")
            issues = Path(report["paths"]["public_data_reconciliation_issues"]).read_text(encoding="utf-8")

        self.assertEqual(report["status"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertFalse(report["production_import_ready"])
        self.assertEqual(report["summary"]["registered_source_count"], 2)
        self.assertEqual(report["summary"]["approved_source_count"], 0)
        self.assertFalse(report["summary"]["first_wave_public_data_required"])
        self.assertEqual(report["summary"]["first_wave_public_data_gate_status"], "pass")
        self.assertTrue(report["guardrails"]["no_supabase_writes"])
        self.assertTrue(report["guardrails"]["public_data_separate_from_contact_basis"])
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Public Data Reconciliation", markdown)
        self.assertIn("BeSt Addresses", matrix)
        self.assertIn("OpenStreetMap", matrix)
        self.assertIn("public_data_import_not_approved", issues)
        self.assertIn("legal_review_required", issues)
        self.assertNotIn("@example.com", json.dumps(report).lower() + markdown.lower() + matrix.lower())

    def test_customer_signoff_reconciliation_separates_buyer_review_from_signed_launch_approval(self) -> None:
        blocked_inputs = {
            "customer_acceptance_plan": {"status": "buyer_review_ready"},
            "first_campaign_input_validation": {"status": "action_required", "summary": {"blockers": 3}},
            "first_campaign_import_plan": {
                "status": "blocked_until_customer_input_fixes",
                "summary": {"campaign_records": 1, "raw_contact_values_written": False, "secret_values_written": False},
            },
            "first_wave_launch_gate": {
                "status": "blocked",
                "launch_decision": "blocked_until_customer_inputs_and_staging_review",
                "launch_authorized": False,
                "summary": {"customer_go_no_go_ready": False, "live_proof_ready": False},
            },
            "customer_pilot_proposal": {"status": "buyer_review_proposal_ready"},
            "support_sla_plan": {"status": "buyer_review_support_ready"},
            "value_realization_plan": {"status": "buyer_review_value_ready"},
            "partner_access_reconciliation": {
                "status": "blocked_until_partner_auth_mapping",
                "production_ready": False,
                "summary": {"blockers": 2},
            },
            "public_data_reconciliation": {
                "status": "blocked_until_dataset_approvals_and_live_proof",
                "production_import_ready": False,
                "summary": {"blockers": 4, "first_wave_public_data_required": False, "first_wave_blocks": 0},
            },
            "production_proof": {"production_gate": {"verified": False}},
        }
        signed_inputs = {
            "customer_acceptance_plan": {"status": "accepted", "signoff_reference": "signed://daw/buyer-review"},
            "first_campaign_input_validation": {"status": "pass", "summary": {"blockers": 0}},
            "first_campaign_import_plan": {
                "status": "ready_for_live_import_review",
                "summary": {"campaign_records": 10, "raw_contact_values_written": False, "secret_values_written": False},
            },
            "first_wave_launch_gate": {
                "status": "ready",
                "launch_decision": "ready_for_first_wave_launch",
                "launch_authorized": True,
                "summary": {"customer_go_no_go_ready": True, "live_proof_ready": True},
            },
            "customer_pilot_proposal": {"status": "pilot_terms_signed", "signoff_reference": "signed://daw/pilot"},
            "support_sla_plan": {"status": "support_sla_signed", "signoff_reference": "signed://daw/support"},
            "value_realization_plan": {"status": "value_baseline_accepted", "signoff_reference": "signed://daw/value"},
            "partner_access_reconciliation": {
                "status": "partner_access_reconciled",
                "production_ready": True,
                "summary": {"blockers": 0},
            },
            "public_data_reconciliation": {
                "status": "public_data_reconciled_for_production_import",
                "production_import_ready": True,
                "summary": {"blockers": 0, "first_wave_public_data_required": False, "first_wave_blocks": 0},
            },
            "production_proof": {"production_gate": {"verified": True}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked = build_customer_signoff_reconciliation_pack(
                root / "blocked",
                release_label="signoff-test",
                **blocked_inputs,
            )
            evidence = build_customer_signoff_reconciliation_pack(
                root / "evidence",
                release_label="signoff-test",
                customer_signoff_evidence=[
                    {
                        "decision_key": "buyer_review_acceptance",
                        "signoff_status": "approved",
                        "signoff_reference": "signed://daw/buyer-review",
                        "signer_role": "Executive sponsor",
                        "signed_at": "2026-06-28",
                    },
                    {
                        "decision_key": "live_proof_archived",
                        "signoff_status": "approved",
                        "signoff_reference": "signed://daw/live-proof-override",
                        "signer_role": "Executive sponsor",
                        "signed_at": "2026-06-28",
                    },
                    {
                        "decision_key": "commercial_pilot_terms",
                        "signoff_status": "approved",
                        "signoff_reference": "customer_to_confirm",
                        "signer_role": "Procurement",
                        "signed_at": "2026-06-28",
                    },
                    {
                        "decision_key": "unknown_decision",
                        "signoff_status": "approved",
                        "signoff_reference": "signed://daw/unknown",
                        "signer_role": "Executive sponsor",
                        "signed_at": "2026-06-28",
                    },
                ],
                **blocked_inputs,
            )
            signed = build_customer_signoff_reconciliation_pack(
                root / "signed",
                release_label="signoff-test",
                **signed_inputs,
            )
            markdown = (root / "blocked" / "CUSTOMER_SIGNOFF_RECONCILIATION.md").read_text(encoding="utf-8")
            matrix = (root / "blocked" / "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv").read_text(encoding="utf-8")
            issues = (root / "blocked" / "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv").read_text(encoding="utf-8")
            intake = (root / "blocked" / "CUSTOMER_SIGNOFF_INTAKE.md").read_text(encoding="utf-8")
            template = (root / "blocked" / "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv").read_text(encoding="utf-8")
            evidence_matrix = (root / "evidence" / "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv").read_text(encoding="utf-8")
            evidence_issues = (root / "evidence" / "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv").read_text(encoding="utf-8")

        self.assertEqual(blocked["status"], "blocked_until_customer_signoff_and_live_proof")
        self.assertFalse(blocked["live_launch_ready"])
        self.assertFalse(blocked["production_signoff_ready"])
        self.assertEqual(blocked["summary"]["decision_count"], 10)
        self.assertGreaterEqual(blocked["summary"]["live_launch_blockers"], 1)
        self.assertGreaterEqual(blocked["summary"]["production_blockers"], 1)
        self.assertEqual(blocked["secret_scan"]["status"], "pass")
        self.assertEqual(blocked["summary"]["signoff_evidence_rows_loaded"], 0)
        self.assertIn("HomePilot Customer Signoff Reconciliation", markdown)
        self.assertIn("buyer_review_acceptance", matrix)
        self.assertIn("first_wave_go_no_go_missing", issues)
        self.assertIn("live_proof_missing", issues)
        self.assertIn("HomePilot Customer Signoff Intake", intake)
        self.assertIn("technical proof", intake.lower())
        self.assertIn("CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv", intake)
        self.assertIn("buyer_review_acceptance", template)
        self.assertIn("technical_proof_required", template)
        self.assertEqual(evidence["summary"]["signoff_evidence_rows_loaded"], 4)
        self.assertEqual(evidence["summary"]["signoff_evidence_rows_applied"], 1)
        self.assertEqual(evidence["summary"]["signoff_evidence_rows_rejected"], 3)
        self.assertIn("signed://daw/buyer-review", evidence_matrix)
        self.assertIn("technical_proof_cannot_be_overridden_by_signoff", evidence_issues)
        self.assertIn("signoff_reference_missing", evidence_issues)
        self.assertIn("signoff_evidence_unknown_decision", evidence_issues)
        self.assertNotIn("@example.com", json.dumps(blocked).lower() + markdown.lower() + matrix.lower())
        self.assertEqual(signed["status"], "customer_signoff_reconciled")
        self.assertTrue(signed["live_launch_ready"])
        self.assertTrue(signed["production_signoff_ready"])
        self.assertEqual(signed["summary"]["signed_decision_count"], signed["summary"]["decision_count"])

    def test_first_campaign_input_validation_blocks_unsafe_or_incomplete_inputs(self) -> None:
        template_pack = self._customer_input_template_pack()
        template_fields = {template["file_name"]: template["fields"] for template in template_pack["templates"]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            self._write_csv(
                inputs / "PARTNER_ROSTER_TEMPLATE.csv",
                template_fields["PARTNER_ROSTER_TEMPLATE.csv"],
                [{
                    "partner_id": "partner-01",
                    "partner_name": "Unsafe Partner",
                    "legal_company_name": "Unsafe Partner BV",
                    "region": "Flanders",
                    "cities_or_postcodes": "2001",
                    "language": "nl",
                    "capacity_per_month": "80",
                    "service_categories": "crepi",
                    "primary_contact_name": "Unsafe Contact",
                    "primary_contact_email_or_secret_channel_ref": "unsafe.partner@example.com",
                    "portal_role": "partner_renovator",
                    "escalation_owner": "DAW partner manager",
                    "partner_scope_notes": "full_network",
                    "status": "draft",
                }],
            )
            self._write_csv(
                inputs / "TERRITORY_ASSIGNMENT_TEMPLATE.csv",
                template_fields["TERRITORY_ASSIGNMENT_TEMPLATE.csv"],
                [{
                    "partner_id": "unknown-partner",
                    "region": "Flanders",
                    "cities_or_postcodes": "",
                    "included_postcodes": "",
                    "excluded_postcodes": "",
                    "capacity_cap": "0",
                    "overlap_rule": "",
                    "fallback_owner": "",
                    "assignment_priority": "1",
                    "notes": "incomplete territory",
                    "status": "draft",
                }],
            )
            self._write_csv(
                inputs / "PROPERTY_SOURCE_TEMPLATE.csv",
                template_fields["PROPERTY_SOURCE_TEMPLATE.csv"],
                [{
                    "source_file_name": "unsafe.csv",
                    "source_owner": "DAW data owner",
                    "tenant_id": "daw-belgium",
                    "module_key": "facadepilot",
                    "allowed_modules": "windowpilot",
                    "address_column": "address",
                    "postcode_column": "postcode",
                    "city_column": "city",
                    "source_provenance": "customer list",
                    "refresh_date": "2026-07-01",
                    "dedupe_rule": "address",
                    "public_data_used": "scraped_contacts",
                    "contact_basis_source": "to be reviewed",
                    "import_status": "pending",
                }],
            )
            self._write_csv(
                inputs / "MESSAGE_APPROVAL_TEMPLATE.csv",
                template_fields["MESSAGE_APPROVAL_TEMPLATE.csv"],
                [{
                    "message_variant": "unsafe_claim",
                    "language": "nl",
                    "module_key": "facadepilot",
                    "channel": "direct_mail",
                    "partner_branding_allowed": "yes",
                    "claim_summary": "guaranteed savings for your home",
                    "prohibited_claims_checked": "pending",
                    "cta": "call",
                    "opt_out_wording": "",
                    "marketing_owner": "DAW marketing owner",
                    "legal_owner": "DAW legal/privacy owner",
                    "approval_status": "pending",
                    "approved_at": "",
                    "notes": "",
                }],
            )
            self._write_csv(
                inputs / "PARTNER_CAPACITY_TEMPLATE.csv",
                template_fields["PARTNER_CAPACITY_TEMPLATE.csv"],
                [{
                    "partner_id": "unknown-partner",
                    "capacity_per_month": "0",
                    "appointment_slots_per_week": "0",
                    "response_sla_hours": "96",
                    "accepted_statuses": "",
                    "rejection_reasons_allowed": "",
                    "feedback_cadence": "",
                    "escalation_owner": "",
                    "capacity_status": "pending",
                    "notes": "",
                }],
            )

            report = build_first_campaign_input_validation(
                out_dir=root / "validation",
                template_pack=template_pack,
                input_dir=inputs,
                release_label="validation-test",
                expected_partner_count=10,
                live_proof_ready=False,
            )
            issues_csv = (root / "validation" / "FIRST_CAMPAIGN_INPUT_ISSUES.csv").read_text(encoding="utf-8")

        self.assertEqual(report["status"], "action_required")
        self.assertEqual(report["first_wave_decision"], "blocked_until_customer_input_fixes")
        self.assertGreater(report["summary"]["blockers"], 10)
        self.assertIn("raw_personal_contact_data", issues_csv)
        self.assertIn("[raw-email-redacted]", issues_csv)
        self.assertNotIn("unsafe.partner@example.com", issues_csv)
        self.assertIn("missing_required_file", issues_csv)
        self.assertIn("unknown_territory_partner", issues_csv)
        self.assertIn("message_not_approved", issues_csv)


    def test_customer_package_builds_filtered_handoff_artifacts(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            onboarding_path = tmp_path / "onboarding.json"
            payload_path = tmp_path / "payload.json"
            package_dir = tmp_path / "package"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Customer",
                tenant_slug="window-customer",
                modules=["windowpilot"],
                include_xlsx=True,
                include_zip=True,
            )
            self.assertEqual(manifest["access_audit"]["status"], "pass")
            self.assertEqual(manifest["summary"]["modules"], {"windowpilot": 1})
            self.assertTrue((package_dir / "dashboard" / "index.html").exists())
            self.assertTrue((package_dir / "dashboard" / "dashboard-data.js").exists())
            self.assertTrue((package_dir / "exports" / "properties.csv").exists())
            self.assertTrue((package_dir / "data" / "access_audit.json").exists())
            self.assertTrue((package_dir / "data" / "export_log.json").exists())
            self.assertTrue((package_dir / "data" / "customer_brief" / "customer_brief.json").exists())
            self.assertTrue((package_dir / "data" / "customer_brief" / "CUSTOMER_BRIEF.md").exists())
            self.assertTrue((package_dir / "data" / "campaign_learning" / "campaign_learning.json").exists())
            self.assertTrue((package_dir / "data" / "campaign_learning" / "CAMPAIGN_LEARNING.md").exists())
            self.assertTrue((package_dir / "data" / "territory_plan" / "territory_plan.json").exists())
            self.assertTrue((package_dir / "data" / "territory_plan" / "TERRITORY_PLAN.md").exists())
            self.assertTrue((package_dir / "data" / "roi_forecast" / "roi_forecast.json").exists())
            self.assertTrue((package_dir / "data" / "roi_forecast" / "ROI_FORECAST.md").exists())
            self.assertTrue((package_dir / "data" / "opportunity_dossier" / "opportunity_dossier.json").exists())
            self.assertTrue((package_dir / "data" / "opportunity_dossier" / "OPPORTUNITY_DOSSIER.md").exists())
            self.assertTrue((package_dir / "data" / "source_ledger" / "source_ledger.json").exists())
            self.assertTrue((package_dir / "data" / "source_ledger" / "SOURCE_LEDGER.md").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "open_intelligence.json").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "OPEN_INTELLIGENCE.md").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "OPEN_INTELLIGENCE_DECISION_MATRIX.csv").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "MARKETING_IMPACT_PLANNER.csv").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "MEASUREMENT_LOOP.csv").exists())
            self.assertTrue((package_dir / "data" / "boardroom_report" / "boardroom_report.json").exists())
            self.assertTrue((package_dir / "data" / "boardroom_report" / "BOARDROOM_REPORT.md").exists())
            self.assertTrue((package_dir / "dashboard" / "boardroom-report.html").exists())
            self.assertTrue((package_dir / "data" / "audit_events.json").exists())
            self.assertTrue((package_dir / "data" / "audit_trail_report.json").exists())
            self.assertTrue((package_dir / "data" / "dashboard_snapshot.json").exists())
            self.assertTrue((package_dir / "manifest.json").exists())
            self.assertTrue(package_dir.with_suffix(".zip").exists())
            export_log = json.loads((package_dir / "data" / "export_log.json").read_text(encoding="utf-8"))
            self.assertEqual(export_log["module_key"], "windowpilot")
            self.assertEqual(export_log["row_count"], 1)
            self.assertEqual(manifest["paths"]["export_log"], str(package_dir / "data" / "export_log.json"))
            self.assertEqual(manifest["audit_trail"]["status"], "pass")
            self.assertEqual(manifest["customer_brief"]["status"], "pass")
            self.assertEqual(manifest["customer_brief"]["scorecard"]["property_count"], 1)
            self.assertEqual(manifest["campaign_learning"]["status"], "pass")
            self.assertGreaterEqual(manifest["campaign_learning"]["experiments"], 1)
            self.assertEqual(manifest["territory_plan"]["status"], "pass")
            self.assertGreaterEqual(manifest["territory_plan"]["territories"], 1)
            self.assertEqual(manifest["roi_forecast"]["status"], "pass")
            self.assertEqual(manifest["roi_forecast"]["scenarios"], 3)
            self.assertEqual(manifest["opportunity_dossier"]["status"], "pass")
            self.assertEqual(manifest["opportunity_dossier"]["summary"]["dossiers"], 1)
            self.assertEqual(manifest["source_ledger"]["status"], "pass")
            self.assertEqual(manifest["source_ledger"]["summary"]["assessments"], 1)
            self.assertEqual(manifest["open_intelligence"]["status"], "pass")
            self.assertIn("Window Customer", manifest["open_intelligence"]["model"])
            self.assertEqual(manifest["open_intelligence"]["data_collaboration_room"], "ready_for_buyer_review")
            self.assertEqual(manifest["open_intelligence"]["marketing_impact_planner"], "review_ready")
            self.assertEqual(manifest["open_intelligence"]["boardroom_brief"], "boardroom_ready")
            self.assertEqual(manifest["open_intelligence"]["boardroom_decisions"], 5)
            self.assertGreaterEqual(manifest["open_intelligence"]["activation_lanes"], 5)
            self.assertGreaterEqual(manifest["open_intelligence"]["measurement_stages"], 5)
            self.assertEqual(manifest["open_intelligence"]["production_gate"], "buyer_review_ready_live_proof_required")
            self.assertFalse(manifest["open_intelligence"]["production_ready"])
            self.assertGreater(manifest["open_intelligence"]["production_blockers"], 0)
            self.assertTrue((package_dir / "data" / "open_intelligence" / "OPEN_INTELLIGENCE_PRODUCTION_GATE.md").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "OPEN_INTELLIGENCE_PRODUCTION_GATES.csv").exists())
            self.assertTrue((package_dir / "data" / "open_intelligence" / "OPEN_INTELLIGENCE_PRODUCTION_RUNBOOK.md").exists())
            self.assertEqual(manifest["boardroom_report"]["status"], "pass")
            self.assertEqual(manifest["boardroom_report"]["summary"]["properties"], 1)
            self.assertEqual(manifest["paths"]["boardroom_report_html"], str(package_dir / "dashboard" / "boardroom-report.html"))
            audit_events = json.loads((package_dir / "data" / "audit_events.json").read_text(encoding="utf-8"))
            audit_trail = json.loads((package_dir / "data" / "audit_trail_report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(audit_events), 3)
            self.assertEqual(audit_trail["status"], "pass")
            self.assertIn("customer_package_generated", audit_trail["metrics"]["event_types"])
            with zipfile.ZipFile(package_dir.with_suffix(".zip")) as archive:
                self.assertIn("manifest.json", archive.namelist())
                self.assertIn("data/export_log.json", archive.namelist())
                self.assertIn("data/customer_brief/CUSTOMER_BRIEF.md", archive.namelist())
                self.assertIn("data/campaign_learning/CAMPAIGN_LEARNING.md", archive.namelist())
                self.assertIn("data/territory_plan/TERRITORY_PLAN.md", archive.namelist())
                self.assertIn("data/roi_forecast/ROI_FORECAST.md", archive.namelist())
                self.assertIn("data/opportunity_dossier/OPPORTUNITY_DOSSIER.md", archive.namelist())
                self.assertIn("data/source_ledger/SOURCE_LEDGER.md", archive.namelist())
                self.assertIn("data/open_intelligence/OPEN_INTELLIGENCE.md", archive.namelist())
                self.assertIn("data/open_intelligence/OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md", archive.namelist())
                self.assertIn("data/open_intelligence/OPEN_INTELLIGENCE_DECISION_MATRIX.csv", archive.namelist())
                self.assertIn("data/open_intelligence/MARKETING_IMPACT_PLANNER.csv", archive.namelist())
                self.assertIn("data/open_intelligence/MEASUREMENT_LOOP.csv", archive.namelist())
                self.assertIn("data/boardroom_report/BOARDROOM_REPORT.md", archive.namelist())
                self.assertIn("dashboard/boardroom-report.html", archive.namelist())
                self.assertIn("data/audit_events.json", archive.namelist())
            dashboard_data = (package_dir / "dashboard" / "dashboard-data.js").read_text(encoding="utf-8").lower()
            dashboard_snapshot = json.loads((package_dir / "data" / "dashboard_snapshot.json").read_text(encoding="utf-8"))
            self.assertIn("windowpilot", dashboard_data)
            self.assertIn("openintelligence", dashboard_data)
            self.assertIn("intelligence", (package_dir / "dashboard" / "index.html").read_text(encoding="utf-8").lower())
            self.assertIn("brain", dashboard_snapshot)
            self.assertIn("visualIntelligence", dashboard_snapshot)
            self.assertIn("openIntelligence", dashboard_snapshot)
            self.assertIn("trust", dashboard_snapshot)
            self.assertIn("sourceLedger", dashboard_snapshot["trust"])
            self.assertGreater(dashboard_snapshot["brain"]["stats"]["nodes"], 0)
            self.assertEqual(dashboard_snapshot["visualIntelligence"]["status"], "pass")
            self.assertEqual(dashboard_snapshot["openIntelligence"]["status"], "pass")
            self.assertEqual(dashboard_snapshot["trust"]["sourceLedger"]["status"], "pass")
            self.assertNotIn("facadepilot", dashboard_data)

    def test_portal_bundle_wraps_customer_package_as_deployable_static_portal(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Portal Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            portal_dir = root / "portal"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Portal Customer",
                tenant_slug="window-portal-customer",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            portal = build_portal_bundle(Path(manifest["paths"]["manifest"]), portal_dir)
            portal_manifest = json.loads((portal_dir / "portal_manifest.json").read_text(encoding="utf-8"))
            headers = (portal_dir / "_headers").read_text(encoding="utf-8")
            redirects = (portal_dir / "_redirects").read_text(encoding="utf-8")
            public_data = (portal_dir / "public" / "dashboard-data.js").read_text(encoding="utf-8").lower()
            live_config = (portal_dir / "public" / "live-config.js").read_text(encoding="utf-8")
            live_loader = (portal_dir / "public" / "live-data.js").read_text(encoding="utf-8")
            public_index_exists = (portal_dir / "public" / "index.html").exists()
            public_export_exists = (portal_dir / "public" / "exports" / "properties.csv").exists()

        self.assertEqual(portal["status"], "pass")
        self.assertEqual(portal_manifest["portal_type"], "homepilot_customer_portal_bundle")
        self.assertEqual(portal_manifest["live_runtime"]["status"], "ready_for_customer_auth_config")
        self.assertFalse(portal_manifest["live_runtime"]["production_verified"])
        self.assertTrue(public_index_exists)
        self.assertTrue(public_export_exists)
        self.assertEqual(portal["checks"]["secret_scan"]["status"], "pass")
        self.assertEqual(portal["checks"]["expected_views"]["status"], "pass")
        self.assertEqual(portal["checks"]["live_runtime"]["status"], "pass")
        self.assertEqual(portal["checks"]["tenant_scope"]["status"], "pass")
        self.assertEqual(portal["checks"]["module_scope"]["enabled_modules"], ["windowpilot"])
        self.assertIn("Content-Security-Policy", headers)
        self.assertIn("frame-ancestors 'none'", headers)
        self.assertIn("/property/* /index.html 200", redirects)
        self.assertIn("window.HOMEPILOT_LIVE_CONFIG", live_config)
        self.assertIn("homepilot_property_intelligence", live_config)
        self.assertIn("Authorization: `Bearer ${accessToken}`", live_loader)
        self.assertNotIn("service-role", live_config.lower())
        self.assertNotIn("service-role", live_loader.lower())
        self.assertIn("windowpilot", public_data)
        self.assertNotIn("facadepilot", public_data)

    def test_live_portal_pack_gates_snapshot_behind_api_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            customer_package = root / "customer_package"
            dashboard_dir = customer_package / "dashboard"
            data_dir = customer_package / "data"
            dashboard_dir.mkdir(parents=True)
            data_dir.mkdir(parents=True)
            for filename in ("index.html", "styles.css", "app.js"):
                shutil.copy2(HOME_ROOT / "client" / filename, dashboard_dir / filename)
            snapshot = {
                "tenant": {
                    "id": "daw-belgium-crepi-network",
                    "name": "DAW Belgium (demo)",
                    "modules": ["facadepilot"],
                    "settings": {"demo": True},
                },
                "campaigns": [],
                "properties": [
                    {
                        "id": "prop-1",
                        "address": "Syntheticstraat 1",
                        "city": "Leuven",
                        "core": {"demo": True, "synthetic_record": True},
                        "assessments": {"facadepilot": {"score": 88, "grade": "A"}},
                    },
                    {
                        "id": "prop-2",
                        "address": "Syntheticstraat 2",
                        "city": "Antwerpen",
                        "core": {"demo": True, "synthetic_record": True},
                        "assessments": {"facadepilot": {"score": 91, "grade": "A+"}},
                    },
                ],
                "recommendations": [],
                "summary": {"properties": 2},
                "network": {"producer": {"id": "daw", "name": "DAW Belgium"}, "partners": []},
                "accessLenses": [],
                "trust": {},
                "brain": {
                    "nodes": [{"id": "n1", "label": "Signal", "type": "signal"}],
                    "edges": [{"source": "n1", "target": "n1", "type": "evidence"}],
                    "stats": {"nodes": 1, "edges": 1},
                },
                "visualIntelligence": {},
            }
            (data_dir / "dashboard_snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")

            out_dir = root / "live"
            result = build_live_portal(
                customer_package=customer_package,
                out_dir=out_dir,
                supabase_url="https://example.supabase.co",
                publishable_key="sb_publishable_test",
                tenant_id="daw-belgium-crepi-network",
                default_email="demo-login",
            )
            manifest = json.loads((out_dir / "api" / "_data" / "manifest.json").read_text(encoding="utf-8"))
            core = json.loads((out_dir / "api" / "_data" / "core.json").read_text(encoding="utf-8"))
            property_chunk = json.loads((out_dir / "api" / "_data" / "properties" / "properties-000.json").read_text(encoding="utf-8"))
            public_text = "\n".join(
                (out_dir / filename).read_text(encoding="utf-8")
                for filename in ("index.html", "dashboard-data.js", "sample-data.js", "live-data.js", "boardroom-report.html")
            )
            api_config = (out_dir / "api" / "_config.js").read_text(encoding="utf-8").lower()
            auth_live = (out_dir / "auth-live.js").read_text(encoding="utf-8")

        self.assertEqual(result["status"], "pass")
        self.assertEqual(manifest["properties"]["total"], 2)
        self.assertEqual(manifest["properties"]["parts"], 1)
        self.assertTrue(manifest["dataset"]["synthetic"])
        self.assertEqual(core["properties"], [])
        self.assertEqual(core["brain"]["nodes"], [])
        self.assertEqual(core["brain"]["edges"], [])
        self.assertEqual(len(property_chunk["rows"]), 2)
        self.assertIn("window.HOMEPILOT_DASHBOARD = null", public_text)
        self.assertIn("Boardroom report is gated", public_text)
        self.assertIn("./auth-live.js", public_text)
        self.assertNotIn("Syntheticstraat", public_text)
        self.assertIn("/api/login", auth_live)
        self.assertNotIn("service-role", api_config)

    def test_hosting_pack_builds_private_static_portal_deployment_evidence(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Hosted Portal",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            portal_dir = root / "portal"
            hosting_dir = root / "hosting"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Hosted Portal",
                tenant_slug="window-hosted-portal",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            build_portal_bundle(Path(manifest["paths"]["manifest"]), portal_dir)
            pack = build_hosting_pack(
                portal_manifest_path=portal_dir / "portal_manifest.json",
                out_dir=hosting_dir,
                release_label="hosting-test",
                env={},
            )
            hosting_manifest = json.loads((hosting_dir / "hosting_manifest.json").read_text(encoding="utf-8"))
            asset_manifest = json.loads((hosting_dir / "asset_manifest.json").read_text(encoding="utf-8"))
            netlify_toml = (hosting_dir / "netlify.toml").read_text(encoding="utf-8")
            vercel_json = (hosting_dir / "vercel.json").read_text(encoding="utf-8")
            runbook = (hosting_dir / "HOSTING_RUNBOOK.md").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in hosting_dir.iterdir()
                if path.is_file()
            )

        dashboard_asset = next(asset for asset in asset_manifest["assets"] if asset["path"] == "dashboard-data.js")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(hosting_manifest["stage_status"], "buyer_review_hosting_ready")
        self.assertEqual(hosting_manifest["checks"]["secret_scan"], "pass")
        self.assertTrue(hosting_manifest["publish_policy"]["requires_access_control_for_static_snapshot"])
        self.assertFalse(hosting_manifest["production_gate"]["verified"])
        self.assertTrue(any("Static tenant snapshot" in blocker for blocker in hosting_manifest["production_gate"]["blockers"]))
        self.assertGreater(asset_manifest["asset_count"], 0)
        self.assertEqual(dashboard_asset["cache_control"], "no-store")
        self.assertIn('publish = "public"', netlify_toml)
        self.assertIn('"rewrites"', vercel_json)
        self.assertIn("HomePilot Portal Hosting Runbook", runbook)
        self.assertNotIn("service-role", combined_output.lower())
        self.assertNotIn("secret-token", combined_output.lower())

    def test_visual_intelligence_pack_clusters_large_territories_and_budgets_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = build_visual_scale_fixture(property_count=180)
            pack = build_visual_intelligence_pack(root / "visual", snapshot=snapshot, release_label="visual-test")
            visual = json.loads((root / "visual" / "visual_intelligence.json").read_text(encoding="utf-8"))
            clusters = (root / "visual" / "map_clusters.csv").read_text(encoding="utf-8")
            runbook = (root / "visual" / "VISUAL_INTELLIGENCE.md").read_text(encoding="utf-8")
            client_app = (HOME_ROOT / "client" / "app.js").read_text(encoding="utf-8")
            combined_output = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (root / "visual").iterdir() if path.is_file())

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(visual["map"]["strategy"], "clustered_map")
        self.assertLess(len(visual["map"]["clusters"]), visual["map"]["property_count"])
        self.assertEqual(visual["graph"]["strategy"], "budgeted_graph")
        self.assertLessEqual(visual["graph"]["render_nodes"], visual["graph"]["node_budget"])
        self.assertGreater(visual["graph"]["hidden_nodes"], 0)
        self.assertIn("layout_config", visual["graph"])
        self.assertIn("layout_quality", visual["graph"])
        self.assertIn("final_score", visual["graph"]["layout_quality"])
        self.assertIn("overlap_count", visual["graph"]["layout_quality"])
        self.assertIn("fit_score", visual["graph"]["layout_quality"])
        self.assertEqual(visual["secret_scan"]["status"], "pass")
        self.assertIn("property_count", clusters)
        self.assertIn("HomePilot Visual Intelligence Runbook", runbook)
        self.assertIn("Graph Readability Evidence", runbook)
        self.assertIn("layout_config || {}", client_app)
        self.assertIn("BRAIN_LAYOUT_DEFAULTS", client_app)
        self.assertNotIn("service-role", combined_output.lower())

    def test_autoresearch_pack_scores_second_brain_layouts_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = build_visual_scale_fixture(property_count=80)
            pack = build_autoresearch_pack(root / "auto", snapshot=snapshot, release_label="auto-test", run_count=3)
            repeat = build_autoresearch_pack(root / "auto-repeat", snapshot=snapshot, release_label="auto-test", run_count=3)
            results = (root / "auto" / "results.tsv").read_text(encoding="utf-8")
            best = json.loads((root / "auto" / "best_graph_layout.json").read_text(encoding="utf-8"))
            report = (root / "auto" / "AUTORESEARCH_REPORT.md").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in (root / "auto").iterdir()
                if path.is_file()
            )

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["secret_scan"]["status"], "pass")
        self.assertEqual(pack["experiment_family"], "second_brain_graph_layout")
        self.assertEqual(pack["summary"]["best_score"], repeat["summary"]["best_score"])
        self.assertEqual(pack["best"]["layout_config"], repeat["best"]["layout_config"])
        self.assertIn("rank\ttag\tfinal_score", results)
        self.assertIn("HomePilot Autoresearch Report", report)
        self.assertIn("layout_config", best)
        self.assertIn("layout_quality", best)
        self.assertIn("final_score", best["layout_quality"])
        self.assertIn("overlap_count", best["layout_quality"])
        self.assertIn("fit_score", best["layout_quality"])
        self.assertTrue(pack["guardrails"]["synthetic_demo_only"])
        self.assertFalse(pack["guardrails"]["writes_supabase"])
        self.assertFalse(pack["guardrails"]["raw_contact_values_written"])
        self.assertNotIn("service-role", combined_output.lower())
        self.assertNotIn("authorization: bearer", combined_output.lower())

    def test_lead_autoresearch_pack_scores_priority_models_without_raw_addresses(self) -> None:
        payload = build_demo_payload(
            tenant_slug="daw-belgium-crepi-network",
            property_count=80,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = build_lead_autoresearch_pack(root / "lead", snapshot=snapshot, release_label="lead-test", run_count=8, limit=20)
            repeat = build_lead_autoresearch_pack(root / "lead-repeat", snapshot=snapshot, release_label="lead-test", run_count=8, limit=20)
            results = (root / "lead" / "results.tsv").read_text(encoding="utf-8")
            best = json.loads((root / "lead" / "best_lead_priority.json").read_text(encoding="utf-8"))
            report = (root / "lead" / "LEAD_AUTORESEARCH_REPORT.md").read_text(encoding="utf-8")
            client_app = (HOME_ROOT / "client" / "app.js").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in (root / "lead").iterdir()
                if path.is_file()
            )

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["secret_scan"]["status"], "pass")
        self.assertEqual(pack["experiment_family"], "lead_prioritization")
        self.assertGreaterEqual(pack["summary"]["best_score"], pack["summary"]["baseline_score"])
        self.assertEqual(pack["summary"]["best_score"], repeat["summary"]["best_score"])
        self.assertEqual(pack["best"]["priority_config"], repeat["best"]["priority_config"])
        self.assertIn("rank\ttag\tmodel_name\tfinal_score", results)
        self.assertIn("HomePilot Lead Autoresearch Report", report)
        self.assertIn("priority_config", best)
        self.assertIn("priority_quality", best)
        self.assertIn("final_score", best["priority_quality"])
        self.assertIn("engaged_rate_pct", best["priority_quality"])
        self.assertIn("partner_balance_score", best["priority_quality"])
        self.assertLessEqual(len(best["best_queue"]), 20)
        self.assertIn("priority_score", best["best_queue"][0])
        self.assertNotIn("address", best["best_queue"][0])
        self.assertTrue(pack["guardrails"]["outcome_proxy_only"])
        self.assertFalse(pack["guardrails"]["writes_supabase"])
        self.assertFalse(pack["guardrails"]["raw_addresses_in_best_queue"])
        self.assertIn("leadPrioritization", client_app)
        self.assertIn("best_queue", client_app)
        self.assertNotIn("daw gevelstraat", combined_output.lower())
        self.assertNotIn("service-role", combined_output.lower())
        self.assertNotIn("authorization: bearer", combined_output.lower())

    def test_partner_assignment_autoresearch_pack_builds_scope_safe_partner_waves(self) -> None:
        payload = build_demo_payload(
            tenant_slug="daw-belgium-crepi-network",
            property_count=100,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        snapshot["leadPrioritization"] = build_lead_priority_recommendation(snapshot, run_count=8, limit=30)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = build_partner_assignment_autoresearch_pack(
                root / "assignment",
                snapshot=snapshot,
                release_label="assignment-test",
                run_count=10,
                limit=30,
            )
            repeat = build_partner_assignment_autoresearch_pack(
                root / "assignment-repeat",
                snapshot=snapshot,
                release_label="assignment-test",
                run_count=10,
                limit=30,
            )
            results = (root / "assignment" / "results.tsv").read_text(encoding="utf-8")
            best = json.loads((root / "assignment" / "best_partner_assignment.json").read_text(encoding="utf-8"))
            report = (root / "assignment" / "PARTNER_ASSIGNMENT_AUTORESEARCH_REPORT.md").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in (root / "assignment").iterdir()
                if path.is_file()
            )
            snapshot["partnerAssignment"] = best
            intelligence = build_open_intelligence(snapshot)

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["secret_scan"]["status"], "pass")
        self.assertEqual(pack["experiment_family"], "partner_assignment")
        self.assertGreaterEqual(pack["summary"]["best_score"], pack["summary"]["baseline_score"])
        self.assertEqual(pack["summary"]["best_score"], repeat["summary"]["best_score"])
        self.assertEqual(pack["best"]["assignment_config"], repeat["best"]["assignment_config"])
        self.assertIn("rank\ttag\tstrategy_name\tfinal_score", results)
        self.assertIn("HomePilot Partner Assignment Autoresearch Report", report)
        self.assertIn("assignment_config", best)
        self.assertIn("assignment_quality", best)
        self.assertIn("final_score", best["assignment_quality"])
        self.assertIn("capacity_fit_score", best["assignment_quality"])
        self.assertIn("territory_fit_score", best["assignment_quality"])
        self.assertEqual(best["assignment_quality"]["scope_leakage_count"], 0)
        self.assertEqual(len(best["best_assignment"]), 10)
        self.assertLessEqual(sum(row["selected_count"] for row in best["best_assignment"]), 30)
        self.assertIn("selected_property_ids", best["best_assignment"][0])
        self.assertNotIn("address", json.dumps(best["best_assignment"][0]).lower())
        self.assertTrue(pack["guardrails"]["existing_partner_assignments_only"])
        self.assertFalse(pack["guardrails"]["writes_supabase"])
        self.assertFalse(pack["guardrails"]["raw_addresses_in_best_assignment"])
        families = {row["family"]: row for row in intelligence["model_lab"]["experiment_families"]}
        self.assertEqual(families["partner_assignment"]["status"], "ready")
        self.assertEqual(families["partner_assignment"]["scope_leakage_count"], 0)
        self.assertEqual(intelligence["activation"]["autoresearched_partner_batches"], 10)
        self.assertNotIn("daw gevelstraat", combined_output.lower())
        self.assertNotIn("service-role", combined_output.lower())
        self.assertNotIn("authorization: bearer", combined_output.lower())

    def test_campaign_segmentation_autoresearch_pack_builds_denominator_safe_segments(self) -> None:
        payload = build_demo_payload(
            tenant_slug="daw-belgium-crepi-network",
            property_count=120,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        snapshot["leadPrioritization"] = build_lead_priority_recommendation(snapshot, run_count=8, limit=30)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assignment_pack = build_partner_assignment_autoresearch_pack(
                root / "assignment",
                snapshot=snapshot,
                release_label="segment-assignment-test",
                run_count=8,
                limit=30,
            )
            snapshot["partnerAssignment"] = json.loads(
                (root / "assignment" / "best_partner_assignment.json").read_text(encoding="utf-8")
            )
            pack = build_campaign_segmentation_autoresearch_pack(
                root / "segments",
                snapshot=snapshot,
                release_label="segment-test",
                run_count=12,
            )
            repeat = build_campaign_segmentation_autoresearch_pack(
                root / "segments-repeat",
                snapshot=snapshot,
                release_label="segment-test",
                run_count=12,
            )
            results = (root / "segments" / "results.tsv").read_text(encoding="utf-8")
            best = json.loads((root / "segments" / "best_campaign_segments.json").read_text(encoding="utf-8"))
            report = (root / "segments" / "CAMPAIGN_SEGMENTATION_AUTORESEARCH_REPORT.md").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in (root / "segments").iterdir()
                if path.is_file()
            )
            snapshot["campaignSegmentation"] = best
            intelligence = build_open_intelligence(snapshot)

        self.assertEqual(assignment_pack["status"], "pass")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["secret_scan"]["status"], "pass")
        self.assertEqual(pack["experiment_family"], "campaign_segmentation")
        self.assertGreaterEqual(pack["summary"]["best_score"], pack["summary"]["baseline_score"])
        self.assertEqual(pack["summary"]["best_score"], repeat["summary"]["best_score"])
        self.assertEqual(pack["best"]["segment_config"], repeat["best"]["segment_config"])
        self.assertIn("rank\ttag\tstrategy_name\tdimensions\tfinal_score", results)
        self.assertIn("HomePilot Campaign Segmentation Autoresearch Report", report)
        self.assertIn("segment_config", best)
        self.assertIn("segment_quality", best)
        self.assertIn("final_score", best["segment_quality"])
        self.assertEqual(best["segment_quality"]["response_denominator"], "contacted_count")
        self.assertEqual(best["segment_quality"]["denominator_clarity_score"], 100.0)
        self.assertGreater(len(best["best_segments"]), 0)
        self.assertEqual(best["best_segments"][0]["response_denominator"], "contacted_count")
        self.assertIn("target_response_rate_pct", best["best_segments"][0])
        self.assertIn("top_property_ids", best["best_segments"][0])
        self.assertNotIn("address", json.dumps(best["best_segments"][0]).lower())
        self.assertTrue(pack["guardrails"]["response_denominator_is_contacted_count"])
        self.assertFalse(pack["guardrails"]["writes_supabase"])
        self.assertFalse(pack["guardrails"]["raw_addresses_in_best_segments"])
        families = {row["family"]: row for row in intelligence["model_lab"]["experiment_families"]}
        self.assertEqual(families["campaign_segmentation"]["status"], "ready")
        self.assertEqual(families["campaign_segmentation"]["response_denominator"], "contacted_count")
        self.assertGreater(intelligence["activation"]["autoresearched_segments"], 0)
        self.assertNotIn("daw gevelstraat", combined_output.lower())
        self.assertNotIn("service-role", combined_output.lower())
        self.assertNotIn("authorization: bearer", combined_output.lower())

    def test_message_strategy_autoresearch_pack_builds_compliant_message_tests(self) -> None:
        payload = build_demo_payload(
            tenant_slug="daw-belgium-crepi-network",
            property_count=120,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        snapshot["leadPrioritization"] = build_lead_priority_recommendation(snapshot, run_count=8, limit=30)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assignment_pack = build_partner_assignment_autoresearch_pack(
                root / "assignment",
                snapshot=snapshot,
                release_label="message-assignment-test",
                run_count=8,
                limit=30,
            )
            snapshot["partnerAssignment"] = json.loads(
                (root / "assignment" / "best_partner_assignment.json").read_text(encoding="utf-8")
            )
            segment_pack = build_campaign_segmentation_autoresearch_pack(
                root / "segments",
                snapshot=snapshot,
                release_label="message-segment-test",
                run_count=12,
            )
            snapshot["campaignSegmentation"] = json.loads(
                (root / "segments" / "best_campaign_segments.json").read_text(encoding="utf-8")
            )
            pack = build_message_strategy_autoresearch_pack(
                root / "messages",
                snapshot=snapshot,
                release_label="message-test",
                run_count=12,
            )
            repeat = build_message_strategy_autoresearch_pack(
                root / "messages-repeat",
                snapshot=snapshot,
                release_label="message-test",
                run_count=12,
            )
            results = (root / "messages" / "results.tsv").read_text(encoding="utf-8")
            best = json.loads((root / "messages" / "best_message_strategy.json").read_text(encoding="utf-8"))
            report = (root / "messages" / "MESSAGE_STRATEGY_AUTORESEARCH_REPORT.md").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in (root / "messages").iterdir()
                if path.is_file()
            )
            snapshot["messageStrategy"] = best
            intelligence = build_open_intelligence(snapshot)

        self.assertEqual(assignment_pack["status"], "pass")
        self.assertEqual(segment_pack["status"], "pass")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["secret_scan"]["status"], "pass")
        self.assertEqual(pack["experiment_family"], "message_strategy")
        self.assertGreaterEqual(pack["summary"]["best_score"], pack["summary"]["baseline_score"])
        self.assertEqual(pack["summary"]["best_score"], repeat["summary"]["best_score"])
        self.assertEqual(pack["best"]["message_config"], repeat["best"]["message_config"])
        self.assertIn("rank\ttag\tstrategy_name\tfinal_score", results)
        self.assertIn("HomePilot Message Strategy Autoresearch Report", report)
        self.assertIn("message_config", best)
        self.assertIn("message_quality", best)
        self.assertIn("final_score", best["message_quality"])
        self.assertEqual(best["message_quality"]["response_denominator"], "contacted_count")
        self.assertEqual(best["message_quality"]["forbidden_claim_count"], 0)
        self.assertEqual(best["message_quality"]["compliance_pass_rate_pct"], 100.0)
        self.assertGreater(len(best["best_message_tests"]), 0)
        self.assertEqual(best["best_message_tests"][0]["compliance_status"], "pass")
        self.assertEqual(best["best_message_tests"][0]["forbidden_claim_count"], 0)
        self.assertTrue(best["best_message_tests"][0]["draft_requires_customer_approval"])
        self.assertIn("claim_guardrails", best["best_message_tests"][0])
        self.assertNotIn("address", json.dumps(best["best_message_tests"][0]).lower())
        self.assertTrue(pack["guardrails"]["drafts_require_customer_approval"])
        self.assertFalse(pack["guardrails"]["writes_supabase"])
        self.assertFalse(pack["guardrails"]["raw_addresses_in_best_message_tests"])
        families = {row["family"]: row for row in intelligence["model_lab"]["experiment_families"]}
        self.assertEqual(families["message_strategy"]["status"], "ready")
        self.assertEqual(families["message_strategy"]["forbidden_claim_count"], 0)
        self.assertEqual(families["message_strategy"]["response_denominator"], "contacted_count")
        self.assertGreater(intelligence["activation"]["autoresearched_message_tests"], 0)
        self.assertNotIn("daw gevelstraat", combined_output.lower())
        self.assertNotIn("service-role", combined_output.lower())
        self.assertNotIn("authorization: bearer", combined_output.lower())
        self.assertNotIn("guaranteed", combined_output.lower())

    def test_intelligence_lab_pack_attaches_full_daw_research_stack(self) -> None:
        payload = build_demo_payload(
            tenant_slug="daw-belgium-crepi-network",
            property_count=120,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = build_intelligence_lab_pack(
                root / "lab",
                snapshot=snapshot,
                release_label="lab-test",
                run_count=6,
                lead_limit=30,
            )
            repeat_snapshot = build_dashboard_snapshot(
                payload,
                tenant_name="DAW Belgium",
                tenant_slug="daw-belgium-crepi-network",
                enabled_modules=["facadepilot"],
            )
            repeat = build_intelligence_lab_pack(
                root / "lab-repeat",
                snapshot=repeat_snapshot,
                release_label="lab-test",
                run_count=6,
                lead_limit=30,
            )
            report = json.loads((root / "lab" / "intelligence_lab.json").read_text(encoding="utf-8"))
            markdown = (root / "lab" / "INTELLIGENCE_LAB.md").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in (root / "lab").rglob("*")
                if path.is_file()
            )
            intelligence = build_open_intelligence(snapshot)

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["report"]["secret_scan"]["status"], "pass")
        self.assertEqual(report["pack_type"], "homepilot_intelligence_lab")
        self.assertIn("HomePilot Intelligence Lab", markdown)
        self.assertEqual(set(report["families"]), {
            "lead_prioritization",
            "partner_assignment",
            "campaign_segmentation",
            "message_strategy",
        })
        self.assertEqual(pack["report"]["families"]["message_strategy"]["forbidden_claim_count"], 0)
        self.assertEqual(pack["report"]["families"]["partner_assignment"]["scope_leakage_count"], 0)
        self.assertEqual(pack["report"]["families"]["campaign_segmentation"]["response_denominator"], "contacted_count")
        self.assertEqual(pack["report"]["families"]["lead_prioritization"]["best_tag"], repeat["report"]["families"]["lead_prioritization"]["best_tag"])
        self.assertEqual(pack["report"]["families"]["message_strategy"]["best_tag"], repeat["report"]["families"]["message_strategy"]["best_tag"])
        self.assertIn("leadPrioritization", snapshot)
        self.assertIn("partnerAssignment", snapshot)
        self.assertIn("campaignSegmentation", snapshot)
        self.assertIn("messageStrategy", snapshot)
        families = {row["family"]: row for row in intelligence["model_lab"]["experiment_families"]}
        self.assertEqual(families["lead_prioritization"]["status"], "ready")
        self.assertEqual(families["partner_assignment"]["status"], "ready")
        self.assertEqual(families["partner_assignment"]["scope_leakage_count"], 0)
        self.assertEqual(families["campaign_segmentation"]["status"], "ready")
        self.assertEqual(families["message_strategy"]["status"], "ready")
        self.assertEqual(families["campaign_segmentation"]["response_denominator"], "contacted_count")
        self.assertEqual(families["message_strategy"]["forbidden_claim_count"], 0)
        self.assertNotIn("daw gevelstraat", combined_output.lower())
        self.assertNotIn("service-role", combined_output.lower())
        self.assertNotIn("authorization: bearer", combined_output.lower())
        self.assertNotIn("guaranteed", combined_output.lower())

    def test_boardroom_report_surfaces_intelligence_lab_evidence(self) -> None:
        payload = build_demo_payload(
            tenant_slug="daw-belgium-crepi-network",
            property_count=120,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_intelligence_lab_pack(
                root / "lab",
                snapshot=snapshot,
                release_label="boardroom-lab-test",
                run_count=6,
                lead_limit=30,
            )
            pack = build_boardroom_report_pack(snapshot, root / "report", dashboard_dir=root / "dashboard")
            report = json.loads(Path(pack["paths"]["boardroom_report"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
            html = Path(pack["paths"]["html"]).read_text(encoding="utf-8")
            combined_output = "\n".join([json.dumps(report), markdown, html]).lower()

        lab = report["intelligence_lab"]
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(lab["status"], "ready")
        self.assertEqual(lab["family_count"], 4)
        self.assertEqual(lab["scope_leakage_count"], 0)
        self.assertEqual(lab["forbidden_claim_count"], 0)
        self.assertEqual(lab["response_denominator"], "contacted_count")
        self.assertTrue(lab["synthetic_demo_evidence"])
        self.assertIn("Intelligence Lab Evidence", markdown)
        self.assertIn("Intelligence Lab Evidence", html)
        self.assertIn("campaign segmentation", markdown)
        self.assertIn("denominator contacted_count", markdown)
        self.assertIn("forbidden claims 0", markdown)
        self.assertIn("Review the Intelligence Lab evidence", report["recommendations"][0])
        self.assertIn("Autoresearch scores are synthetic/demo outcome proxies", report["caveats"][-1])
        self.assertNotIn("daw gevelstraat", combined_output)
        self.assertNotIn("service-role", combined_output)
        self.assertNotIn("authorization: bearer", combined_output)
        self.assertNotIn("guaranteed", combined_output)

    def test_open_intelligence_pack_builds_model_lab_and_data_room_without_raw_addresses(self) -> None:
        payload = build_demo_payload(
            tenant_slug="daw-belgium-crepi-network",
            property_count=80,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_open_intelligence_pack(Path(tmp), snapshot=snapshot)
            report = json.loads(Path(pack["paths"]["open_intelligence"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
            boardroom_brief = Path(pack["paths"]["boardroom_brief"]).read_text(encoding="utf-8")
            decision_matrix = Path(pack["paths"]["decision_matrix"]).read_text(encoding="utf-8")
            impact_csv = Path(pack["paths"]["marketing_impact_planner"]).read_text(encoding="utf-8")
            measurement_csv = Path(pack["paths"]["measurement_loop"]).read_text(encoding="utf-8")
            production_gate = Path(pack["paths"]["production_gate"]).read_text(encoding="utf-8")
            production_gates = Path(pack["paths"]["production_gates"]).read_text(encoding="utf-8")
            production_runbook = Path(pack["paths"]["production_runbook"]).read_text(encoding="utf-8")
            combined = (
                json.dumps(report).lower()
                + markdown.lower()
                + boardroom_brief.lower()
                + decision_matrix.lower()
                + production_gate.lower()
                + production_runbook.lower()
            )

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(report["report_type"], "homepilot_open_intelligence")
        self.assertEqual(report["model_card"]["name"], "DAW Belgium Crepi Opportunity Model")
        self.assertEqual(report["model_card"]["tenant"]["partner_count"], 10)
        self.assertEqual(report["data_collaboration_room"]["status"], "ready_for_buyer_review")
        self.assertEqual(report["marketing_impact_planner"]["status"], "review_ready")
        self.assertEqual(report["boardroom_brief"]["status"], "boardroom_ready")
        self.assertEqual(report["production_gate"]["status"], "buyer_review_ready_live_proof_required")
        self.assertFalse(report["production_gate"]["production_ready"])
        self.assertTrue(report["production_gate"]["buyer_review_ready"])
        self.assertGreaterEqual(report["production_gate"]["gate_count"], 8)
        self.assertGreater(report["production_gate"]["production_blocker_count"], 0)
        self.assertEqual(len(report["boardroom_brief"]["decision_questions"]), 5)
        self.assertEqual(report["marketing_impact_planner"]["privacy_pattern"]["name"], "intelligence_beyond_identity")
        self.assertGreaterEqual(len(report["marketing_impact_planner"]["activation_lanes"]), 5)
        self.assertGreaterEqual(len(report["marketing_impact_planner"]["channel_mix"]), 5)
        self.assertIn("contacted_count", json.dumps(report["marketing_impact_planner"]))
        self.assertTrue(report["guardrails"]["tenant_scoped"])
        self.assertTrue(report["guardrails"]["partner_scoped_for_producer_networks"])
        self.assertTrue(report["guardrails"]["no_homeowner_intent_without_response_or_customer_evidence"])
        self.assertIn("HomePilot Open Intelligence", markdown)
        self.assertIn("Marketing Impact Planner", markdown)
        self.assertIn("HomePilot Open Intelligence Boardroom Brief", boardroom_brief)
        self.assertIn("where_to_focus_first_wave", decision_matrix)
        self.assertIn("how_to_measure_marketing_impact", decision_matrix)
        self.assertIn("priority_queue_activation", impact_csv)
        self.assertIn("contacted_measurement", measurement_csv)
        self.assertIn("HomePilot Open Intelligence Production Gate", production_gate)
        self.assertIn("activation_control_contract", production_gates)
        self.assertIn("customer go/no-go", production_runbook)
        self.assertIn("production_gate", combined)
        self.assertIn("second_brain_graph_layout", combined)
        self.assertIn("lead_prioritization", combined)
        self.assertNotIn("daw gevelstraat", combined)
        self.assertNotIn("service-role", combined)
        self.assertNotIn("authorization: bearer", combined)
        self.assertNotIn("service-role", impact_csv.lower() + measurement_csv.lower() + decision_matrix.lower() + production_gates.lower())

    def test_outcome_measurement_contract_defines_closed_loop_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = build_outcome_measurement_contract_pack(
                root,
                market_readiness={
                    "decisions": {"buyer_review": "go", "live_launch": "no_go", "production": "no_go"},
                    "summary": {"production_verified": False},
                    "value_realization_plan": {"status": "buyer_review_value_ready"},
                },
                production_proof={"production_gate": {"verified": False}},
                release_label="outcome-contract-test",
            )
            report = json.loads(Path(pack["paths"]["outcome_measurement_contract"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["outcome_measurement_contract_markdown"]).read_text(encoding="utf-8")
            schema_csv = Path(pack["paths"]["outcome_event_schema"]).read_text(encoding="utf-8")
            template_csv = Path(pack["paths"]["outcome_sync_template"]).read_text(encoding="utf-8")
            checklist_csv = Path(pack["paths"]["outcome_reconciliation_checklist"]).read_text(encoding="utf-8")
            combined = json.dumps(report).lower() + markdown.lower() + schema_csv.lower() + template_csv.lower() + checklist_csv.lower()

        self.assertEqual(report["contract_type"], "homepilot_outcome_measurement_contract")
        self.assertEqual(report["status"], "buyer_review_ready_live_outcome_sync_blocked")
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertGreaterEqual(report["summary"]["event_field_count"], 14)
        self.assertGreaterEqual(report["summary"]["metric_count"], 5)
        self.assertGreaterEqual(report["summary"]["blocked_gate_count"], 2)
        self.assertFalse(report["summary"]["production_verified"])
        self.assertIn("won_project", report["summary"]["allowed_outcome_stages"])
        self.assertIn("lost_project", report["summary"]["allowed_outcome_stages"])
        self.assertIn("quote_sent", report["summary"]["allowed_outcome_stages"])
        self.assertTrue(report["guardrails"]["no_crm_writes"])
        self.assertTrue(report["guardrails"]["no_supabase_writes"])
        self.assertTrue(report["guardrails"]["no_raw_contact_data"])
        self.assertIn("HomePilot Outcome Measurement Contract", markdown)
        self.assertIn("Win rate", markdown)
        self.assertIn("outcome_stage", schema_csv)
        self.assertIn("source_record_ref", schema_csv)
        self.assertIn("crm://redacted", template_csv)
        self.assertIn("live_access_proven", checklist_csv)
        self.assertNotIn("@example.com", combined)
        self.assertNotIn("service_role=", combined)
        self.assertNotIn("authorization: bearer", combined)

    def test_outcome_import_validation_dry_run_blocks_unsafe_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = build_outcome_measurement_contract_pack(
                root / "contract",
                market_readiness={
                    "decisions": {"buyer_review": "go", "live_launch": "no_go", "production": "no_go"},
                    "summary": {"production_verified": False},
                },
                production_proof={"production_gate": {"verified": False}},
                release_label="outcome-import-test",
            )
            passing = build_outcome_import_validation_pack(
                root / "passing",
                input_csv=Path(contract["paths"]["outcome_sync_template"]),
                outcome_contract=contract,
                expected_tenant_id="daw-belgium",
                expected_module_key="facadepilot",
                release_label="outcome-import-test",
            )
            unsafe_csv = root / "unsafe_outcomes.csv"
            with unsafe_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "tenant_id",
                    "module_key",
                    "partner_id",
                    "campaign_id",
                    "property_id",
                    "outcome_event_id",
                    "outcome_stage",
                    "event_at",
                    "source_system",
                    "source_record_ref",
                    "amount_ex_vat",
                    "currency",
                    "loss_reason",
                    "evidence_reference",
                    "customer_approval_reference",
                ])
                writer.writeheader()
                writer.writerow({
                    "tenant_id": "daw-belgium",
                    "module_key": "facadepilot",
                    "partner_id": "daw-partner-01",
                    "campaign_id": "campaign-001",
                    "property_id": "property-001",
                    "outcome_event_id": "duplicate-event",
                    "outcome_stage": "quote_sent",
                    "event_at": "not-a-date",
                    "source_system": "customer_crm",
                    "source_record_ref": "owner@example.com",
                    "amount_ex_vat": "",
                    "currency": "EUR",
                    "loss_reason": "",
                    "evidence_reference": "crm://redacted/quote/001",
                    "customer_approval_reference": "",
                })
                writer.writerow({
                    "tenant_id": "daw-belgium",
                    "module_key": "facadepilot",
                    "partner_id": "daw-partner-01",
                    "campaign_id": "campaign-001",
                    "property_id": "property-002",
                    "outcome_event_id": "duplicate-event",
                    "outcome_stage": "won_project",
                    "event_at": "2026-07-22T14:30:00Z",
                    "source_system": "private_note",
                    "source_record_ref": "crm://redacted/opportunity/002",
                    "amount_ex_vat": "-50",
                    "currency": "USD",
                    "loss_reason": "",
                    "evidence_reference": "crm://redacted/won/002",
                    "customer_approval_reference": "signed://customer/outcome-sync-approval",
                })
            blocked = build_outcome_import_validation_pack(
                root / "blocked",
                input_csv=unsafe_csv,
                outcome_contract=contract,
                expected_tenant_id="daw-belgium",
                expected_module_key="facadepilot",
                release_label="outcome-import-test",
            )
            passing_report = json.loads(Path(passing["paths"]["outcome_import_validation"]).read_text(encoding="utf-8"))
            blocked_report = json.loads(Path(blocked["paths"]["outcome_import_validation"]).read_text(encoding="utf-8"))
            blocked_markdown = Path(blocked["paths"]["outcome_import_validation_markdown"]).read_text(encoding="utf-8")
            blocked_issues = Path(blocked["paths"]["outcome_import_issues"]).read_text(encoding="utf-8")
            blocked_rows = Path(blocked["paths"]["outcome_import_review_rows"]).read_text(encoding="utf-8")
            combined_blocked = json.dumps(blocked_report).lower() + blocked_markdown.lower() + blocked_issues.lower() + blocked_rows.lower()

        self.assertEqual(passing_report["status"], "ready_for_customer_review_live_sync_blocked")
        self.assertEqual(passing_report["sync_decision"], "blocked_until_live_proof")
        self.assertEqual(passing_report["secret_scan"]["status"], "pass")
        self.assertEqual(passing_report["summary"]["blocker_count"], 0)
        self.assertEqual(passing_report["summary"]["row_count"], 2)
        self.assertTrue(passing_report["guardrails"]["no_supabase_writes"])
        self.assertTrue(passing_report["guardrails"]["no_crm_writes"])
        self.assertEqual(blocked_report["status"], "blocked_until_outcome_input_fixes")
        self.assertGreaterEqual(blocked_report["summary"]["blocker_count"], 6)
        self.assertIn("raw_contact_data_detected", blocked_issues)
        self.assertIn("[raw-email-redacted]", blocked_issues)
        self.assertIn("duplicate_outcome_event_id", blocked_issues)
        self.assertIn("missing_amount_ex_vat", blocked_issues)
        self.assertIn("invalid_currency", blocked_issues)
        self.assertIn("invalid_source_system", blocked_issues)
        self.assertIn("blocked", blocked_rows)
        self.assertNotIn("owner@example.com", combined_blocked)
        self.assertNotIn("service_role=", combined_blocked)
        self.assertNotIn("authorization: bearer", combined_blocked)

    def test_live_proof_evidence_vault_indexes_required_proof_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "LIVE_PROOF_EXECUTION_PLAN.md",
                "LIVE_PROOF_ACCEPTANCE_MATRIX.md",
                "LIVE_LAUNCH_CONTROL_ROOM.md",
                "PARTNER_AUTH_MAPPING.md",
            ):
                (root / name).write_text(f"# {name}\nreview artifact only\n", encoding="utf-8")
            pack = build_live_proof_evidence_vault_pack(
                root,
                artifact_paths={
                    "live_proof_plan": str(root / "LIVE_PROOF_EXECUTION_PLAN.md"),
                    "live_proof_acceptance": str(root / "LIVE_PROOF_ACCEPTANCE_MATRIX.md"),
                    "live_launch_control_room": str(root / "LIVE_LAUNCH_CONTROL_ROOM.md"),
                    "partner_auth_mapping": str(root / "PARTNER_AUTH_MAPPING.md"),
                },
                live_launch_request={"summary": {"task_count": 10}},
                live_proof_plan={"secret_scan": {"status": "pass"}, "plan_validation": {"status": "pass"}},
                live_proof_acceptance={"secret_scan": {"status": "pass"}, "summary": {"criterion_count": 12}},
                production_proof={"production_gate": {"verified": False}},
                launch_control_room={"secret_scan": {"status": "pass"}},
                partner_auth_mapping={"status": "mapping_required"},
                first_wave_launch_gate={"launch_authorized": False},
                release_label="vault-test",
            )
            report = json.loads(Path(pack["paths"]["live_proof_evidence_vault"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["live_proof_evidence_vault_markdown"]).read_text(encoding="utf-8")
            archive_csv = Path(pack["paths"]["live_proof_archive_index"]).read_text(encoding="utf-8")
            combined = json.dumps(report).lower() + markdown.lower() + archive_csv.lower()

        self.assertEqual(report["vault_type"], "homepilot_live_proof_evidence_vault")
        self.assertEqual(report["status"], "live_proof_blocked")
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertFalse(report["summary"]["production_verified"])
        self.assertEqual(report["summary"]["production_verified_label"], "production_verified=false")
        self.assertGreaterEqual(report["summary"]["required_count"], 14)
        self.assertGreaterEqual(report["summary"]["blocked_count"], 5)
        keys = {row["key"] for row in report["evidence_rows"]}
        self.assertIn("schema_verification_report", keys)
        self.assertIn("customer_access_report", keys)
        self.assertIn("production_proof_gate", keys)
        self.assertIn("partner_access_reconciliation", keys)
        self.assertIn("HomePilot Live Proof Evidence Vault", markdown)
        self.assertIn("production_verified=false", markdown)
        self.assertIn("no_secret_values: true", markdown)
        self.assertIn("schema_verification_report", archive_csv)
        self.assertIn("customer_access_report", archive_csv)
        self.assertIn("production_proof_gate", archive_csv)
        self.assertNotIn("@example.com", combined)
        self.assertNotIn("service_role=", combined)
        self.assertNotIn("authorization: bearer", combined)

    def test_live_credential_handoff_builds_secret_safe_channel_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = build_live_credential_handoff_pack(
                root,
                live_readiness={"status": "action_required", "ready_to_run_live_cutover": False},
                live_launch_request={
                    "status": "action_required",
                    "summary": {"task_count": 3},
                    "tasks": [
                        {
                            "task_id": "supabase_url",
                            "category": "supabase",
                            "owner": "platform_admin",
                            "owner_label": "Platform admin / Supabase owner",
                            "status": "required",
                            "input_name": "supabase_url",
                            "env_var": "HOMEPILOT_SUPABASE_URL",
                            "accepted_env_vars": ["HOMEPILOT_SUPABASE_URL", "SUPABASE_URL"],
                            "purpose": "Supabase project REST/Auth endpoint.",
                            "required_for_live": True,
                            "current_status": "missing",
                            "secret_value_required": False,
                        },
                        {
                            "task_id": "supabase_service_key",
                            "category": "supabase",
                            "owner": "platform_admin",
                            "owner_label": "Platform admin / Supabase owner",
                            "status": "required",
                            "input_name": "supabase_service_key",
                            "env_var": "HOMEPILOT_SUPABASE_SERVICE_KEY",
                            "accepted_env_vars": ["HOMEPILOT_SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY"],
                            "purpose": "Service-role access for module seeding and fixture import.",
                            "required_for_live": True,
                            "current_status": "missing",
                            "secret_value_required": True,
                        },
                        {
                            "task_id": "customer_access_partner_example_com",
                            "category": "customer_access",
                            "owner": "customer_success",
                            "owner_label": "Customer success / tenant admin",
                            "status": "required",
                            "input_name": "credential for partner@example.com",
                            "env_var": "HOMEPILOT_ACCESS_PARTNER_TOKEN",
                            "accepted_env_vars": ["HOMEPILOT_ACCESS_PARTNER_TOKEN", "HOMEPILOT_ACCESS_PARTNER_PASSWORD"],
                            "purpose": "Short-lived JWT token or password for planned partner access probe.",
                            "required_for_live": True,
                            "current_status": "missing",
                            "secret_value_required": True,
                            "email": "partner@example.com",
                            "role": "partner",
                            "access_scope": "partner",
                        },
                    ],
                },
                live_proof_plan={"status": "blocked_until_live_inputs", "secret_scan": {"status": "pass"}},
                production_proof={"production_gate": {"verified": False}},
                release_label="credential-test",
            )
            report = json.loads(Path(pack["paths"]["live_credential_handoff"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
            checklist = Path(pack["paths"]["checklist_csv"]).read_text(encoding="utf-8")
            channel_contract = Path(pack["paths"]["secret_channel_contract"]).read_text(encoding="utf-8")
            combined = json.dumps(report).lower() + markdown.lower() + checklist.lower() + channel_contract.lower()

        self.assertEqual(report["handoff_type"], "homepilot_live_credential_handoff")
        self.assertEqual(report["status"], "handoff_required")
        self.assertEqual(report["summary"]["task_count"], 3)
        self.assertEqual(report["summary"]["secret_task_count"], 2)
        self.assertEqual(report["summary"]["env_var_count"], 6)
        self.assertFalse(report["summary"]["production_verified"])
        self.assertEqual(report["summary"]["production_verified_label"], "production_verified=false")
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertTrue(report["guardrails"]["env_var_names_only"])
        self.assertTrue(report["guardrails"]["no_secret_values"])
        self.assertTrue(report["guardrails"]["no_raw_contact_data"])
        self.assertIn("HomePilot Live Credential Handoff", markdown)
        self.assertIn("HOMEPILOT_SUPABASE_URL", checklist)
        self.assertIn("HOMEPILOT_ACCESS_PARTNER_TOKEN", channel_contract)
        self.assertIn("approved customer secret manager", channel_contract)
        self.assertIn("portable data room", channel_contract)
        self.assertIn("customer_access_verification", channel_contract)
        self.assertNotIn("@example.com", combined)
        self.assertNotIn("partner@example", combined)
        self.assertNotIn("service_role=", combined)
        self.assertNotIn("authorization: bearer", combined)

    def test_portal_bundle_secret_scan_blocks_public_service_role_markers(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Secret Portal",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            portal_dir = root / "portal"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Secret Portal",
                tenant_slug="window-secret-portal",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            (package_dir / "dashboard" / "dashboard-data.js").write_text("const leaked = 'service-role-key';\n", encoding="utf-8")
            portal = build_portal_bundle(Path(manifest["paths"]["manifest"]), portal_dir)

        self.assertEqual(portal["status"], "fail")
        self.assertEqual(portal["checks"]["secret_scan"]["status"], "fail")
        self.assertTrue(any("Secret-like values" in failure for failure in portal["failures"]))

    def test_enrichment_pack_builds_vendor_coverage_and_backlog_from_customer_package(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Enrichment Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            enrichment_dir = root / "enrichment"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Enrichment Customer",
                tenant_slug="window-enrichment-customer",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            pack = build_enrichment_pack(Path(manifest["paths"]["manifest"]), enrichment_dir)
            plan = json.loads((enrichment_dir / "data_vendor_plan.json").read_text(encoding="utf-8"))
            backlog = (enrichment_dir / "enrichment_backlog.csv").read_text(encoding="utf-8-sig")
            markdown = (enrichment_dir / "DATA_VENDOR_PLAN.md").read_text(encoding="utf-8")

        coverage = {row["key"]: row for row in plan["coverage"]}
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["review_status"], "ready_with_backlog")
        self.assertEqual(plan["summary"]["categories"], 7)
        self.assertGreater(plan["summary"]["backlog_items"], 0)
        self.assertEqual(coverage["geocode"]["coverage_pct"], 100.0)
        self.assertEqual(coverage["imagery"]["coverage_pct"], 100.0)
        self.assertEqual(coverage["pricing_estimate"]["coverage_pct"], 100.0)
        self.assertEqual(coverage["permit_history"]["missing"], 1)
        self.assertFalse(plan["guardrails"]["vendor_credentials_included"])
        self.assertTrue(plan["guardrails"]["license_review_required_before_production"])
        self.assertIn("HomePilot Data Vendor And Enrichment Plan", markdown)
        self.assertIn("permit_history", backlog)
        self.assertNotIn("bearer ", markdown.lower())
        self.assertNotIn("private key", markdown.lower())

    def test_enrichment_refresh_dry_run_builds_secret_safe_job_evidence(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Refresh Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            enrichment_dir = root / "enrichment"
            refresh_dir = root / "refresh"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Refresh Customer",
                tenant_slug="window-refresh-customer",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            pack = build_enrichment_pack(Path(manifest["paths"]["manifest"]), enrichment_dir)
            report = build_enrichment_refresh_pack(Path(pack["paths"]["data_vendor_plan"]), refresh_dir, live=False, env={})
            saved = json.loads((refresh_dir / "enrichment_refresh_report.json").read_text(encoding="utf-8"))
            jobs = [json.loads(line) for line in (refresh_dir / "refresh_jobs.jsonl").read_text(encoding="utf-8").splitlines()]
            attempts = [json.loads(line) for line in (refresh_dir / "delivery_attempts.jsonl").read_text(encoding="utf-8").splitlines()]
            runbook = (refresh_dir / "ENRICHMENT_REFRESH_RUNBOOK.md").read_text(encoding="utf-8")
            combined_output = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in refresh_dir.iterdir() if path.is_file())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(saved["mode"], "dry_run")
        self.assertGreater(saved["summary"]["jobs"], 0)
        self.assertEqual(saved["summary"]["dry_run"], saved["summary"]["jobs"])
        self.assertFalse(saved["summary"]["live_api_calls_made"])
        self.assertTrue(all(job["event_type"] == "homepilot.enrichment.refresh" for job in jobs))
        self.assertTrue(all(job["guardrails"]["credentials_in_payload"] is False for job in jobs))
        self.assertEqual(attempts[0]["status"], "dry_run")
        self.assertIn("HomePilot Enrichment Refresh Runbook", runbook)
        self.assertNotIn("secret-token", combined_output)
        self.assertNotIn("service-role", combined_output.lower())

    def test_enrichment_refresh_live_uses_env_credentials_without_writing_them(self) -> None:
        calls = []

        def fake_sender(url: str, payload: dict, headers: dict, timeout: int) -> dict:
            calls.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
            return {"status_code": 202, "body": "accepted"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "data_vendor_plan.json"
            plan_path.write_text(json.dumps({
                "status": "pass",
                "tenant": {"id": "tenant_live_refresh"},
                "source_requirements": [{
                    "key": "geocode",
                    "label": "Geocode and map placement",
                    "freshness_sla": "before every campaign import",
                    "license_review": "confirm display/export rights",
                    "vendor_options": ["geocoder"],
                }],
                "backlog": [{
                    "property_id": "prop_live_refresh",
                    "address": "Live Refresh 1",
                    "city": "Leuven",
                    "category": "geocode",
                    "label": "Geocode and map placement",
                    "recommended_sources": "geocoder",
                    "priority": "high",
                }],
            }), encoding="utf-8")
            report = build_enrichment_refresh_pack(
                plan_path,
                root / "refresh",
                live=True,
                env={
                    "HOMEPILOT_ENRICHMENT_WEBHOOK_URL": "https://vendor.example.test/hooks/enrichment",
                    "HOMEPILOT_ENRICHMENT_API_KEY": "secret-token-value",
                },
                sender=fake_sender,
            )
            combined_output = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (root / "refresh").iterdir() if path.is_file())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["mode"], "live")
        self.assertEqual(report["summary"]["sent"], 1)
        self.assertTrue(report["summary"]["live_api_calls_made"])
        self.assertEqual(report["credentials"]["endpoint_host"], "vendor.example.test")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer secret-token-value")
        self.assertNotIn("secret-token-value", combined_output)

    def test_enrichment_refresh_live_requires_endpoint_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "data_vendor_plan.json"
            plan_path.write_text(json.dumps({
                "status": "pass",
                "tenant": {"id": "tenant_missing_endpoint"},
                "source_requirements": [],
                "backlog": [{
                    "property_id": "prop_missing_endpoint",
                    "address": "Missing Endpoint 1",
                    "city": "Leuven",
                    "category": "geocode",
                    "label": "Geocode",
                    "recommended_sources": "geocoder",
                    "priority": "high",
                }],
            }), encoding="utf-8")
            report = build_enrichment_refresh_pack(plan_path, root / "refresh", live=True, env={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["checks"]["credentials"], "fail")
        self.assertTrue(any("HOMEPILOT_ENRICHMENT_WEBHOOK_URL" in failure for failure in report["failures"]))

    def test_enrichment_plan_fails_when_payload_is_not_tenant_scoped(self) -> None:
        payload = base_payload()
        second_tenant = canonical_tenant_id("tenant_b")
        payload["properties"].append({
            **payload["properties"][0],
            "id": "prop_2",
            "tenant_id": second_tenant,
            "address": "Tweede Teststraat 2",
        })
        plan = build_enrichment_plan(payload, tenant={"id": "mixed"})

        self.assertEqual(plan["status"], "fail")
        self.assertEqual(plan["review_status"], "action_required")
        self.assertTrue(any("exactly one scoped tenant" in failure for failure in plan["failures"]))

    def test_integration_pack_builds_crm_and_webhook_handoff_artifacts(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Integration Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            integration_dir = root / "integration"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Integration Customer",
                tenant_slug="window-integration-customer",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            pack = build_integration_pack(Path(manifest["paths"]["manifest"]), integration_dir)
            with (integration_dir / "crm_leads.csv").open("r", encoding="utf-8-sig") as handle:
                crm_rows = list(csv.DictReader(handle))
            webhook_rows = [json.loads(line) for line in (integration_dir / "webhook_payloads.jsonl").read_text(encoding="utf-8").splitlines()]
            mapping = json.loads((integration_dir / "field_mapping.json").read_text(encoding="utf-8"))
            runbook = (integration_dir / "INTEGRATION_RUNBOOK.md").read_text(encoding="utf-8")
            combined_output = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in integration_dir.iterdir() if path.is_file())

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["counts"]["crm_rows"], 1)
        self.assertEqual(pack["counts"]["webhook_payloads"], 1)
        self.assertEqual(pack["checks"]["secret_scan"]["status"], "pass")
        self.assertEqual(pack["checks"]["tenant_scope"]["status"], "pass")
        self.assertEqual(pack["checks"]["module_scope"]["enabled_modules"], ["windowpilot"])
        self.assertIn("hubspot", mapping)
        self.assertIn("pipedrive", mapping)
        self.assertIn("salesforce", mapping)
        self.assertEqual(crm_rows[0]["best_module"], "windowpilot")
        self.assertEqual(webhook_rows[0]["event_type"], "homepilot.opportunity.upsert")
        self.assertEqual(webhook_rows[0]["idempotency_key"], crm_rows[0]["integration_record_id"])
        self.assertIn("HomePilot Sales Integration Runbook", runbook)
        self.assertNotIn("facadepilot", json.dumps(crm_rows).lower())
        self.assertNotIn("service-role", combined_output.lower())

    def test_integration_pack_secret_scan_blocks_public_secret_markers(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Secret Integration",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        payload = base_payload()
        for target in payload["campaign_targets"]:
            if target["module_key"] == "windowpilot":
                target.setdefault("metadata", {})["next_action"] = "Do not export service-role-key"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            integration_dir = root / "integration"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Secret Integration",
                tenant_slug="window-secret-integration",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            pack = build_integration_pack(Path(manifest["paths"]["manifest"]), integration_dir)

        self.assertEqual(pack["status"], "fail")
        self.assertEqual(pack["checks"]["secret_scan"]["status"], "fail")
        self.assertTrue(any("Secret-like values" in failure for failure in pack["failures"]))

    def test_integration_sync_dry_run_builds_secret_safe_delivery_evidence(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Sync Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            integration_dir = root / "integration"
            sync_dir = root / "sync"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Sync Customer",
                tenant_slug="window-sync-customer",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            integration = build_integration_pack(Path(manifest["paths"]["manifest"]), integration_dir)
            report = build_integration_sync_pack(Path(integration["paths"]["integration_manifest"]), sync_dir, live=False, env={})
            saved = json.loads((sync_dir / "sync_report.json").read_text(encoding="utf-8"))
            attempts = [json.loads(line) for line in (sync_dir / "delivery_attempts.jsonl").read_text(encoding="utf-8").splitlines()]
            runbook = (sync_dir / "SYNC_RUNBOOK.md").read_text(encoding="utf-8")
            combined_output = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in sync_dir.iterdir() if path.is_file())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(saved["mode"], "dry_run")
        self.assertEqual(saved["summary"]["payloads"], 1)
        self.assertEqual(saved["summary"]["dry_run"], 1)
        self.assertFalse(saved["summary"]["live_api_calls_made"])
        self.assertEqual(attempts[0]["status"], "dry_run")
        self.assertIn("HomePilot CRM/Webhook Sync Report", runbook)
        self.assertNotIn("secret-token", combined_output)
        self.assertNotIn("service-role", combined_output.lower())

    def test_integration_sync_live_uses_env_credentials_without_writing_them(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Live Sync Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        calls = []

        def fake_sender(url: str, payload: dict, headers: dict, timeout: int) -> dict:
            calls.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
            return {"status_code": 202, "body": "accepted"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            onboarding_path = root / "onboarding.json"
            payload_path = root / "payload.json"
            package_dir = root / "package"
            integration_dir = root / "integration"
            sync_dir = root / "sync"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Live Sync Customer",
                tenant_slug="window-live-sync-customer",
                modules=["windowpilot"],
                include_xlsx=False,
            )
            integration = build_integration_pack(Path(manifest["paths"]["manifest"]), integration_dir)
            report = build_integration_sync_pack(
                Path(integration["paths"]["integration_manifest"]),
                sync_dir,
                live=True,
                env={
                    "HOMEPILOT_CRM_WEBHOOK_URL": "https://crm.example.test/hooks/homepilot",
                    "HOMEPILOT_CRM_API_KEY": "secret-token-value",
                },
                sender=fake_sender,
            )
            combined_output = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in sync_dir.iterdir() if path.is_file())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["mode"], "live")
        self.assertEqual(report["summary"]["sent"], 1)
        self.assertTrue(report["summary"]["live_api_calls_made"])
        self.assertEqual(report["credentials"]["webhook_host"], "crm.example.test")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer secret-token-value")
        self.assertNotIn("secret-token-value", combined_output)

    def test_integration_sync_live_requires_webhook_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "integration_manifest.json"
            webhook_path = root / "webhook_payloads.jsonl"
            webhook_path.write_text(json.dumps({
                "event_type": "homepilot.opportunity.upsert",
                "idempotency_key": "sync-missing-url",
                "guardrails": {"tenant_scoped": True, "module_scoped": True},
            }) + "\n", encoding="utf-8")
            manifest_path.write_text(json.dumps({
                "status": "pass",
                "paths": {"webhook_jsonl": str(webhook_path)},
            }), encoding="utf-8")
            report = build_integration_sync_pack(manifest_path, root / "sync", live=True, env={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["checks"]["credentials"], "fail")
        self.assertTrue(any("HOMEPILOT_CRM_WEBHOOK_URL" in failure for failure in report["failures"]))

    def test_entitlement_filter_removes_disabled_module_records_and_orphan_properties(self) -> None:
        payload = base_payload()
        tenant_id = payload["properties"][0]["tenant_id"]
        facade_only_campaign = canonical_campaign_id(tenant_id, "facadepilot", "facade_only")
        payload["campaigns"].append({
            "id": facade_only_campaign,
            "tenant_id": tenant_id,
            "name": "Facade only",
            "module_key": "facadepilot",
        })
        payload["properties"].append({
            "id": "prop_facade_only",
            "tenant_id": tenant_id,
            "address": "Gevel Alleen 9",
            "city": "Leuven",
            "lat": 50.89,
            "lon": 4.71,
            "property_type": "open",
            "tags": ["facade-only"],
            "core": {},
        })
        payload["assessments"].append({
            "id": "asmt_facade_only",
            "tenant_id": tenant_id,
            "property_id": "prop_facade_only",
            "module_key": "facadepilot",
            "score": 88,
            "grade": "A",
            "confidence": 0.8,
            "metrics": {"facade_preset": "Crepi"},
            "evidence": [{"type": "note", "value": "Facade only"}],
        })
        payload["campaign_targets"].append({
            "tenant_id": tenant_id,
            "campaign_id": facade_only_campaign,
            "property_id": "prop_facade_only",
            "module_key": "facadepilot",
            "status": "sent",
            "priority_score": 88,
            "priority_grade": "A",
        })

        scoped = filter_payload_for_entitlements(
            payload,
            tenant_ids={tenant_id},
            enabled_modules=["windowpilot"],
        )

        validate_payload(scoped)
        self.assertEqual([row["module_key"] for row in scoped["campaigns"]], ["windowpilot"])
        self.assertEqual([row["module_key"] for row in scoped["assessments"]], ["windowpilot"])
        self.assertEqual([row["module_key"] for row in scoped["campaign_targets"]], ["windowpilot"])
        self.assertEqual([row["module_key"] for row in scoped["interactions"]], ["windowpilot"])
        self.assertEqual([row["id"] for row in scoped["properties"]], ["prop_1"])
        self.assertNotIn("facadepilot", json.dumps(scoped).lower())
        self.assertNotIn("Gevel Alleen", json.dumps(scoped))

    def test_customer_package_derives_modules_from_onboarding_when_modules_omitted(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            onboarding_path = tmp_path / "onboarding.json"
            payload_path = tmp_path / "payload.json"
            package_dir = tmp_path / "package"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            raw_payload = base_payload()
            raw_payload["assessments"][1]["metrics"]["internal_model_prompt"] = "secret prompt"
            payload_path.write_text(json.dumps(raw_payload), encoding="utf-8")

            manifest = build_customer_package(
                onboarding_path=onboarding_path,
                payload_path=payload_path,
                output_dir=package_dir,
                tenant_name="Window Customer",
                tenant_slug="window-customer",
                include_xlsx=False,
                audit_payload=True,
            )

            scoped_payload = json.loads((package_dir / "data" / "scoped_payload.json").read_text(encoding="utf-8"))
            dashboard_data = (package_dir / "dashboard" / "dashboard-data.js").read_text(encoding="utf-8").lower()

        self.assertEqual(manifest["modules"], ["windowpilot"])
        self.assertEqual(manifest["access_audit"]["status"], "pass")
        self.assertEqual(manifest["source_scope"]["enabled_modules"], ["windowpilot"])
        self.assertEqual(manifest["source_scope"]["scoped_summary"]["modules"], {"windowpilot": 1})
        self.assertNotIn("facadepilot", json.dumps(scoped_payload).lower())
        self.assertNotIn("facadepilot", dashboard_data)
        self.assertNotIn("secret prompt", json.dumps(scoped_payload).lower())
        self.assertNotIn("internal_model_prompt", json.dumps(scoped_payload).lower())
        self.assertNotIn("secret prompt", dashboard_data)

    def test_generic_pilot_csv_converts_windowpilot_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "windowpilot.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "address",
                    "city",
                    "lat",
                    "lon",
                    "window_opportunity_score",
                    "grade",
                    "replacement_urgency",
                    "visible_window_count",
                    "status",
                    "next_action",
                    "render_url",
                ])
                writer.writeheader()
                writer.writerow({
                    "address": "Vensterstraat 7",
                    "city": "Leuven",
                    "lat": "50.87",
                    "lon": "4.70",
                    "window_opportunity_score": "91",
                    "grade": "A+",
                    "replacement_urgency": "Old glazing",
                    "visible_window_count": "12",
                    "status": "responded",
                    "next_action": "Call about glazing",
                    "render_url": "https://example.com/window-render.jpg",
                })
            payload = convert_pilot_csv(
                csv_path=csv_path,
                module_key="windowpilot",
                tenant_id="window-customer",
                campaign_id="window-q3",
                campaign_name="Window Q3",
            )
        validate_payload(payload)
        self.assertEqual(payload["campaigns"][0]["module_key"], "windowpilot")
        self.assertEqual(payload["campaigns"][0]["name"], "Window Q3")
        self.assertEqual(payload["assessments"][0]["module_key"], "windowpilot")
        self.assertEqual(payload["assessments"][0]["score"], 91.0)
        self.assertEqual(payload["assessments"][0]["metrics"]["visible_window_count"], 12.0)
        self.assertEqual(payload["campaign_targets"][0]["status"], "responded")
        self.assertEqual(payload["campaign_targets"][0]["metadata"]["next_action"], "Call about glazing")

        onboarding = build_onboarding_payload(
            name="Window Customer",
            slug="window-customer",
            modules=["windowpilot"],
        )
        snapshot = build_dashboard_snapshot(payload, enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            onboarding_path = tmp_path / "onboarding.json"
            snapshot_path = tmp_path / "snapshot.json"
            payload_path = tmp_path / "payload.json"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            report = build_access_audit(onboarding_path, payload_path=payload_path, snapshot_path=snapshot_path)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["matrix"]["windowpilot"]["payload"], 3)

    def test_access_audit_passes_for_filtered_window_snapshot(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        snapshot = build_dashboard_snapshot(base_payload(), enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            onboarding_path = tmp_path / "onboarding.json"
            snapshot_path = tmp_path / "snapshot.json"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            report = build_access_audit(onboarding_path, snapshot_path=snapshot_path)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["enabled_modules"], ["windowpilot"])
        self.assertEqual(report["matrix"]["windowpilot"]["snapshot"], 1)
        self.assertEqual(report["matrix"]["facadepilot"]["snapshot"], 0)

    def test_access_audit_fails_when_payload_contains_disabled_module(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Customer",
            slug="tenant_a",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            onboarding_path = tmp_path / "onboarding.json"
            payload_path = tmp_path / "payload.json"
            onboarding_path.write_text(json.dumps(onboarding), encoding="utf-8")
            payload_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            report = build_access_audit(onboarding_path, payload_path=payload_path)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("facadepilot" in issue for issue in report["issues"]))

    def test_onboarding_payload_enables_only_purchased_modules(self) -> None:
        owner_id = "11111111-1111-4111-8111-111111111111"
        payload = build_onboarding_payload(
            name="Window Customer",
            slug="window-customer",
            modules=["windowpilot"],
            memberships=[f"{owner_id}:owner"],
        )
        summary = summarize_onboarding_payload(payload)
        self.assertEqual(summary["tenants"], 1)
        self.assertEqual(summary["tenant_modules"], 1)
        self.assertEqual(summary["memberships"], 1)
        self.assertEqual(summary["modules"], ["windowpilot"])
        self.assertEqual(payload["tenant_modules"][0]["module_key"], "windowpilot")
        self.assertEqual(payload["memberships"][0]["role"], "owner")
        self.assertEqual(payload["tenants"][0]["id"], canonical_tenant_id("window-customer"))

    def test_payload_validation_rejects_non_uuid_tenant_ids(self) -> None:
        payload = base_payload()
        payload["properties"][0]["tenant_id"] = "not-a-tenant-uuid"
        with self.assertRaises(ValueError):
            validate_payload(payload)

    def test_module_primary_score_keys_exist_in_metric_catalog(self) -> None:
        for module_key, definition in PILOT_MODULES.items():
            metric_keys = {metric.key for metric in definition.metrics}
            self.assertIn(definition.primary_score_key, metric_keys, module_key)
            self.assertEqual(len(metric_keys), len(definition.metrics), module_key)

    def test_product_access_matrix_scopes_role_modules_and_metrics(self) -> None:
        matrix = build_product_access_matrix(
            enabled_modules=["windowpilot"],
            role="viewer",
            surface="dashboard",
        )
        self.assertEqual(matrix["role"], "viewer")
        self.assertIn("dashboard_read", matrix["permissions"])
        self.assertEqual([module["key"] for module in matrix["modules"]], ["windowpilot"])
        visible_keys = {metric["key"] for metric in matrix["modules"][0]["visible_metrics"]}
        self.assertIn("window_opportunity_score", visible_keys)
        self.assertNotIn("facadepilot", json.dumps(matrix).lower())

    def test_customer_view_catalog_explains_scoped_lenses_without_authorizing_live_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build_customer_view_catalog_pack(
                out_dir=Path(tmp),
                due_diligence={"modules": ["windowpilot"]},
                account_access_plan={
                    "status": "pass",
                    "review_status": "ready",
                    "scope_counts": {"tenant": 1, "partner": 1},
                    "role_counts": {"owner": 1, "manager": 1},
                },
                portal_manifest={
                    "status": "pass",
                    "live_runtime": {
                        "status": "ready_for_customer_auth_config",
                        "enabled_by_default": False,
                    },
                },
                partner_access_reconciliation={
                    "production_ready": False,
                    "summary": {"blockers": 1},
                },
                customer_signoff_reconciliation={
                    "status": "blocked_until_customer_signoff_and_live_proof",
                    "summary": {"signed_decision_count": 0, "decision_count": 10},
                },
                production_proof={"production_gate": {"verified": False}},
                release_label="catalog-test",
            )
            markdown = Path(catalog["paths"]["customer_view_catalog_markdown"]).read_text(encoding="utf-8")
            matrix_csv = Path(catalog["paths"]["customer_view_matrix"]).read_text(encoding="utf-8")

        views_by_key = {row["view_key"]: row for row in catalog["views"]}
        self.assertEqual(catalog["status"], "buyer_review_ready_live_access_blocked")
        self.assertEqual(catalog["modules"], ["windowpilot"])
        self.assertFalse(catalog["summary"]["live_access_ready"])
        self.assertEqual(catalog["summary"]["portal_runtime_status"], "static_portal_ready_live_runtime_disabled")
        self.assertTrue(catalog["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertTrue(catalog["guardrails"]["catalog_is_not_runtime_authorization"])
        self.assertEqual(catalog["secret_scan"]["status"], "pass")
        self.assertIn("assigned records only", views_by_key["partner_renovator"]["partner_scope"].lower())
        self.assertIn("other partner raw addresses", "; ".join(views_by_key["partner_renovator"]["blocked_visibility"]))
        self.assertIn("windowpilot", views_by_key["module_only_customer"]["module_scope"])
        self.assertNotIn("facadepilot", json.dumps(catalog["metric_access"]["dashboard"]).lower())
        self.assertIn("HomePilot Customer View Catalog", markdown)
        self.assertIn("Supabase RLS", markdown)
        self.assertIn("partner_renovator", matrix_csv)
        self.assertIn("assigned records only", matrix_csv.lower())
        self.assertNotIn("@example.com", markdown + matrix_csv)

    def test_data_platform_blueprint_explains_shared_spine_without_live_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blueprint = build_data_platform_blueprint_pack(
                Path(tmp),
                due_diligence={"modules": ["facadepilot"]},
                readiness={"gates": [{"name": "customer_package_smoke", "status": "pass"}]},
                production_proof={"production_gate": {"verified": False}},
                release_label="blueprint-test",
            )
            markdown = Path(blueprint["paths"]["data_platform_blueprint_markdown"]).read_text(encoding="utf-8")
            scope_matrix = Path(blueprint["paths"]["data_platform_scope_matrix"]).read_text(encoding="utf-8")

        modules_by_key = {row["module_key"]: row for row in blueprint["modules"]}
        layers_by_key = {row["key"]: row for row in blueprint["data_layers"]}
        lenses_by_key = {row["key"]: row for row in blueprint["access_lenses"]}
        self.assertEqual(blueprint["status"], "buyer_review_ready_live_proof_required")
        self.assertEqual(blueprint["secret_scan"]["status"], "pass")
        self.assertEqual(blueprint["summary"]["module_count"], len(PILOT_MODULES))
        self.assertFalse(blueprint["summary"]["production_verified"])
        self.assertEqual(blueprint["summary"]["production_verified_label"], "production_verified=false")
        self.assertTrue(modules_by_key["facadepilot"]["enabled_in_current_customer_scope"])
        self.assertFalse(modules_by_key["windowpilot"]["enabled_in_current_customer_scope"])
        self.assertEqual(layers_by_key["campaign_funnel"]["required_keys"][-1], "partner_id")
        self.assertIn("assigned campaign records", lenses_by_key["partner_renovator"]["scope"])
        self.assertTrue(blueprint["guardrails"]["tenant_id_required"])
        self.assertTrue(blueprint["guardrails"]["module_key_required_for_module_rows"])
        self.assertTrue(blueprint["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertTrue(blueprint["guardrails"]["no_cross_tenant_raw_learning"])
        self.assertIn("HomePilot Data Platform Blueprint", markdown)
        self.assertIn("tenant -> modules -> campaigns -> properties -> assessments -> interactions", markdown)
        self.assertIn("FacadePilot", markdown)
        self.assertIn("DrivewayPilot", markdown)
        self.assertIn("partner_renovator", scope_matrix)
        self.assertIn("homepilot_campaign_targets", markdown)
        self.assertIn("production_verified=true", markdown)
        self.assertNotIn("service_role=", markdown + scope_matrix)
        self.assertNotIn("@example.com", markdown + scope_matrix)

    def test_module_readiness_matrix_covers_all_pilots_without_live_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            matrix = build_module_readiness_matrix_pack(
                Path(tmp),
                due_diligence={"modules": ["facadepilot"]},
                production_proof={"production_gate": {"verified": False}},
                release_label="module-matrix-test",
            )
            markdown = Path(matrix["paths"]["markdown"]).read_text(encoding="utf-8")
            matrix_csv = Path(matrix["paths"]["matrix_csv"]).read_text(encoding="utf-8")
            metric_coverage = Path(matrix["paths"]["metric_coverage_csv"]).read_text(encoding="utf-8")

        modules_by_key = {row["module_key"]: row for row in matrix["modules"]}
        self.assertEqual(matrix["matrix_type"], "homepilot_module_readiness_matrix")
        self.assertEqual(matrix["status"], "buyer_review_ready_live_proof_required")
        self.assertEqual(matrix["summary"]["module_count"], len(PILOT_MODULES))
        self.assertEqual(matrix["summary"]["enabled_module_count"], 1)
        self.assertEqual(matrix["summary"]["buyer_ready_count"], len(PILOT_MODULES))
        self.assertEqual(matrix["summary"]["production_ready_count"], 0)
        self.assertEqual(matrix["summary"]["production_verified_label"], "production_verified=false")
        self.assertEqual(matrix["secret_scan"]["status"], "pass")
        self.assertTrue(matrix["guardrails"]["tenant_id_required"])
        self.assertTrue(matrix["guardrails"]["module_key_required"])
        self.assertTrue(matrix["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertTrue(matrix["guardrails"]["benchmark_metrics_aggregate_only"])
        self.assertTrue(modules_by_key["facadepilot"]["enabled_in_current_customer_scope"])
        self.assertFalse(modules_by_key["windowpilot"]["enabled_in_current_customer_scope"])
        self.assertEqual(modules_by_key["windowpilot"]["overall_status"], "catalog_ready_not_entitled_for_current_customer")
        self.assertIn("HomePilot Module Readiness Matrix", markdown)
        self.assertIn("WindowPilot", markdown)
        self.assertIn("DrivewayPilot", markdown)
        self.assertIn("MODULE_METRIC_COVERAGE", markdown)
        self.assertIn("facade_opportunity_score", metric_coverage)
        self.assertIn("module_key,label,category", matrix_csv)
        self.assertNotIn("@example.com", markdown + matrix_csv + metric_coverage)
        self.assertNotIn("service_role=", markdown + matrix_csv + metric_coverage)

    def test_metric_filter_hides_unknown_internal_metrics_by_default(self) -> None:
        metrics = filter_metrics_for_surface("windowpilot", {
            "window_opportunity_score": 91,
            "replacement_urgency": "Old glazing",
            "estimated_value": 36000,
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
        })
        self.assertEqual(metrics["window_opportunity_score"], 91)
        self.assertEqual(metrics["estimated_value"], 36000)
        self.assertNotIn("internal_model_prompt", metrics)
        self.assertNotIn("raw_feature_dump", metrics)

    def test_data_dictionary_covers_metrics_surfaces_views_and_exports(self) -> None:
        dictionary = build_data_dictionary(modules=["facadepilot", "windowpilot"])
        self.assertEqual(dictionary["status"], "pass")
        self.assertEqual(dictionary["modules_selected"], ["facadepilot", "windowpilot"])
        metric_keys = {metric["metric_key"] for metric in dictionary["metrics"]}
        export_columns = {column["column"] for column in dictionary["export_columns"]}
        views = {view["view"] for view in dictionary["views"]}
        view_columns = {
            view["view"]: set(view["columns"])
            for view in dictionary["views"]
        }
        self.assertIn("facade_preset", metric_keys)
        self.assertIn("replacement_urgency", metric_keys)
        self.assertIn("dashboard", dictionary["surfaces"])
        self.assertIn("export", dictionary["surfaces"])
        self.assertIn("benchmark", dictionary["surfaces"])
        self.assertIn("address", export_columns)
        self.assertIn("best_score", export_columns)
        self.assertIn("metrics_json", export_columns)
        self.assertIn("homepilot_property_intelligence", views)
        self.assertIn("homepilot_property_public_enrichment", views)
        self.assertIn("homepilot_second_brain_edges", views)
        self.assertIn("licence", view_columns["homepilot_property_public_enrichment"])
        self.assertIn("allowed_use", view_columns["homepilot_property_public_enrichment"])
        self.assertIn("provenance", view_columns["homepilot_property_public_enrichment"])
        self.assertIn("contacted_count", view_columns["homepilot_module_metrics"])
        self.assertIn("target_response_rate_pct", view_columns["homepilot_campaign_metrics"])
        self.assertIn("target_response_rate_pct", view_columns["homepilot_module_metrics"])
        self.assertNotIn("internal_model_prompt", json.dumps(dictionary).lower())

    def test_api_contract_documents_customer_read_models_without_service_role(self) -> None:
        contract = build_api_contract(modules=["windowpilot"], base_url="https://example.supabase.co")
        self.assertEqual(contract["status"], "pass")
        self.assertEqual(contract["modules_selected"], ["windowpilot"])
        views = {endpoint["view"] for endpoint in contract["endpoints"]}
        self.assertEqual(contract["counts"]["endpoints"], 6)
        self.assertIn("homepilot_property_intelligence", views)
        self.assertIn("homepilot_property_export", views)
        self.assertIn("homepilot_property_public_enrichment", views)
        self.assertIn("homepilot_second_brain_edges", views)
        campaign_endpoint = next(endpoint for endpoint in contract["endpoints"] if endpoint["view"] == "homepilot_campaign_metrics")
        module_endpoint = next(endpoint for endpoint in contract["endpoints"] if endpoint["view"] == "homepilot_module_metrics")
        enrichment_endpoint = next(endpoint for endpoint in contract["endpoints"] if endpoint["view"] == "homepilot_property_public_enrichment")
        self.assertIn("source_name", enrichment_endpoint["default_select"])
        self.assertIn("licence", enrichment_endpoint["default_select"])
        self.assertIn("allowed_use", enrichment_endpoint["default_select"])
        self.assertIn("target_response_rate_pct", campaign_endpoint["default_select"])
        self.assertIn("contacted_count", module_endpoint["default_select"])
        self.assertIn("target_response_rate_pct", module_endpoint["default_select"])
        for endpoint in contract["endpoints"]:
            self.assertEqual(endpoint["method"], "GET")
            self.assertIn("Authorization", endpoint["required_headers"])
            self.assertIn("apikey", endpoint["required_headers"])
            self.assertIn("customer-jwt", json.dumps(endpoint).lower())
        self.assertNotIn("service-role", json.dumps(contract).lower())

    def test_api_contract_pack_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_api_contract_pack(Path(tmp), modules=["facadepilot"])
            contract = json.loads(Path(pack["paths"]["api_contract"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(contract["modules_selected"], ["facadepilot"])
        self.assertIn("HomePilot Customer API Contract", markdown)
        self.assertIn("homepilot_property_intelligence", markdown)

    def test_processing_register_documents_activities_controls_and_risks(self) -> None:
        register = build_processing_register(modules=["windowpilot"])
        activity_keys = {activity["key"] for activity in register["processing_activities"]}
        control_keys = {control["key"] for control in register["controls"]}
        risk_text = json.dumps(register["risk_register"]).lower()
        self.assertEqual(register["status"], "pass")
        self.assertEqual(register["modules_selected"], ["windowpilot"])
        self.assertIn("property_intelligence", activity_keys)
        self.assertIn("campaign_outreach_memory", activity_keys)
        self.assertIn("tenant_rls", control_keys)
        self.assertIn("retention_lifecycle", control_keys)
        self.assertIn("cross-tenant", risk_text)
        self.assertTrue(register["not_legal_advice"])

    def test_processing_register_pack_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_processing_register_pack(Path(tmp), modules=["windowpilot", "facadepilot"])
            register = json.loads(Path(pack["paths"]["processing_register"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(register["modules_selected"], ["facadepilot", "windowpilot"])
        self.assertIn("HomePilot Data Processing Register", markdown)
        self.assertIn("Processing Activities", markdown)

    def test_customer_brief_builds_boardroom_summary_from_scoped_snapshot(self) -> None:
        payload = base_payload()
        payload["assessments"][1]["metrics"].update({
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
            "estimated_value": 36000,
        })
        snapshot = build_dashboard_snapshot(payload, tenant_name="Window Customer", enabled_modules=["windowpilot"])
        brief = build_customer_brief(snapshot)
        body = json.dumps(brief).lower()
        self.assertEqual(brief["status"], "pass")
        self.assertEqual(brief["tenant"]["modules"], ["windowpilot"])
        self.assertEqual(brief["scorecard"]["property_count"], 1)
        self.assertEqual(brief["scorecard"]["top_module"], "windowpilot")
        self.assertIn("campaign_learnings", brief)
        self.assertIn("action_plan", brief)
        self.assertNotIn("score_total", body)
        self.assertNotIn("facadepilot", body)
        self.assertNotIn("secret prompt", body)
        self.assertNotIn("private raw features", body)

    def test_boardroom_response_rate_uses_contacted_denominator(self) -> None:
        payload = base_payload()
        tenant_id = payload["properties"][0]["tenant_id"]
        window_campaign = payload["campaigns"][1]["id"]
        payload["properties"].append({
            "id": "prop_2",
            "tenant_id": tenant_id,
            "address": "Teststraat 2",
            "city": "Leuven",
            "lat": 50.89,
            "lon": 4.71,
            "property_type": "rijwoning",
            "tags": ["pre-1990"],
            "core": {},
        })
        payload["assessments"].append({
            "id": "asmt_window_2",
            "tenant_id": tenant_id,
            "property_id": "prop_2",
            "module_key": "windowpilot",
            "score": 76,
            "grade": "B",
            "confidence": 0.74,
            "metrics": {"replacement_urgency": "Review", "estimated_value": 28000},
            "evidence": [{"type": "render", "value": "window-2.jpg"}],
        })
        payload["campaign_targets"].append({
            "tenant_id": tenant_id,
            "campaign_id": window_campaign,
            "property_id": "prop_2",
            "module_key": "windowpilot",
            "status": "generated",
            "priority_score": 76,
            "priority_grade": "B",
            "metadata": {},
        })
        snapshot = build_dashboard_snapshot(payload, tenant_name="Window Customer", enabled_modules=["windowpilot"])
        report = build_boardroom_report(snapshot)
        module_row = next(row for row in report["module_rows"] if row["module_key"] == "windowpilot")
        self.assertEqual(report["summary"]["properties"], 2)
        self.assertEqual(report["summary"]["contacted"], 1)
        self.assertEqual(report["summary"]["responses"], 1)
        self.assertEqual(report["summary"]["response_rate_pct"], 100.0)
        self.assertEqual(module_row["contacted"], 1)
        self.assertEqual(module_row["response_rate_pct"], 100.0)
        self.assertEqual(module_row["target_response_rate_pct"], 50.0)

    def test_customer_brief_pack_writes_json_and_markdown(self) -> None:
        snapshot = build_dashboard_snapshot(base_payload(), tenant_name="Window Customer", enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_customer_brief_pack(Path(tmp), snapshot=snapshot)
            brief = json.loads(Path(pack["paths"]["customer_brief"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(brief["brief_type"], "homepilot_customer_intelligence_brief")
        self.assertIn("HomePilot Customer Intelligence Brief", markdown)
        self.assertIn("Action Plan", markdown)

    def test_campaign_learning_report_turns_responses_into_experiments(self) -> None:
        payload = base_payload()
        payload["assessments"][1]["metrics"].update({
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
        })
        snapshot = build_dashboard_snapshot(payload, tenant_name="Window Customer", enabled_modules=["windowpilot"])
        report = build_campaign_learning_report(snapshot)
        body = json.dumps(report).lower()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["tenant"]["modules"], ["windowpilot"])
        self.assertEqual(report["funnel"]["properties"], 1)
        self.assertEqual(report["funnel"]["engaged"], 1)
        self.assertGreaterEqual(len(report["experiment_backlog"]), 1)
        self.assertNotIn("facadepilot", body)
        self.assertNotIn("secret prompt", body)
        self.assertNotIn("private raw features", body)
        self.assertNotIn("score_total", body)

    def test_campaign_learning_pack_writes_json_and_markdown(self) -> None:
        snapshot = build_dashboard_snapshot(base_payload(), tenant_name="Window Customer", enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_campaign_learning_pack(Path(tmp), snapshot=snapshot)
            report = json.loads(Path(pack["paths"]["campaign_learning"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(report["report_type"], "homepilot_campaign_learning_report")
        self.assertIn("HomePilot Campaign Learning Report", markdown)
        self.assertIn("Experiment Backlog", markdown)

    def test_territory_plan_prioritizes_next_batch_from_scoped_snapshot(self) -> None:
        payload = base_payload()
        payload["assessments"][1]["metrics"].update({
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
        })
        snapshot = build_dashboard_snapshot(payload, tenant_name="Window Customer", enabled_modules=["windowpilot"])
        plan = build_territory_plan(snapshot)
        body = json.dumps(plan).lower()
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["tenant"]["modules"], ["windowpilot"])
        self.assertEqual(plan["market_overview"]["properties"], 1)
        self.assertGreaterEqual(len(plan["territory_cells"]), 1)
        self.assertGreaterEqual(len(plan["next_batch_plan"]), 1)
        self.assertNotIn("facadepilot", body)
        self.assertNotIn("secret prompt", body)
        self.assertNotIn("private raw features", body)
        self.assertNotIn("score_total", body)

    def test_territory_plan_pack_writes_json_and_markdown(self) -> None:
        snapshot = build_dashboard_snapshot(base_payload(), tenant_name="Window Customer", enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_territory_plan_pack(Path(tmp), snapshot=snapshot)
            plan = json.loads(Path(pack["paths"]["territory_plan"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(plan["report_type"], "homepilot_territory_plan")
        self.assertIn("HomePilot Territory Plan", markdown)
        self.assertIn("Next Batch Plan", markdown)

    def test_roi_forecast_builds_scenario_business_case_from_scoped_snapshot(self) -> None:
        payload = base_payload()
        payload["assessments"][1]["metrics"].update({
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
        })
        snapshot = build_dashboard_snapshot(payload, tenant_name="Window Customer", enabled_modules=["windowpilot"])
        forecast = build_roi_forecast(snapshot)
        body = json.dumps(forecast).lower()
        self.assertEqual(forecast["status"], "pass")
        self.assertTrue(forecast["not_financial_advice"])
        self.assertEqual(forecast["tenant"]["modules"], ["windowpilot"])
        self.assertEqual(forecast["business_case"]["properties"], 1)
        self.assertEqual(len(forecast["scenario_forecast"]), 3)
        self.assertGreater(forecast["business_case"]["visible_pipeline_value"], 0)
        self.assertNotIn("facadepilot", body)
        self.assertNotIn("secret prompt", body)
        self.assertNotIn("private raw features", body)
        self.assertNotIn("score_total", body)

    def test_roi_forecast_pack_writes_json_and_markdown(self) -> None:
        snapshot = build_dashboard_snapshot(base_payload(), tenant_name="Window Customer", enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_roi_forecast_pack(Path(tmp), snapshot=snapshot)
            report = json.loads(Path(pack["paths"]["roi_forecast"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(report["report_type"], "homepilot_roi_forecast")
        self.assertIn("HomePilot ROI Forecast", markdown)
        self.assertIn("Scenario Forecast", markdown)

    def test_opportunity_dossier_explains_top_properties_without_internal_metrics(self) -> None:
        payload = base_payload()
        payload["assessments"][1]["metrics"].update({
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
        })
        snapshot = build_dashboard_snapshot(payload, tenant_name="Window Customer", enabled_modules=["windowpilot"])
        dossier = build_opportunity_dossier(snapshot)
        body = json.dumps(dossier).lower()
        self.assertEqual(dossier["status"], "pass")
        self.assertEqual(dossier["tenant"]["modules"], ["windowpilot"])
        self.assertEqual(dossier["summary"]["dossiers"], 1)
        self.assertEqual(dossier["dossiers"][0]["module_key"], "windowpilot")
        self.assertGreaterEqual(len(dossier["dossiers"][0]["metric_drivers"]), 1)
        self.assertNotIn("facadepilot", body)
        self.assertNotIn("secret prompt", body)
        self.assertNotIn("private raw features", body)
        self.assertNotIn("internal_model_prompt", body)

    def test_opportunity_dossier_pack_writes_json_and_markdown(self) -> None:
        snapshot = build_dashboard_snapshot(base_payload(), tenant_name="Window Customer", enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_opportunity_dossier_pack(Path(tmp), snapshot=snapshot)
            report = json.loads(Path(pack["paths"]["opportunity_dossier"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(report["report_type"], "homepilot_opportunity_dossier")
        self.assertIn("HomePilot Opportunity Dossier", markdown)
        self.assertIn("Metric drivers", markdown)

    def test_source_ledger_tracks_provenance_without_internal_metric_leakage(self) -> None:
        payload = base_payload()
        payload["assessments"][1]["source_run_id"] = "window-run-2026-06-19"
        payload["assessments"][1]["metrics"].update({
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
        })
        payload["campaign_targets"][1]["metadata"].update({
            "contact_basis": "legitimate_interest_reviewed",
            "source_provenance": "Customer-approved visual opportunity scan",
            "contact_channel": "direct_mail",
            "opt_out_method": "Reply using customer suppression workflow",
            "lead_claim": "renovation opportunity based on visible property signals",
        })
        ledger = build_source_ledger(filter_payload_for_entitlements(
            payload,
            tenant_ids={payload["properties"][0]["tenant_id"]},
            enabled_modules=["windowpilot"],
        ))
        body = json.dumps(ledger).lower()
        self.assertEqual(ledger["status"], "pass")
        self.assertTrue(ledger["scope"]["tenant_scoped"])
        self.assertEqual(ledger["scope"]["module_keys"], ["windowpilot"])
        self.assertEqual(ledger["summary"]["evidence_references"], 1)
        self.assertEqual(ledger["summary"]["source_runs"], 1)
        self.assertNotIn("facadepilot", body)
        self.assertNotIn("secret prompt", body)
        self.assertNotIn("private raw features", body)
        self.assertNotIn("internal_model_prompt", body)

    def test_source_ledger_pack_writes_json_and_markdown(self) -> None:
        payload = build_module_payload(
            tenant_slug="ledger-customer",
            module_key="windowpilot",
            campaign_key="ledger-window",
            address="Ledgerlaan 1",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=94,
        )
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_source_ledger_pack(Path(tmp), payload=payload)
            report = json.loads(Path(pack["paths"]["source_ledger"]).read_text(encoding="utf-8"))
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(report["report_type"], "homepilot_source_ledger")
        self.assertIn("HomePilot Source Ledger", markdown)
        self.assertIn("Evidence Types", markdown)

    def test_data_dictionary_pack_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_data_dictionary_pack(Path(tmp), modules=["windowpilot"])
            dictionary_path = Path(pack["paths"]["data_dictionary"])
            markdown_path = Path(pack["paths"]["markdown"])
            dictionary = json.loads(dictionary_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(dictionary["modules_selected"], ["windowpilot"])
        self.assertIn("HomePilot Data Dictionary", markdown)
        self.assertIn("windowpilot.replacement_urgency", markdown)
        self.assertIn("CUSTOMER_BRIEF.md", markdown)
        self.assertIn("CAMPAIGN_LEARNING.md", markdown)
        self.assertIn("TERRITORY_PLAN.md", markdown)
        self.assertIn("ROI_FORECAST.md", markdown)
        self.assertIn("OPPORTUNITY_DOSSIER.md", markdown)
        self.assertIn("SOURCE_LEDGER.md", markdown)

    def test_enterprise_demo_payload_covers_all_modules_without_internal_metrics(self) -> None:
        payload = build_demo_payload()
        validate_payload(payload)
        modules = {assessment["module_key"] for assessment in payload["assessments"]}
        body = json.dumps(payload).lower()
        self.assertEqual(modules, set(PILOT_MODULES))
        self.assertGreaterEqual(len(payload["properties"]), 15)
        self.assertGreaterEqual(len(payload["interactions"]), 20)
        self.assertTrue(all(target.get("metadata", {}).get("contact_basis") for target in payload["campaign_targets"]))
        self.assertTrue(all(target.get("metadata", {}).get("lead_claim") == "opportunity intelligence only; no homeowner buying intent claimed" for target in payload["campaign_targets"]))
        self.assertTrue(all(any(item.get("type") == "render" for item in assessment.get("evidence", [])) for assessment in payload["assessments"]))
        self.assertTrue(all(prop.get("core", {}).get("public_enrichment", {}).get("status") == "demo_public_context" for prop in payload["properties"]))
        self.assertTrue(all(prop.get("core", {}).get("public_enrichment", {}).get("features") for prop in payload["properties"]))
        self.assertNotIn("internal_model_prompt", body)
        self.assertNotIn("raw_feature_dump", body)
        self.assertNotIn("owner_name", body)
        self.assertNotIn("personal_contact", body)

    def test_enterprise_demo_payload_can_scale_to_synthetic_territory(self) -> None:
        payload = build_demo_payload(property_count=250)
        validate_payload(payload)
        modules = {assessment["module_key"] for assessment in payload["assessments"]}
        statuses = {target["status"] for target in payload["campaign_targets"]}
        body = json.dumps(payload).lower()
        self.assertEqual(len(payload["properties"]), 250)
        self.assertEqual(modules, set(PILOT_MODULES))
        self.assertGreaterEqual(len(payload["assessments"]), 750)
        self.assertGreaterEqual(len(payload["interactions"]), 250)
        self.assertIn("appointment", statuses)
        self.assertIn("no_response", statuses)
        self.assertTrue(all(prop["address"].startswith("Demo ") for prop in payload["properties"]))
        self.assertTrue(all(prop.get("core", {}).get("synthetic_record") for prop in payload["properties"]))
        self.assertTrue(all(prop.get("core", {}).get("public_enrichment", {}).get("source_run_id") == "homepilot-scaled-demo-public-context" for prop in payload["properties"]))
        self.assertTrue(all(target.get("metadata", {}).get("demo_dataset") == "homepilot-scaled-demo" for target in payload["campaign_targets"]))
        self.assertNotIn("internal_model_prompt", body)
        self.assertNotIn("raw_feature_dump", body)

    def test_daw_demo_payload_builds_producer_partner_network_scope(self) -> None:
        payload = build_demo_payload(tenant_slug="daw-belgium-crepi-network", property_count=120, scenario="daw")
        validate_payload(payload)
        modules = {assessment["module_key"] for assessment in payload["assessments"]}
        partner_ids = {prop["core"]["network"]["partner_id"] for prop in payload["properties"]}
        snapshot = build_dashboard_snapshot(payload, tenant_name="DAW Belgium", enabled_modules=["facadepilot"])
        brain_types = {node["type"] for node in snapshot["brain"]["nodes"]}
        first_context = payload["properties"][0]["core"]["public_enrichment"]
        snapshot_context = snapshot["properties"][0]["publicContext"]
        self.assertEqual(len(payload["properties"]), 120)
        self.assertEqual(modules, {"facadepilot"})
        self.assertEqual(len(payload["network"]["partners"]), 10)
        self.assertEqual(len(partner_ids), 10)
        self.assertTrue(all(prop["core"]["network"]["producer"] == "DAW" for prop in payload["properties"]))
        self.assertEqual(first_context["source_run_id"], "daw-crepi-network-demo-public-context")
        self.assertEqual(first_context["read_model"], "homepilot_property_public_enrichment")
        self.assertTrue(first_context["guardrails"])
        self.assertEqual(snapshot_context["sourceRunId"], "daw-crepi-network-demo-public-context")
        self.assertEqual(snapshot_context["readModel"], "homepilot_property_public_enrichment")
        self.assertGreaterEqual(len(snapshot_context["features"]), 5)
        self.assertEqual(snapshot["trust"]["publicContext"]["propertiesWithContext"], 120)
        self.assertTrue(snapshot["trust"]["publicContext"]["privateLanesExcluded"])
        self.assertEqual(snapshot["network"]["producer"]["name"], "DAW Belgium")
        self.assertEqual(snapshot["network"]["metrics"]["partners"], 10)
        self.assertEqual(snapshot["network"]["metrics"]["properties"], 120)
        self.assertIn("partner", brain_types)
        self.assertTrue(any(edge["type"] == "partner_scope" for edge in snapshot["brain"]["edges"]))
        self.assertTrue(any(edge["type"] == "public_context" for edge in snapshot["brain"]["edges"]))

    def test_partner_cutdown_pack_builds_isolated_partner_packages(self) -> None:
        payload = build_demo_payload(tenant_slug="daw-belgium-crepi-network", property_count=120, scenario="daw")
        first_partner = payload["network"]["partners"][0]
        scoped = filter_payload_for_partner(payload, first_partner["id"])
        scoped_partner_ids = {
            prop["core"]["network"]["partner_id"]
            for prop in scoped["properties"]
        }
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_partner_cutdown_pack(
                payload=payload,
                out_dir=Path(tmp) / "partner_cutdowns",
                tenant_name="DAW Belgium Crepi Network",
                tenant_slug="daw-belgium-crepi-network",
                modules=["facadepilot"],
                include_xlsx=False,
                include_zip=False,
            )
            manifest_exists = Path(pack["paths"]["manifest"]).exists()
            first_row = pack["partners"][0]
            first_manifest = json.loads(Path(first_row["paths"]["manifest"]).read_text(encoding="utf-8"))
            first_snapshot = json.loads((Path(first_row["paths"]["manifest"]).parent / "data" / "dashboard_snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(scoped_partner_ids, {first_partner["id"]})
        self.assertEqual(len(scoped["properties"]), 12)
        self.assertEqual(pack["status"], "pass")
        self.assertTrue(manifest_exists)
        self.assertEqual(pack["summary"]["partners"], 10)
        self.assertEqual(pack["summary"]["properties"], 120)
        self.assertEqual(pack["summary"]["failed_partners"], 0)
        self.assertTrue(all(row["status"] == "pass" for row in pack["partners"]))
        self.assertTrue(all(row["payload_scope_audit"]["status"] == "pass" for row in pack["partners"]))
        self.assertTrue(all(row["snapshot_scope_audit"]["status"] == "pass" for row in pack["partners"]))
        self.assertEqual(first_manifest["access_audit"]["status"], "pass")
        self.assertEqual(first_manifest["boardroom_report"]["status"], "pass")
        self.assertEqual(first_snapshot["network"]["metrics"]["partners"], 1)
        self.assertEqual(len(first_snapshot["network"]["partners"]), 1)

    def test_boardroom_report_pack_builds_producer_network_report(self) -> None:
        payload = build_demo_payload(tenant_slug="daw-belgium-crepi-network", property_count=120, scenario="daw")
        snapshot = build_dashboard_snapshot(payload, tenant_name="DAW Belgium", enabled_modules=["facadepilot"])
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_boardroom_report_pack(snapshot, Path(tmp) / "report", dashboard_dir=Path(tmp) / "dashboard")
            report = build_boardroom_report(snapshot)
            html = (Path(tmp) / "dashboard" / "boardroom-report.html").read_text(encoding="utf-8")
            partner_csv = Path(pack["paths"]["partner_summary"])
            partner_csv_exists = partner_csv.exists()
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["mode"], "producer_network")
        self.assertEqual(report["summary"]["properties"], 120)
        self.assertEqual(report["summary"]["partners"], 10)
        self.assertEqual(len(report["partner_rows"]), 10)
        self.assertEqual(report["intelligence_lab"]["status"], "not_run")
        self.assertTrue(partner_csv_exists)
        self.assertIn("DAW Belgium", html)
        self.assertIn("Partner steering matrix", html)

    def test_enterprise_demo_room_builds_customer_package_dictionary_and_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_demo_room(Path(tmp), include_xlsx=False, include_zip=False)
            package_manifest = json.loads(Path(manifest["paths"]["customer_package_manifest"]).read_text(encoding="utf-8"))
            dictionary = json.loads(Path(manifest["paths"]["data_dictionary"]).read_text(encoding="utf-8"))
            enrichment = json.loads(Path(manifest["paths"]["data_vendor_plan"]).read_text(encoding="utf-8"))
            properties_csv_exists = (Path(manifest["paths"]["exports"]) / "properties.csv").exists()
            dashboard_exists = Path(manifest["paths"]["dashboard_index"]).exists()
            portal_exists = Path(manifest["paths"]["portal_manifest"]).exists()
            integration_exists = Path(manifest["paths"]["integration_manifest"]).exists()
            readme = Path(manifest["paths"]["readme"]).read_text(encoding="utf-8")
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(set(manifest["modules"]), set(PILOT_MODULES))
        self.assertGreaterEqual(manifest["summary"]["properties"], 15)
        self.assertEqual(manifest["portal"]["status"], "pass")
        self.assertEqual(manifest["sales_integration"]["status"], "pass")
        self.assertEqual(manifest["data_vendor_enrichment"]["status"], "pass")
        self.assertEqual(manifest["data_vendor_enrichment"]["review_status"], "ready")
        self.assertEqual(package_manifest["access_audit"]["status"], "pass")
        self.assertEqual(package_manifest["audit_trail"]["status"], "pass")
        self.assertEqual(dictionary["status"], "pass")
        self.assertEqual(set(dictionary["modules_selected"]), set(PILOT_MODULES))
        self.assertEqual(enrichment["summary"]["categories"], 7)
        self.assertEqual(enrichment["summary"]["backlog_items"], 0)
        self.assertTrue(properties_csv_exists)
        self.assertTrue(dashboard_exists)
        self.assertTrue(portal_exists)
        self.assertTrue(integration_exists)
        self.assertIn("HomePilot Enterprise Demo Room", readme)
        self.assertIn("Data vendor plan", readme)

    def test_enterprise_demo_room_builds_scaled_synthetic_customer_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_demo_room(Path(tmp), include_xlsx=False, include_zip=False, property_count=180)
            package_manifest_path = Path(manifest["paths"]["customer_package_manifest"])
            package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
            snapshot = json.loads((package_manifest_path.parent / "data" / "dashboard_snapshot.json").read_text(encoding="utf-8"))
            readme = Path(manifest["paths"]["readme"]).read_text(encoding="utf-8")
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["dataset"]["mode"], "scaled_synthetic")
        self.assertEqual(manifest["summary"]["properties"], 180)
        self.assertEqual(package_manifest["summary"]["properties"], 180)
        self.assertEqual(package_manifest["access_audit"]["status"], "pass")
        self.assertEqual(snapshot["visualIntelligence"]["map"]["strategy"], "clustered_map")
        self.assertIn("Properties: 180", readme)
        self.assertIn("Scaled demo addresses", readme)

    def test_daw_demo_room_builds_customer_package_with_partner_lens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_demo_room(
                Path(tmp),
                tenant_name="DAW Belgium Crepi Network",
                tenant_slug="daw-belgium-crepi-network",
                include_xlsx=False,
                include_zip=False,
                property_count=160,
                scenario="daw",
            )
            package_manifest_path = Path(manifest["paths"]["customer_package_manifest"])
            package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
            snapshot = json.loads((package_manifest_path.parent / "data" / "dashboard_snapshot.json").read_text(encoding="utf-8"))
            dashboard_index = Path(manifest["paths"]["dashboard_index"]).read_text(encoding="utf-8")
            dashboard_js = (Path(manifest["paths"]["dashboard_index"]).parent / "dashboard-data.js").read_text(encoding="utf-8")
            partner_manifest = json.loads(Path(manifest["paths"]["partner_cutdowns_manifest"]).read_text(encoding="utf-8"))
            readme = Path(manifest["paths"]["readme"]).read_text(encoding="utf-8")
            intelligence_lab_exists = Path(package_manifest["paths"]["intelligence_lab"]).exists()
            intelligence_lab_markdown_exists = Path(package_manifest["paths"]["intelligence_lab_markdown"]).exists()
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["dataset"]["mode"], "daw_producer_network")
        self.assertEqual(manifest["modules"], ["facadepilot"])
        self.assertEqual(manifest["summary"]["properties"], 160)
        self.assertEqual(package_manifest["access_audit"]["status"], "pass")
        self.assertEqual(package_manifest["intelligence_lab"]["status"], "pass")
        self.assertEqual(set(package_manifest["intelligence_lab"]["families"]), {
            "lead_prioritization",
            "partner_assignment",
            "campaign_segmentation",
            "message_strategy",
        })
        self.assertEqual(set(package_manifest["intelligence_lab"]["snapshot_keys_attached"]), {
            "leadPrioritization",
            "partnerAssignment",
            "campaignSegmentation",
            "messageStrategy",
        })
        self.assertEqual(package_manifest["open_intelligence"]["status"], "pass")
        self.assertEqual(package_manifest["open_intelligence"]["model"], "DAW Belgium Crepi Opportunity Model")
        self.assertEqual(package_manifest["open_intelligence"]["data_collaboration_room"], "ready_for_buyer_review")
        self.assertEqual(package_manifest["open_intelligence"]["marketing_impact_planner"], "review_ready")
        self.assertEqual(package_manifest["open_intelligence"]["boardroom_brief"], "boardroom_ready")
        self.assertEqual(package_manifest["open_intelligence"]["boardroom_decisions"], 5)
        self.assertGreaterEqual(package_manifest["open_intelligence"]["activation_lanes"], 5)
        self.assertGreaterEqual(package_manifest["open_intelligence"]["measurement_stages"], 5)
        self.assertEqual(package_manifest["boardroom_report"]["intelligence_lab"]["status"], "ready")
        self.assertEqual(package_manifest["boardroom_report"]["intelligence_lab"]["family_count"], 4)
        self.assertEqual(package_manifest["boardroom_report"]["intelligence_lab"]["scope_leakage_count"], 0)
        self.assertEqual(package_manifest["boardroom_report"]["intelligence_lab"]["forbidden_claim_count"], 0)
        self.assertIn("lead_prioritization", package_manifest["open_intelligence"]["experiment_families"])
        self.assertIn("partner_assignment", package_manifest["open_intelligence"]["experiment_families"])
        self.assertIn("campaign_segmentation", package_manifest["open_intelligence"]["experiment_families"])
        self.assertIn("message_strategy", package_manifest["open_intelligence"]["experiment_families"])
        self.assertEqual(snapshot["network"]["producer"]["name"], "DAW Belgium")
        self.assertEqual(len(snapshot["network"]["partners"]), 10)
        access_lenses = {row["key"]: row for row in snapshot["accessLenses"]}
        self.assertIn("producer_network", access_lenses)
        self.assertIn("partner_renovator", access_lenses)
        self.assertIn("module_only_customer", access_lenses)
        self.assertEqual(access_lenses["producer_network"]["partner_mode"], "all")
        self.assertEqual(access_lenses["partner_renovator"]["scope"], "assigned records only")
        self.assertEqual(access_lenses["module_only_customer"]["module_keys"], ["facadepilot"])
        self.assertTrue(access_lenses["producer_network"]["buyer_review_only"])
        self.assertIn("other partner raw addresses", json.dumps(access_lenses["partner_renovator"]).lower())
        self.assertEqual(snapshot["trust"]["publicContext"]["propertiesWithContext"], 160)
        self.assertIn("publicContext", snapshot["properties"][0])
        self.assertIn("leadPrioritization", snapshot)
        self.assertIn("partnerAssignment", snapshot)
        self.assertIn("campaignSegmentation", snapshot)
        self.assertIn("messageStrategy", snapshot)
        families = {row["family"]: row for row in snapshot["openIntelligence"]["model_lab"]["experiment_families"]}
        self.assertEqual(families["lead_prioritization"]["status"], "ready")
        self.assertEqual(families["partner_assignment"]["scope_leakage_count"], 0)
        self.assertEqual(families["campaign_segmentation"]["response_denominator"], "contacted_count")
        self.assertEqual(families["message_strategy"]["forbidden_claim_count"], 0)
        self.assertTrue(intelligence_lab_exists)
        self.assertTrue(intelligence_lab_markdown_exists)
        self.assertEqual(manifest["status_checks"]["partner_cutdowns"], "pass")
        self.assertEqual(manifest["partner_cutdowns"]["status"], "pass")
        self.assertEqual(partner_manifest["summary"]["partners"], 10)
        self.assertEqual(partner_manifest["summary"]["failed_partners"], 0)
        self.assertEqual(partner_manifest["summary"]["properties"], 160)
        self.assertIn("partnerLensBox", dashboard_index)
        self.assertIn("accessLensBox", dashboard_index)
        self.assertIn("accessLensPanel", dashboard_index)
        self.assertIn('data-view="intelligence"', dashboard_index)
        self.assertIn("intelligenceModelName", dashboard_index)
        self.assertIn("intelligenceDecisionBrief", dashboard_index)
        self.assertIn("intelligenceBriefSummary", dashboard_index)
        self.assertIn("intelligenceDecisionMatrix", dashboard_index)
        self.assertIn("intelligenceLabCockpit", dashboard_index)
        self.assertIn("intelligenceCockpitMetrics", dashboard_index)
        self.assertIn("intelligencePartnerWaves", dashboard_index)
        self.assertIn("intelligenceSegments", dashboard_index)
        self.assertIn("intelligenceMessageTests", dashboard_index)
        self.assertIn("networkPanel", dashboard_index)
        self.assertIn("publicContextList", dashboard_index)
        self.assertIn('"network"', dashboard_js)
        self.assertIn('"accessLenses"', dashboard_js)
        self.assertIn('"partner_renovator"', dashboard_js)
        self.assertIn('"module_only_customer"', dashboard_js)
        self.assertIn('"publicContext"', dashboard_js)
        self.assertIn('"openIntelligence"', dashboard_js)
        self.assertIn('"boardroom_brief"', dashboard_js)
        self.assertIn('"leadPrioritization"', dashboard_js)
        self.assertIn('"partnerAssignment"', dashboard_js)
        self.assertIn('"campaignSegmentation"', dashboard_js)
        self.assertIn('"messageStrategy"', dashboard_js)
        self.assertIn("Producer network: DAW Belgium", readme)
        self.assertIn("Partner cutdowns:", readme)

    def test_snapshot_and_exports_hide_internal_metrics(self) -> None:
        payload = base_payload()
        payload["assessments"][1]["metrics"].update({
            "internal_model_prompt": "secret prompt",
            "raw_feature_dump": "private raw features",
            "estimated_value": 36000,
        })
        snapshot = build_dashboard_snapshot(payload, enabled_modules=["windowpilot"])
        body = json.dumps(snapshot).lower()
        metrics = snapshot["properties"][0]["assessments"]["windowpilot"]["metrics"]
        self.assertEqual(metrics["estimated_value"], 36000)
        self.assertEqual(metrics["replacement_urgency"], "Old glazing")
        self.assertNotIn("internal_model_prompt", metrics)
        self.assertNotIn("raw_feature_dump", metrics)
        self.assertNotIn("secret prompt", body)
        self.assertNotIn("private raw features", body)
        self.assertIn("sourceledger", body)
        self.assertEqual(snapshot["trust"]["sourceLedger"]["status"], "pass")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_export_bundle(snapshot, Path(tmp), include_xlsx=False)
            assessments_csv = Path(manifest["files"]["assessments_csv"]).read_text(encoding="utf-8-sig").lower()
        self.assertNotIn("internal_model_prompt", assessments_csv)
        self.assertNotIn("secret prompt", assessments_csv)

    def test_snapshot_restricts_enabled_modules_without_leaking_counts(self) -> None:
        snapshot = build_dashboard_snapshot(
            base_payload(),
            tenant_name="Window Customer",
            tenant_slug="window-customer",
            enabled_modules=["windowpilot"],
        )
        self.assertEqual(snapshot["tenant"]["modules"], ["windowpilot"])
        self.assertEqual([campaign["module"] for campaign in snapshot["campaigns"]], ["windowpilot"])
        self.assertEqual(snapshot["summary"]["modules"], {"windowpilot": 1})
        self.assertEqual(snapshot["summary"]["assessments"], 1)
        self.assertEqual(snapshot["summary"]["properties"], 1)
        self.assertIn("brain", snapshot)
        self.assertIn("trust", snapshot)
        self.assertIn("sourceLedger", snapshot["trust"])
        self.assertGreater(snapshot["brain"]["stats"]["nodes"], 0)
        self.assertGreater(snapshot["brain"]["stats"]["edges"], 0)
        self.assertEqual(snapshot["trust"]["sourceLedger"]["scope"]["module_keys"], ["windowpilot"])
        self.assertTrue(any(node["type"] == "property" for node in snapshot["brain"]["nodes"]))
        self.assertTrue(any(edge["type"] == "scores_property" for edge in snapshot["brain"]["edges"]))
        self.assertNotIn("facadepilot", json.dumps(snapshot["brain"]).lower())

        prop = snapshot["properties"][0]
        self.assertEqual(set(prop["assessments"]), {"windowpilot"})
        self.assertEqual(prop["status"], "responded")
        self.assertEqual(prop["nextAction"], "Call about glazing")
        self.assertEqual([item["type"] for item in prop["interactions"]], ["call"])
        self.assertNotIn("facadepilot", json.dumps(snapshot).lower())

    def test_snapshot_rejects_multi_tenant_payloads(self) -> None:
        payload = base_payload()
        payload["properties"].append({
            "id": "prop_2",
            "tenant_id": canonical_tenant_id("tenant_b"),
            "address": "Otherstraat 2",
            "city": "Gent",
            "core": {},
            "tags": [],
        })
        payload["assessments"].append({
            "id": "asmt_other",
            "tenant_id": canonical_tenant_id("tenant_b"),
            "property_id": "prop_2",
            "module_key": "facadepilot",
            "score": 70,
            "grade": "A",
            "confidence": 0.7,
            "metrics": {},
            "evidence": [],
        })
        with self.assertRaises(ValueError):
            build_dashboard_snapshot(payload)

    def test_dashboard_js_writer_uses_expected_global(self) -> None:
        snapshot = build_dashboard_snapshot(base_payload(), enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dashboard-data.js"
            write_dashboard_js(snapshot, output)
            text = output.read_text(encoding="utf-8")
        self.assertIn("window.HOMEPILOT_DASHBOARD =", text)
        self.assertIn("WindowPilot", text)



    def test_export_log_records_validate_with_payload(self) -> None:
        payload = base_payload()
        tenant_id = payload["properties"][0]["tenant_id"]
        payload["exports"] = [
            build_export_log_record(
                tenant_id=tenant_id,
                module_key="windowpilot",
                export_type="xlsx",
                storage_path="exports/window/homepilot_export.xlsx",
                row_count=1,
                filters={"modules": ["windowpilot"]},
                created_at="2026-06-18T12:00:00+00:00",
            )
        ]
        validate_payload(payload)
        self.assertEqual(payload["exports"][0]["module_key"], "windowpilot")
        self.assertEqual(payload["exports"][0]["export_type"], "xlsx")

    def test_audit_trail_events_validate_with_payload(self) -> None:
        payload = base_payload()
        tenant_id = payload["properties"][0]["tenant_id"]
        payload["audit_events"] = [
            build_audit_event(
                tenant_id=tenant_id,
                module_key="windowpilot",
                event_type="export_generated",
                subject_type="export",
                subject_id="unit-test-export",
                details={"row_count": 1, "filter_modules": ["windowpilot"]},
                created_at="2026-06-18T12:00:00+00:00",
            )
        ]
        validate_payload(payload)
        report = build_audit_trail_report(
            payload["audit_events"],
            expected_tenant_id=tenant_id,
            required_event_types=["export_generated"],
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["metrics"]["event_count"], 1)

    def test_audit_trail_report_rejects_cross_tenant_or_secret_details(self) -> None:
        tenant_id = canonical_tenant_id("audit-tenant-a")
        other_tenant_id = canonical_tenant_id("audit-tenant-b")
        events = [
            build_audit_event(
                tenant_id=other_tenant_id,
                event_type="preflight_run",
                details={"supabase_service_key": "service-role-key"},
                created_at="2026-06-18T12:00:00+00:00",
            )
        ]
        report = build_audit_trail_report(events, expected_tenant_id=tenant_id)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("does not match expected tenant" in issue for issue in report["issues"]))
        self.assertTrue(any("sensitive marker" in issue for issue in report["issues"]))

    def test_deployment_manifest_pins_sql_apply_order_and_hashes(self) -> None:
        manifest = build_deployment_manifest(release_label="unit-test")
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["apply_order"], ["platform/supabase_schema.sql", "platform/dashboard_views.sql"])
        self.assertEqual(len(manifest["steps"]), 2)
        self.assertTrue(all(step["sha256"] for step in manifest["steps"]))
        self.assertFalse(manifest["issues"])

    def test_sql_apply_plan_pack_writes_reviewable_apply_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_sql_apply_plan_pack(Path(tmp), release_label="sql-apply-test")
            plan = json.loads(Path(pack["paths"]["sql_apply_plan"]).read_text(encoding="utf-8"))
            runbook = Path(pack["paths"]["sql_apply_runbook"]).read_text(encoding="utf-8")
            apply_sql = Path(pack["paths"]["apply_sql"]).read_text(encoding="utf-8")
            verification_sql = Path(pack["paths"]["post_apply_verification_sql"]).read_text(encoding="utf-8")

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(plan["apply_order"], ["platform/supabase_schema.sql", "platform/dashboard_views.sql"])
        self.assertTrue(plan["transactional"])
        self.assertEqual(plan["guardrails"]["stores_database_url"], False)
        self.assertEqual(plan["guardrails"]["requires_live_schema_verification_after_apply"], True)
        self.assertEqual(len(plan["apply_bundle"]["sha256"]), 64)
        self.assertEqual(plan["apply_bundle"]["sha256"], hashlib.sha256(apply_sql.encode("utf-8")).hexdigest())
        self.assertIn("begin;", apply_sql)
        self.assertIn("commit;", apply_sql)
        self.assertIn("homepilot_tenants", apply_sql)
        self.assertIn("homepilot_property_intelligence", apply_sql)
        self.assertIn("post_apply_verification.sql", runbook)
        self.assertIn("homepilot_live_schema_verification.py", runbook)
        self.assertIn("homepilot_second_brain_edges", verification_sql)

    def test_deployment_pack_writes_manifest_and_runbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_deployment_pack(Path(tmp), release_label="unit-pack")
            manifest_path = Path(pack["paths"]["deployment_manifest"])
            runbook_path = Path(pack["paths"]["deployment_runbook"])
            sql_apply_plan_path = Path(pack["paths"]["sql_apply_plan"])
            apply_sql_path = Path(pack["paths"]["apply_sql"])
            post_apply_path = Path(pack["paths"]["post_apply_verification_sql"])
            sql_apply_plan_exists = sql_apply_plan_path.exists()
            apply_sql_exists = apply_sql_path.exists()
            post_apply_exists = post_apply_path.exists()
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            runbook = runbook_path.read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "pass")
        self.assertEqual(saved["release_label"], "unit-pack")
        self.assertTrue(sql_apply_plan_exists)
        self.assertTrue(apply_sql_exists)
        self.assertTrue(post_apply_exists)
        self.assertIn("HomePilot Schema Deployment Runbook", runbook)
        self.assertIn("platform/supabase_schema.sql", runbook)
        self.assertIn("SQL_APPLY_PLAN.md", runbook)
        self.assertIn("homepilot_live_schema_verification.py", runbook)
        self.assertIn("homepilot_live_readiness.py", runbook)
        self.assertIn("homepilot_production_cutover.py", runbook)

    def test_schema_verification_dry_run_checks_local_contract_without_production_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_schema_verification_report(Path(tmp), live=False, env={})
            saved = json.loads((Path(tmp) / "schema_verification.json").read_text(encoding="utf-8"))
            runbook = (Path(tmp) / "SCHEMA_VERIFICATION.md").read_text(encoding="utf-8")

        checks = {check["name"]: check for check in report["checks"]}
        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["contract_status"], "pass")
        self.assertEqual(report["live_status"], "not_run")
        self.assertFalse(report["production_verified"])
        self.assertEqual(saved["status"], "dry_run")
        self.assertEqual(checks["local_contract_markers"]["status"], "pass")
        self.assertEqual(checks["live.metadata_query"]["status"], "skipped")
        self.assertIn("HomePilot Live Schema Verification", runbook)

    def test_schema_verification_evaluates_live_metadata_contract(self) -> None:
        metadata = {
            "tables": {
                table: {
                    "exists": True,
                    "columns": list(columns),
                    "rls_enabled": True,
                    "policies": list(EXPECTED_POLICIES.get(table, ())),
                }
                for table, columns in EXPECTED_TABLE_COLUMNS.items()
            },
            "views": {
                view: {
                    "exists": True,
                    "columns": list(columns),
                    "reloptions": ["security_invoker=true"],
                }
                for view, columns in EXPECTED_VIEW_COLUMNS.items()
            },
            "functions": {
                function: {"exists": True, "security_definer": function != "homepilot_metrics_for_customer"}
                for function in EXPECTED_FUNCTIONS
            },
        }
        checks, failures = evaluate_live_metadata(metadata)
        self.assertFalse(failures)
        self.assertTrue(all(check["status"] == "pass" for check in checks))

        broken = json.loads(json.dumps(metadata))
        broken["tables"]["homepilot_memberships"]["columns"].remove("partner_id")
        checks, failures = evaluate_live_metadata(broken)
        self.assertTrue(any("homepilot_memberships" in failure and "partner_id" in failure for failure in failures))
        self.assertTrue(any(check["name"] == "table.homepilot_memberships" and check["status"] == "fail" for check in checks))

    def test_production_cutover_dry_run_builds_full_evidence_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = build_readiness_pack(root / "readiness", run_qa=False)
            readiness_path = root / "readiness" / "readiness_report.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            due = build_due_diligence_pack(
                root / "due",
                readiness_report_path=readiness_path,
                modules=["windowpilot"],
            )
            report = build_production_cutover(
                out_dir=root / "cutover",
                readiness_report_path=readiness_path,
                due_diligence_report_path=Path(due["paths"]["due_diligence_report"]),
                account_access_plan_path=root / "readiness" / "account_access_smoke" / "account_access_plan.json",
                release_label="unit-cutover",
                live=False,
                env={},
            )
            saved = json.loads((root / "cutover" / "cutover_report.json").read_text(encoding="utf-8"))
            runbook = (root / "cutover" / "CUTOVER_RUNBOOK.md").read_text(encoding="utf-8")
            live_readiness_exists = Path(report["paths"]["live_readiness"]).exists()
            module_seed_exists = Path(report["paths"]["module_seed"]).exists()
            launch_report_exists = Path(report["paths"]["launch_report"]).exists()
            customer_access_exists = Path(report["paths"]["customer_access_verification"]).exists()

        steps = {step["name"]: step for step in report["steps"]}
        self.assertEqual(report["status"], "dry_run_ready")
        self.assertFalse(report["production_verified"])
        self.assertEqual(report["decisions"]["production"], "no_go")
        self.assertEqual(steps["input_evidence"]["status"], "pass")
        self.assertEqual(steps["live_readiness"]["status"], "pass")
        self.assertFalse(steps["live_readiness"]["ready_to_run_live_cutover"])
        self.assertEqual(steps["schema_verification"]["status"], "pass")
        self.assertEqual(steps["seed_modules"]["status"], "pass")
        self.assertEqual(steps["rls_launch"]["status"], "pass")
        self.assertEqual(steps["customer_access_verification"]["status"], "pass")
        self.assertTrue(live_readiness_exists)
        self.assertTrue(module_seed_exists)
        self.assertTrue(launch_report_exists)
        self.assertTrue(customer_access_exists)
        self.assertEqual(saved["release_label"], "unit-cutover")
        self.assertIn("HomePilot Production Cutover", runbook)
        self.assertIn("live_readiness", runbook)

    def test_production_cutover_live_blocks_before_mutating_when_live_inputs_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = build_readiness_pack(root / "readiness", run_qa=False)
            readiness_path = root / "readiness" / "readiness_report.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            due = build_due_diligence_pack(
                root / "due",
                readiness_report_path=readiness_path,
                modules=["facadepilot"],
            )
            report = build_production_cutover(
                out_dir=root / "cutover",
                readiness_report_path=readiness_path,
                due_diligence_report_path=Path(due["paths"]["due_diligence_report"]),
                account_access_plan_path=root / "readiness" / "account_access_smoke" / "account_access_plan.json",
                release_label="unit-live-blocked",
                live=True,
                env={},
            )
            live_readiness = json.loads(Path(report["paths"]["live_readiness"]).read_text(encoding="utf-8"))

        steps = {step["name"]: step for step in report["steps"]}
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["production_verified"])
        self.assertEqual(steps["live_readiness"]["status"], "fail")
        self.assertFalse(live_readiness["ready_to_run_live_cutover"])
        self.assertGreater(len(live_readiness["missing_live_inputs"]), 0)
        self.assertIsNone(report["paths"]["launch_report"])
        self.assertNotIn("rls_launch", steps)

    def test_production_cutover_blocks_without_required_input_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_production_cutover(
                out_dir=Path(tmp) / "cutover",
                live=False,
                env={},
            )
        steps = {step["name"]: step for step in report["steps"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(steps["input_evidence"]["status"], "fail")
        self.assertTrue(any("Missing readiness report" in blocker for blocker in report["blockers"]))

    def test_recovery_pack_builds_backup_manifest_and_tenant_guarded_rollback(self) -> None:
        payload = base_payload()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            payload_path = tmp_path / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            manifest = build_backup_manifest([payload_path], label="unit_recovery")
            pack = build_recovery_pack(payload_path, tmp_path / "recovery", include_properties=True)
            rollback = pack["rollback_plan"]
            sql = "\n".join(rollback["sql"])

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(pack["status"], "ready_for_review")
        self.assertEqual(rollback["tenant_id"], payload["properties"][0]["tenant_id"])
        self.assertGreater(rollback["counts"]["homepilot_campaign_targets"], 0)
        self.assertEqual(rollback["counts"]["homepilot_properties"], 1)
        self.assertIn("where tenant_id =", sql)
        self.assertIn("delete from public.homepilot_campaign_targets", sql)
        self.assertIn("delete from public.homepilot_properties", sql)
        self.assertLess(sql.index("homepilot_campaign_targets"), sql.index("homepilot_properties"))

    def test_recovery_plan_retains_properties_by_default(self) -> None:
        payload = base_payload()
        plan = build_import_rollback_plan(payload, module_keys=["windowpilot"], include_properties=False)
        sql = "\n".join(plan["sql"])
        self.assertEqual(plan["module_keys"], ["windowpilot"])
        self.assertEqual(plan["counts"]["homepilot_properties"], 0)
        self.assertNotIn("delete from public.homepilot_properties", sql)
        self.assertTrue(any("Properties are retained by default" in warning for warning in plan["warnings"]))

    def test_property_delete_plan_builds_ordered_reviewable_sql(self) -> None:
        plan = build_property_delete_plan(base_payload(), ["prop_1"])
        self.assertEqual(plan["status"], "ready_for_review")
        self.assertEqual(plan["counts"]["homepilot_properties"], 1)
        self.assertEqual(plan["counts"]["homepilot_assessments"], 2)
        self.assertEqual(plan["counts"]["homepilot_campaign_targets"], 2)
        self.assertEqual(plan["counts"]["homepilot_interactions"], 2)
        self.assertEqual(plan["affected_modules"], ["facadepilot", "windowpilot"])
        sql = "\n".join(plan["sql"])
        self.assertIn("delete from public.homepilot_interactions", sql)
        self.assertIn("delete from public.homepilot_properties", sql)
        self.assertLess(
            sql.index("delete from public.homepilot_interactions"),
            sql.index("delete from public.homepilot_properties"),
        )
        self.assertIn("'prop_1'", sql)
        self.assertTrue(any("campaign-level" in warning for warning in plan["warnings"]))

    def test_response_rows_update_campaign_target_and_log_interaction(self) -> None:
        payload = base_payload()
        merged = merge_response_rows(payload, [{
            "property_id": "prop_1",
            "module_key": "windowpilot",
            "status": "appointment",
            "interaction_type": "call",
            "response_status": "interested",
            "detail": "Booked a measurement visit",
            "occurred_at": "2026-06-18T09:30:00Z",
            "next_action": "Prepare quote",
        }])
        validate_payload(merged)
        target = [
            row for row in merged["campaign_targets"]
            if row["property_id"] == "prop_1" and row["module_key"] == "windowpilot"
        ][0]
        self.assertEqual(target["status"], "appointment")
        self.assertEqual(target["metadata"]["next_action"], "Prepare quote")
        self.assertEqual(merged["interactions"][-1]["detail"], "Booked a measurement visit")
        self.assertEqual(merged["interactions"][-1]["interaction_type"], "call")

    def test_payload_validation_rejects_non_uuid_campaign_targets(self) -> None:
        payload = base_payload()
        payload["campaigns"] = []
        payload["campaign_targets"][0]["campaign_id"] = "not-a-uuid"
        with self.assertRaises(ValueError):
            validate_payload(payload)

    def test_export_bundle_writes_excel_style_customer_files(self) -> None:
        snapshot = build_dashboard_snapshot(base_payload(), enabled_modules=["windowpilot"])
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_export_bundle(snapshot, Path(tmp), include_xlsx=True)
            self.assertTrue(Path(manifest["files"]["properties_csv"]).exists())
            self.assertTrue(Path(manifest["files"]["assessments_csv"]).exists())
            self.assertTrue(Path(manifest["files"]["recommendations_csv"]).exists())
            self.assertTrue(Path(manifest["files"]["manifest"]).exists())
            if importlib.util.find_spec("openpyxl"):
                self.assertTrue(manifest["xlsx_written"])
                self.assertTrue(Path(manifest["files"]["xlsx"]).exists())
            self.assertEqual(manifest["summary"]["modules"], {"windowpilot": 1})


    def test_compliance_passes_for_provenance_and_opportunity_language(self) -> None:
        payload = build_module_payload(
            tenant_slug="compliance-window",
            module_key="windowpilot",
            campaign_key="compliance-window",
            address="Compliancelaan 1",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["campaigns"][0]["message_variant"] = "opportunity_language"
        payload["campaign_targets"][0]["metadata"].update({
            "contact_basis": "legitimate_interest_reviewed",
            "source_provenance": "Synthetic test source",
            "contact_channel": "direct_mail",
            "opt_out_method": "Suppression list",
            "retention_review_at": "2026-12-31",
            "lead_claim": "renovation opportunity based on visible property signals",
        })
        report = build_compliance_report(payload)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["metrics"]["failure_count"], 0)
        self.assertEqual(report["metrics"]["contactable_count"], 1)

    def test_compliance_fails_missing_contact_basis(self) -> None:
        payload = build_module_payload(
            tenant_slug="compliance-missing-basis",
            module_key="windowpilot",
            campaign_key="compliance-missing-basis",
            address="Compliancelaan 2",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["campaign_targets"][0]["metadata"].update({
            "source_provenance": "Synthetic test source",
            "contact_channel": "direct_mail",
        })
        report = build_compliance_report(payload)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("contact_basis" in item for item in report["failures"]))

    def test_compliance_fails_unproven_ready_to_hire_claim(self) -> None:
        payload = build_module_payload(
            tenant_slug="compliance-intent-claim",
            module_key="windowpilot",
            campaign_key="compliance-intent-claim",
            address="Compliancelaan 3",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["campaigns"][0]["message_variant"] = "bad_claim"
        payload["campaign_targets"][0]["status"] = "sent"
        payload["campaign_targets"][0]["metadata"].update({
            "contact_basis": "legitimate_interest_reviewed",
            "source_provenance": "Synthetic test source",
            "contact_channel": "direct_mail",
            "opt_out_method": "Suppression list",
            "retention_review_at": "2026-12-31",
            "lead_claim": "ready to hire for new windows",
        })
        report = build_compliance_report(payload)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("unproven" in item for item in report["failures"]))

    def test_compliance_fails_when_do_not_contact_is_not_propagated(self) -> None:
        payload = build_module_payload(
            tenant_slug="compliance-dnc",
            module_key="windowpilot",
            campaign_key="compliance-dnc",
            address="Compliancelaan 4",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["campaigns"][0]["message_variant"] = "dnc"
        payload["campaign_targets"][0]["metadata"].update({
            "contact_basis": "legitimate_interest_reviewed",
            "source_provenance": "Synthetic test source",
            "contact_channel": "direct_mail",
            "opt_out_method": "Suppression list",
            "retention_review_at": "2026-12-31",
            "lead_claim": "renovation opportunity",
        })
        payload["interactions"][0]["response_status"] = "do_not_contact"
        report = build_compliance_report(payload)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("do_not_contact interaction" in item for item in report["failures"]))

    def test_retention_passes_for_scheduled_contacted_target(self) -> None:
        payload = build_module_payload(
            tenant_slug="retention-window",
            module_key="windowpilot",
            campaign_key="retention-window",
            address="Retentiedreef 1",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["campaign_targets"][0]["metadata"].update({
            "retention_review_at": "2026-12-31",
            "delete_after": "2027-12-31",
        })
        report = build_retention_report(payload, as_of="2026-06-19")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["metrics"]["contacted_count"], 1)
        self.assertEqual(report["metrics"]["action_count"], 0)

    def test_retention_fails_missing_schedule_for_contacted_target(self) -> None:
        payload = build_module_payload(
            tenant_slug="retention-missing",
            module_key="windowpilot",
            campaign_key="retention-missing",
            address="Retentiedreef 2",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        report = build_retention_report(payload, as_of="2026-06-19")
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(action["action"] == "add_retention_schedule" for action in report["actions"]))

    def test_retention_flags_due_delete_plan(self) -> None:
        payload = build_module_payload(
            tenant_slug="retention-delete",
            module_key="windowpilot",
            campaign_key="retention-delete",
            address="Retentiedreef 3",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["campaign_targets"][0]["metadata"]["delete_after"] = "2026-01-01"
        report = build_retention_report(payload, as_of="2026-06-19")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["delete_plan_property_ids"], [payload["properties"][0]["id"]])

    def test_data_quality_passes_for_seeded_module_payload(self) -> None:
        payload = build_module_payload(
            tenant_slug="quality-window",
            module_key="windowpilot",
            campaign_key="quality-window",
            address="Qualitylaan 1",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        report = build_data_quality_report(payload)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["metrics"]["geocode_coverage_pct"], 100.0)
        self.assertEqual(report["metrics"]["score_coverage_pct"], 100.0)
        self.assertEqual(report["metrics"]["evidence_coverage_pct"], 100.0)
        self.assertEqual(report["metrics"]["target_coverage_pct"], 100.0)

    def test_data_quality_warns_for_missing_geocode_and_evidence(self) -> None:
        payload = build_module_payload(
            tenant_slug="quality-window-warn",
            module_key="windowpilot",
            campaign_key="quality-window-warn",
            address="Qualitylaan 2",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["properties"][0].pop("lat")
        payload["properties"][0].pop("lon")
        payload["assessments"][0]["evidence"] = []
        report = build_data_quality_report(payload)
        self.assertEqual(report["status"], "warn")
        self.assertEqual(report["metrics"]["geocode_coverage_pct"], 0.0)
        self.assertEqual(report["metrics"]["evidence_coverage_pct"], 0.0)
        self.assertTrue(report["warnings"])

    def test_data_quality_fails_for_missing_scores(self) -> None:
        payload = build_module_payload(
            tenant_slug="quality-window-fail",
            module_key="windowpilot",
            campaign_key="quality-window-fail",
            address="Qualitylaan 3",
            city="Leuven",
            lat=50.88,
            lon=4.70,
            score=91,
        )
        payload["assessments"][0]["score"] = None
        report = build_data_quality_report(payload)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("Score coverage" in item for item in report["failures"]))

    def test_benchmarks_skip_small_cohorts(self) -> None:
        payloads = [
            build_module_payload(
                tenant_slug=f"benchmark-window-{index}",
                module_key="windowpilot",
                campaign_key=f"window-{index}",
                address=f"Benchmarklaan {index}",
                city="Leuven",
                lat=50.80 + index / 1000,
                lon=4.70,
                score=80 + (index % 10),
            )
            for index in range(9)
        ]
        self.assertEqual(build_benchmark_rows(payloads, min_sample_size=10), [])

    def test_benchmarks_publish_only_aggregate_metrics_at_threshold(self) -> None:
        payloads = [
            build_module_payload(
                tenant_slug=f"benchmark-window-{index}",
                module_key="windowpilot",
                campaign_key=f"window-{index}",
                address=f"Benchmarklaan {index}",
                city="Leuven",
                lat=50.80 + index / 1000,
                lon=4.70,
                score=80 + (index % 10),
            )
            for index in range(10)
        ]
        rows = build_benchmark_rows(payloads, min_sample_size=10, computed_at="2026-06-19T00:00:00+00:00")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["module_key"], "windowpilot")
        self.assertEqual(row["sample_size"], 10)
        self.assertEqual(row["cohort"]["scope"], "platform")
        self.assertEqual(row["metrics"]["response_count"], 10)
        self.assertEqual(row["metrics"]["response_rate_pct"], 100.0)
        self.assertNotIn("tenant_id", json.dumps(row))
        self.assertNotIn("property_id", json.dumps(row))
        self.assertNotIn("Benchmarklaan", json.dumps(row))
        validate_benchmark_rows(rows, min_sample_size=10)

    def test_benchmark_validation_rejects_raw_fields(self) -> None:
        row = build_benchmark_rows([
            build_module_payload(
                tenant_slug=f"benchmark-facade-{index}",
                module_key="facadepilot",
                campaign_key=f"facade-{index}",
                address=f"Gevel Benchmark {index}",
                city="Gent",
                lat=51.00 + index / 1000,
                lon=3.70,
                score=82,
            )
            for index in range(10)
        ])[0]
        row["metrics"]["tenant_id"] = "should-not-leak"
        with self.assertRaises(ValueError):
            validate_benchmark_rows([row], min_sample_size=10)

    def test_due_diligence_pack_builds_buyer_evidence_without_customer_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "readiness"
            readiness = build_readiness_pack(out_dir, run_qa=False)
            due_dir = Path(tmp) / "due_diligence"
            report = build_due_diligence_pack(
                due_dir,
                readiness_report_path=Path(readiness["paths"]["readiness_report"]),
                modules=["windowpilot"],
                role="viewer",
            )
            summary = (due_dir / "executive_summary.md").read_text(encoding="utf-8")
            dashboard_matrix = json.loads((due_dir / "access_matrices" / "dashboard_access_matrix.json").read_text(encoding="utf-8"))
            data_dictionary = json.loads((due_dir / "evidence" / "data_dictionary" / "data_dictionary.json").read_text(encoding="utf-8"))
            api_contract = json.loads((due_dir / "evidence" / "api_contract" / "api_contract.json").read_text(encoding="utf-8"))
            processing_register = json.loads((due_dir / "evidence" / "processing_register" / "processing_register.json").read_text(encoding="utf-8"))
            redaction = json.loads((due_dir / "evidence" / "redaction_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "local_ready")
        self.assertFalse(report["production_gate"]["verified"])
        self.assertEqual(report["readiness"]["status"], "pass")
        self.assertEqual(report["redaction"]["status"], "pass")
        self.assertEqual(redaction["issues"], [])
        self.assertIn("HomePilot Enterprise Due-Diligence Pack", summary)
        self.assertEqual([module["key"] for module in dashboard_matrix["modules"]], ["windowpilot"])
        self.assertEqual(data_dictionary["modules_selected"], ["windowpilot"])
        self.assertEqual(api_contract["modules_selected"], ["windowpilot"])
        self.assertEqual(processing_register["modules_selected"], ["windowpilot"])
        self.assertIn("data_dictionary", report["paths"])
        self.assertIn("api_contract", report["paths"])
        self.assertIn("processing_register", report["paths"])
        self.assertNotIn("facadepilot", json.dumps(dashboard_matrix).lower())

    def test_due_diligence_redaction_scan_detects_secret_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.txt"
            path.write_text("internal_model_prompt: secret prompt\n", encoding="utf-8")
            report = scan_generated_files([path])
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["issues"][0]["pattern"], "secret_prompt")

    def test_account_access_pack_builds_invitation_membership_and_revocation_evidence(self) -> None:
        owner_id = "33333333-3333-4333-8333-333333333333"
        manager_id = "44444444-4444-4444-8444-444444444444"
        onboarding = build_onboarding_payload(
            name="Window Enterprise",
            slug="window-enterprise",
            modules=["windowpilot"],
            memberships=[f"{owner_id}:owner"],
        )
        invitees = [
            parse_invitee(f"owner@example.com:owner:{owner_id}"),
            parse_invitee(f"manager@example.com:manager:{manager_id}"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            pack = build_account_access_pack(Path(tmp), onboarding=onboarding, invitees=invitees)
            plan_path = Path(pack["paths"]["account_access_plan"])
            markdown_path = Path(pack["paths"]["markdown"])
            upsert_path = Path(pack["paths"]["membership_upsert_sql"])
            revocation_path = Path(pack["paths"]["membership_revocation_sql"])
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
            membership_sql = upsert_path.read_text(encoding="utf-8").lower()
            revocation_sql = revocation_path.read_text(encoding="utf-8").lower()

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["review_status"], "ready")
        self.assertEqual(plan["enabled_modules"], ["windowpilot"])
        self.assertEqual(plan["role_counts"], {"manager": 1, "owner": 1})
        self.assertEqual(len(plan["membership_rows"]), 2)
        self.assertIn("member_manage", plan["invitees"][0]["permissions"])
        self.assertIn("billing_manage", plan["invitees"][0]["permissions"])
        self.assertFalse(plan["guardrails"]["passwords_included"])
        self.assertFalse(plan["guardrails"]["service_role_keys_included"])
        self.assertIn("HomePilot Account Access Plan", markdown)
        self.assertIn("insert into public.homepilot_memberships", membership_sql)
        self.assertIn("tenant_id, user_id, role, partner_id", membership_sql)
        self.assertIn("on conflict (tenant_id, user_id)", membership_sql)
        self.assertIn("delete from public.homepilot_memberships", revocation_sql)
        self.assertNotIn("owner@example.com", membership_sql)
        self.assertNotIn("manager@example.com", membership_sql)
        self.assertNotIn("password", membership_sql)
        self.assertNotIn("service-role", membership_sql)

    def test_account_access_plan_requires_auth_user_ids_before_ready(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Pending Auth",
            slug="window-pending-auth",
            modules=["windowpilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_account_access_pack(
                Path(tmp),
                onboarding=onboarding,
                invitees=[parse_invitee("owner@example.com:owner")],
            )
            membership_sql = Path(pack["paths"]["membership_upsert_sql"]).read_text(encoding="utf-8")

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["review_status"], "review_required")
        self.assertEqual(pack["plan"]["membership_rows"], [])
        self.assertTrue(any("missing Supabase Auth user_id" in warning for warning in pack["plan"]["warnings"]))
        self.assertIn("create/invite Supabase Auth users first", membership_sql)

    def test_account_access_plan_rejects_duplicate_invitees(self) -> None:
        onboarding = build_onboarding_payload(
            name="Window Duplicate",
            slug="window-duplicate",
            modules=["windowpilot"],
        )
        plan = build_account_access_plan(
            onboarding,
            invitees=[
                parse_invitee("owner@example.com:owner:55555555-5555-4555-8555-555555555555"),
                parse_invitee("OWNER@example.com:manager:66666666-6666-4666-8666-666666666666"),
            ],
        )
        self.assertEqual(plan["status"], "fail")
        self.assertTrue(any("Duplicate invitee email" in failure for failure in plan["failures"]))

    def test_account_access_pack_supports_partner_scoped_memberships(self) -> None:
        owner_id = "55555555-5555-4555-8555-555555555555"
        partner_id = "66666666-6666-4666-8666-666666666666"
        onboarding = build_onboarding_payload(
            name="DAW Partner Access",
            slug="daw-partner-access",
            modules=["facadepilot"],
        )
        invitees = [
            parse_invitee(f"owner@example.com:owner:{owner_id}"),
            parse_invitee(f"renotec@example.com:manager:{partner_id}:renotec-antwerp"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_account_access_pack(Path(tmp), onboarding=onboarding, invitees=invitees)
            membership_sql = Path(pack["paths"]["membership_upsert_sql"]).read_text(encoding="utf-8").lower()
            markdown = Path(pack["paths"]["markdown"]).read_text(encoding="utf-8").lower()

        self.assertEqual(pack["status"], "pass")
        self.assertEqual(pack["review_status"], "ready")
        self.assertEqual(pack["plan"]["scope_counts"], {"tenant": 1, "partner": 1})
        self.assertEqual(pack["plan"]["membership_rows"][1]["partner_id"], "renotec-antwerp")
        self.assertEqual(pack["plan"]["invitees"][1]["access_scope"], "partner")
        self.assertIn("renotec-antwerp", membership_sql)
        self.assertIn("partner_id = excluded.partner_id", membership_sql)
        self.assertIn("scope: partner `renotec-antwerp`", markdown)

    def test_customer_access_verification_dry_run_builds_redacted_probe_contract(self) -> None:
        owner_id = "77777777-7777-4777-8777-777777777777"
        onboarding = build_onboarding_payload(
            name="Window Access Verify",
            slug="window-access-verify",
            modules=["windowpilot"],
            memberships=[f"{owner_id}:owner"],
        )
        invitees = [parse_invitee(f"owner@example.com:owner:{owner_id}")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(root / "account", onboarding=onboarding, invitees=invitees)
            plan_path = Path(account_pack["paths"]["account_access_plan"])
            report = build_customer_access_verification(
                root / "verify",
                account_access_plan=load_account_access_plan(plan_path),
                dry_run=True,
                env={"HOMEPILOT_ACCESS_OWNER_OWNER_EXAMPLE_COM_TOKEN": "secret-token-value"},
            )
            contract = json.loads(Path(report["paths"]["probe_contract"]).read_text(encoding="utf-8"))
            markdown = Path(report["paths"]["markdown"]).read_text(encoding="utf-8")
            access_lens_matrix_exists = Path(report["paths"]["access_lens_matrix"]).exists()
            combined_output = "\n".join(path.read_text(encoding="utf-8") for path in (root / "verify").iterdir())

        self.assertEqual(report["status"], "dry_run")
        self.assertFalse(report["production_verified"])
        self.assertEqual(report["rls_probe"]["status"], "skipped_dry_run")
        self.assertEqual(report["identities"][0]["credential_status"], "not_required_for_dry_run")
        self.assertEqual(report["access_lens_proof"]["status"], "review_ready")
        self.assertEqual(report["access_lens_proof"]["summary"]["missing_lenses"], 0)
        self.assertTrue(access_lens_matrix_exists)
        self.assertFalse(report["guardrails"]["secrets_written"])
        self.assertEqual(contract["identities"][0]["token_env"], "HOMEPILOT_ACCESS_OWNER_OWNER_EXAMPLE_COM_TOKEN")
        self.assertTrue(contract["guardrails"]["partner_scoped"])
        self.assertTrue(report["guardrails"]["partner_scoped"])
        self.assertIn("HomePilot Customer Access Verification", markdown)
        self.assertIn("Access Lens Proof", markdown)
        self.assertNotIn("secret-token-value", combined_output)
        self.assertNotIn("service-role", combined_output.lower())

    def test_customer_access_verification_passes_partner_scope_to_probe(self) -> None:
        owner_id = "77777777-7777-4777-8777-777777777778"
        partner_user_id = "77777777-7777-4777-8777-777777777779"
        onboarding = build_onboarding_payload(
            name="DAW Partner Verify",
            slug="daw-partner-verify",
            modules=["facadepilot"],
        )
        captured: dict[str, dict] = {}

        def fake_probe(config: dict, url: str, anon_key: str, allow_empty: bool) -> dict:
            captured["config"] = config
            return {"report_type": "homepilot_rls_probe", "status": "pass", "identities": []}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[
                    parse_invitee(f"owner@example.com:owner:{owner_id}"),
                    parse_invitee(f"renotec@example.com:manager:{partner_user_id}:renotec-antwerp"),
                ],
            )
            report = build_customer_access_verification(
                root / "verify",
                account_access_plan=account_pack["plan"],
                url="https://example.supabase.co",
                anon_key="anon-key",
                dry_run=False,
                env={
                    "HOMEPILOT_ACCESS_OWNER_OWNER_EXAMPLE_COM_TOKEN": "owner-token",
                    "HOMEPILOT_ACCESS_MANAGER_RENOTEC_EXAMPLE_COM_TOKEN": "partner-token",
                },
                probe_runner=fake_probe,
            )
            contract = json.loads(Path(report["paths"]["probe_contract"]).read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["identities"][1]["partner_id"], "renotec-antwerp")
        self.assertEqual(contract["identities"][1]["access_scope"], "partner")
        self.assertEqual(captured["config"]["identities"][1]["partner_id"], "renotec-antwerp")

    def test_customer_access_verification_maps_dashboard_access_lenses_to_identities(self) -> None:
        owner_id = "77777777-7777-4777-8777-777777777780"
        partner_user_id = "77777777-7777-4777-8777-777777777781"
        payload = build_demo_payload(
            tenant_slug="daw-access-lens-proof",
            property_count=60,
            scenario="daw",
        )
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-access-lens-proof",
            enabled_modules=["facadepilot"],
        )
        first_partner = snapshot["network"]["partners"][0]["id"]
        onboarding = build_onboarding_payload(
            name="DAW Access Lens Proof",
            slug="daw-access-lens-proof",
            modules=["facadepilot"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[
                    parse_invitee(f"owner@example.com:owner:{owner_id}"),
                    parse_invitee(f"partner@example.com:manager:{partner_user_id}:{first_partner}"),
                ],
            )
            report = build_customer_access_verification(
                root / "verify",
                account_access_plan=account_pack["plan"],
                dry_run=True,
                dashboard_snapshot=snapshot,
                env={
                    "HOMEPILOT_ACCESS_OWNER_OWNER_EXAMPLE_COM_TOKEN": "owner-secret",
                    "HOMEPILOT_ACCESS_MANAGER_PARTNER_EXAMPLE_COM_TOKEN": "partner-secret",
                },
            )
            matrix = Path(report["paths"]["access_lens_matrix"]).read_text(encoding="utf-8")
            combined_output = "\n".join(path.read_text(encoding="utf-8") for path in (root / "verify").iterdir())

        lenses = {row["lens_key"]: row for row in report["access_lens_proof"]["lenses"]}
        self.assertEqual(report["access_lens_proof"]["source"], "dashboard_snapshot")
        self.assertEqual(report["access_lens_proof"]["status"], "review_ready")
        self.assertEqual(report["access_lens_proof"]["summary"]["network_partner_count"], 10)
        self.assertEqual(report["access_lens_proof"]["summary"]["partner_identities"], 1)
        self.assertEqual(lenses["producer_network"]["coverage_status"], "covered")
        self.assertEqual(lenses["module_only_customer"]["coverage_status"], "covered")
        self.assertEqual(lenses["partner_renovator"]["coverage_status"], "sample_covered_pending_partner_reconciliation")
        self.assertIn("producer_network", matrix)
        self.assertIn("partner_renovator", matrix)
        self.assertIn("sample_covered_pending_partner_reconciliation", matrix)
        self.assertTrue(report["access_lens_proof"]["guardrails"]["runtime_authorization_remains_supabase_rls"])
        self.assertNotIn("owner-secret", combined_output)
        self.assertNotIn("partner-secret", combined_output)
        self.assertNotIn("service-role", combined_output.lower())

    def test_customer_access_verification_requires_live_credentials_before_production(self) -> None:
        owner_id = "88888888-8888-4888-8888-888888888888"
        onboarding = build_onboarding_payload(
            name="Window Missing Credentials",
            slug="window-missing-credentials",
            modules=["windowpilot"],
            memberships=[f"{owner_id}:owner"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[parse_invitee(f"owner@example.com:owner:{owner_id}")],
            )
            report = build_customer_access_verification(
                root / "verify",
                account_access_plan=account_pack["plan"],
                url="https://example.supabase.co",
                anon_key="anon-key",
                dry_run=False,
                env={},
            )

        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["production_verified"])
        self.assertEqual(report["rls_probe"]["status"], "skipped_missing_credentials")
        self.assertTrue(any("Missing credentials" in failure for failure in report["failures"]))

    def test_customer_access_verification_can_prove_production_with_env_token_and_probe_pass(self) -> None:
        owner_id = "99999999-9999-4999-8999-999999999999"
        onboarding = build_onboarding_payload(
            name="Window Live Token",
            slug="window-live-token",
            modules=["windowpilot"],
            memberships=[f"{owner_id}:owner"],
        )

        def fake_probe(config: dict, url: str, anon_key: str, allow_empty: bool) -> dict:
            self.assertEqual(url, "https://example.supabase.co")
            self.assertEqual(anon_key, "anon-key")
            self.assertFalse(allow_empty)
            self.assertEqual(config["identities"][0]["access_token"], "secret-token-value")
            return {
                "report_type": "homepilot_rls_probe",
                "status": "pass",
                "identities": [{"label": config["identities"][0]["label"], "status": "pass"}],
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[parse_invitee(f"owner@example.com:owner:{owner_id}")],
            )
            report = build_customer_access_verification(
                root / "verify",
                account_access_plan=account_pack["plan"],
                url="https://example.supabase.co",
                anon_key="anon-key",
                dry_run=False,
                env={"HOMEPILOT_ACCESS_OWNER_OWNER_EXAMPLE_COM_TOKEN": "secret-token-value"},
                probe_runner=fake_probe,
            )
            combined_output = "\n".join(path.read_text(encoding="utf-8") for path in (root / "verify").iterdir())

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["production_verified"])
        self.assertEqual(report["rls_probe"]["status"], "pass")
        self.assertEqual(report["identities"][0]["credential_mode_used"], "access_token_env")
        self.assertNotIn("secret-token-value", combined_output)

    def test_live_readiness_reports_missing_inputs_without_writing_secrets(self) -> None:
        owner_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        onboarding = build_onboarding_payload(
            name="DAW Live Readiness",
            slug="daw-live-readiness",
            modules=["facadepilot"],
            memberships=[f"{owner_id}:owner"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[parse_invitee(f"owner@example.com:owner:{owner_id}")],
            )
            report = build_live_readiness_report(
                root / "live_readiness",
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                readiness_report_path=root / "readiness_report.json",
                due_diligence_report_path=root / "due_diligence_report.json",
                env={},
            )
            combined_output = "\n".join(path.read_text(encoding="utf-8") for path in (root / "live_readiness").iterdir())

        self.assertEqual(report["status"], "action_required")
        self.assertFalse(report["ready_to_run_live_cutover"])
        self.assertFalse(report["guardrails"]["secrets_written"])
        self.assertTrue(any("supabase" in item for item in report["missing_live_inputs"]))
        self.assertTrue(any("Missing customer access credential" in item for item in report["missing_live_inputs"]))
        self.assertIn("HOMEPILOT_RLS_WINDOW_PASSWORD", combined_output)
        self.assertNotIn("secret-token-value", combined_output)

    def test_live_launch_request_pack_turns_missing_inputs_into_safe_checklist(self) -> None:
        owner_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        onboarding = build_onboarding_payload(
            name="DAW Launch Request",
            slug="daw-launch-request",
            modules=["facadepilot"],
            memberships=[f"{owner_id}:owner"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[parse_invitee(f"owner@example.com:owner:{owner_id}")],
            )
            live_readiness = build_live_readiness_report(
                root / "live_readiness",
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                readiness_report_path=root / "readiness_report.json",
                due_diligence_report_path=root / "due_diligence_report.json",
                env={},
            )
            report = build_live_launch_request_pack(
                root / "launch_request",
                live_readiness_report_path=Path(live_readiness["paths"]["live_readiness"]),
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                release_label="launch-request-test",
            )
            checklist = (root / "launch_request" / "LIVE_LAUNCH_CHECKLIST.csv").read_text(encoding="utf-8")
            env_template = (root / "launch_request" / "live_launch.env.template").read_text(encoding="utf-8")
            request_email = (root / "launch_request" / "LIVE_LAUNCH_REQUEST_EMAIL.txt").read_text(encoding="utf-8")
            combined_output = "\n".join(path.read_text(encoding="utf-8") for path in (root / "launch_request").iterdir())

        self.assertEqual(report["status"], "action_required")
        self.assertGreaterEqual(report["summary"]["task_count"], 8)
        self.assertEqual(report["summary"]["by_owner"]["platform_admin"], 4)
        self.assertFalse(report["guardrails"]["secrets_written"])
        self.assertIn("HOMEPILOT_SUPABASE_URL", checklist)
        self.assertIn("HOMEPILOT_SUPABASE_SERVICE_KEY", env_template)
        self.assertIn("Do not send secrets by email", request_email)
        self.assertIn("set-secret-value", combined_output)
        self.assertNotIn("secret-token-value", combined_output)

    def test_live_proof_plan_turns_live_blockers_into_guarded_execution_plan(self) -> None:
        owner_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        onboarding = build_onboarding_payload(
            name="DAW Live Proof",
            slug="daw-live-proof",
            modules=["facadepilot"],
            memberships=[f"{owner_id}:owner"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            due_path = root / "due.json"
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[parse_invitee(f"owner@example.com:owner:{owner_id}")],
            )
            readiness_path.write_text(
                json.dumps({"status": "pass", "paths": {"account_access_smoke": str(root / "account")}}),
                encoding="utf-8",
            )
            due_path.write_text(json.dumps({"status": "local_ready"}), encoding="utf-8")
            live_readiness = build_live_readiness_report(
                root / "live_readiness",
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                readiness_report_path=readiness_path,
                due_diligence_report_path=due_path,
                release_label="live-proof-test",
                env={},
            )
            live_request = build_live_launch_request_pack(
                root / "launch_request",
                live_readiness_report_path=Path(live_readiness["paths"]["live_readiness"]),
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                release_label="live-proof-test",
            )
            cutover_path = root / "cutover.json"
            cutover_path.write_text(
                json.dumps({
                    "steps": [
                        {"name": "schema_verification", "detail": "Schema verification status is dry_run."},
                        {"name": "rls_launch", "detail": "RLS launch status is dry_run."},
                        {"name": "customer_access_verification", "detail": "Customer access verification status is dry_run."},
                    ],
                    "paths": {
                        "schema_verification": str(root / "schema_verification.json"),
                        "launch_report": str(root / "launch_report.json"),
                        "customer_access_verification": str(root / "customer_access_verification.json"),
                    },
                }),
                encoding="utf-8",
            )
            proof_path = root / "production_proof.json"
            proof_path.write_text(
                json.dumps({
                    "status": "buyer_review_ready",
                    "production_gate": {
                        "verified": False,
                        "blockers": ["Live readiness status is 'action_required', expected 'ready'."],
                    },
                    "paths": {"production_proof": str(proof_path)},
                }),
                encoding="utf-8",
            )
            index_path = root / "artifact_index.json"
            index_path.write_text(json.dumps({"status": "buyer_review_ready"}), encoding="utf-8")
            plan = build_live_proof_plan_pack(
                root / "plan",
                readiness_report_path=readiness_path,
                due_diligence_report_path=due_path,
                live_readiness_report_path=Path(live_readiness["paths"]["live_readiness"]),
                live_launch_request_path=Path(live_request["paths"]["live_launch_request"]),
                production_cutover_report_path=cutover_path,
                production_proof_path=proof_path,
                artifact_index_path=index_path,
                release_label="live-proof-test",
            )
            report = json.loads((root / "plan" / "live_proof_execution_plan.json").read_text(encoding="utf-8"))
            markdown = (root / "plan" / "LIVE_PROOF_EXECUTION_PLAN.md").read_text(encoding="utf-8")
            evidence_csv = (root / "plan" / "LIVE_PROOF_EVIDENCE_MAP.csv").read_text(encoding="utf-8")
            commands = (root / "plan" / "LIVE_PROOF_COMMANDS.sh").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (root / "plan").iterdir()
                if path.is_file()
            )

        self.assertEqual(plan["status"], "blocked_until_live_inputs")
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertGreater(report["summary"]["live_launch_task_count"], 0)
        self.assertFalse(report["summary"]["production_verified"])
        self.assertTrue(report["guardrails"]["manual_sql_and_customer_signoff_confirmations_required"])
        self.assertTrue(report["guardrails"]["regenerated_live_readiness_gate_required"])
        self.assertTrue(report["guardrails"]["plan_validation_required"])
        self.assertEqual(report["plan_validation"]["status"], "pass")
        validation_by_key = {check["key"]: check for check in report["plan_validation"]["checks"]}
        self.assertEqual(validation_by_key["step_order"]["status"], "pass")
        self.assertEqual(validation_by_key["readiness_gate_command"]["status"], "pass")
        self.assertEqual(validation_by_key["manual_cutover_confirmations"]["status"], "pass")
        self.assertEqual(validation_by_key["downstream_uses_regenerated_readiness"]["status"], "pass")
        self.assertEqual(validation_by_key["stale_live_readiness_not_reused"]["status"], "pass")
        self.assertEqual(validation_by_key["secret_scan_pass"]["status"], "pass")
        readiness_gate = next(step for step in report["execution_steps"] if step["step_key"] == "verify_live_readiness_ready")
        self.assertEqual(readiness_gate["command_key"], "verify_live_readiness_ready")
        self.assertEqual(readiness_gate["status"], "blocked")
        cutover_step = next(step for step in report["execution_steps"] if step["step_key"] == "run_live_cutover")
        self.assertEqual(
            cutover_step["required_env_confirmations"]["HOMEPILOT_SQL_APPLY_CONFIRM"],
            "reviewed-sql-applied",
        )
        self.assertEqual(
            cutover_step["required_env_confirmations"]["HOMEPILOT_CUSTOMER_LIVE_PROOF_CONFIRM"],
            "customer-approved-live-proof",
        )
        self.assertIn("schema_verification", evidence_csv)
        self.assertIn("customer_access_verification", evidence_csv)
        self.assertIn("HomePilot Live Proof Execution Plan", markdown)
        self.assertIn("Plan Validation", markdown)
        self.assertIn("downstream_uses_regenerated_readiness: pass", markdown)
        self.assertIn("homepilot_production_cutover.py --live", markdown)
        self.assertIn("HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof", commands)
        self.assertIn("verify_live_readiness_ready", report["commands"])
        self.assertIn("ready_to_run_live_cutover", report["commands"]["verify_live_readiness_ready"])
        self.assertIn("ready_to_run_live_cutover", commands)
        self.assertIn("HOMEPILOT_SQL_APPLY_CONFIRM=reviewed-sql-applied", markdown)
        self.assertIn("HOMEPILOT_CUSTOMER_LIVE_PROOF_CONFIRM=customer-approved-live-proof", markdown)
        self.assertIn('HOMEPILOT_SQL_APPLY_CONFIRM:-}" != "reviewed-sql-applied"', commands)
        self.assertIn(
            'HOMEPILOT_CUSTOMER_LIVE_PROOF_CONFIRM:-}" != "customer-approved-live-proof"',
            commands,
        )
        self.assertIn("homepilot_market_readiness.py", commands)
        generated_live_readiness = root / "plan" / "live_execution" / "live_readiness" / "live_readiness.json"
        original_live_readiness = Path(live_readiness["paths"]["live_readiness"])
        self.assertIn(str(generated_live_readiness), report["commands"]["verify_live_readiness_ready"])
        self.assertIn(f"--live-readiness-report {generated_live_readiness}", report["commands"]["regenerate_release"])
        self.assertIn(f"--live-readiness-report {generated_live_readiness}", report["commands"]["regenerate_market"])
        self.assertIn(str(Path(live_request["paths"]["live_launch_request"])), report["commands"]["regenerate_market"])
        self.assertNotIn(str(original_live_readiness), report["commands"]["regenerate_release"])
        self.assertNotIn(str(original_live_readiness), report["commands"]["regenerate_market"])
        self.assertNotIn("secret-token-value", combined_output)
        self.assertNotIn("postgresql://postgres:password@", combined_output)

    def test_live_proof_evidence_vault_indexes_proof_artifacts_without_secrets(self) -> None:
        owner_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        onboarding = build_onboarding_payload(
            name="DAW Live Proof Vault",
            slug="daw-live-proof-vault",
            modules=["facadepilot"],
            memberships=[f"{owner_id}:owner"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            due_path = root / "due.json"
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[parse_invitee(f"owner@example.com:owner:{owner_id}")],
            )
            readiness_path.write_text(
                json.dumps({"status": "pass", "paths": {"account_access_smoke": str(root / "account")}}),
                encoding="utf-8",
            )
            due_path.write_text(json.dumps({"status": "local_ready"}), encoding="utf-8")
            live_readiness = build_live_readiness_report(
                root / "live_readiness",
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                readiness_report_path=readiness_path,
                due_diligence_report_path=due_path,
                release_label="live-proof-vault-test",
                env={},
            )
            live_request = build_live_launch_request_pack(
                root / "launch_request",
                live_readiness_report_path=Path(live_readiness["paths"]["live_readiness"]),
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                release_label="live-proof-vault-test",
            )
            proof_path = root / "production_proof.json"
            production_proof = {
                "status": "buyer_review_ready",
                "production_gate": {
                    "verified": False,
                    "blockers": ["Live readiness status is 'action_required', expected 'ready'."],
                },
                "paths": {"production_proof": str(proof_path)},
            }
            proof_path.write_text(json.dumps(production_proof), encoding="utf-8")
            index_path = root / "artifact_index.json"
            index_path.write_text(json.dumps({"status": "buyer_review_ready"}), encoding="utf-8")
            plan = build_live_proof_plan_pack(
                root / "plan",
                readiness_report_path=readiness_path,
                due_diligence_report_path=due_path,
                live_readiness_report_path=Path(live_readiness["paths"]["live_readiness"]),
                live_launch_request_path=Path(live_request["paths"]["live_launch_request"]),
                production_proof_path=proof_path,
                artifact_index_path=index_path,
                release_label="live-proof-vault-test",
            )
            vault = build_live_proof_evidence_vault_pack(
                root / "vault",
                artifact_paths={
                    "production_proof": str(proof_path),
                    "live_readiness_report": live_readiness["paths"]["live_readiness"],
                    "live_launch_request": live_request["paths"]["live_launch_request"],
                    "live_proof_plan": plan["paths"]["markdown"],
                },
                live_readiness=live_readiness,
                live_launch_request=live_request,
                live_proof_plan=plan,
                production_proof=production_proof,
                release_label="live-proof-vault-test",
            )
            report = json.loads((root / "vault" / "live_proof_evidence_vault.json").read_text(encoding="utf-8"))
            markdown = (root / "vault" / "LIVE_PROOF_EVIDENCE_VAULT.md").read_text(encoding="utf-8")
            archive_csv = (root / "vault" / "LIVE_PROOF_ARCHIVE_INDEX.csv").read_text(encoding="utf-8")
            combined_output = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (root / "vault").iterdir()
                if path.is_file()
            )

        rows_by_key = {row["key"]: row for row in report["evidence_rows"]}
        self.assertEqual(vault["status"], "live_proof_blocked")
        self.assertEqual(report["vault_type"], "homepilot_live_proof_evidence_vault")
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertGreaterEqual(report["summary"]["required_count"], 14)
        self.assertGreaterEqual(report["summary"]["archived_count"], 4)
        self.assertFalse(report["summary"]["production_verified"])
        self.assertEqual(report["summary"]["production_verified_label"], "production_verified=false")
        self.assertEqual(rows_by_key["live_proof_execution_plan"]["current_status"], "pass")
        self.assertEqual(rows_by_key["production_proof_gate"]["current_status"], "blocked")
        self.assertEqual(rows_by_key["customer_access_report"]["current_status"], "blocked")
        self.assertIn("HomePilot Live Proof Evidence Vault", markdown)
        self.assertIn("schema_verification_report", archive_csv)
        self.assertIn("customer_access_report", archive_csv)
        self.assertIn("production_proof_gate", archive_csv)
        self.assertTrue(report["guardrails"]["non_mutating"])
        self.assertTrue(report["guardrails"]["no_secret_values"])
        self.assertTrue(report["guardrails"]["no_raw_contact_data"])
        self.assertNotIn("service_role=", combined_output)
        self.assertNotIn("authorization: bearer", combined_output.lower())
        self.assertNotIn("@example.com", combined_output)

    def test_live_readiness_passes_with_redacted_env_credentials(self) -> None:
        owner_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        onboarding = build_onboarding_payload(
            name="Window Live Ready",
            slug="window-live-ready",
            modules=["windowpilot"],
            memberships=[f"{owner_id}:owner"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_pack = build_account_access_pack(
                root / "account",
                onboarding=onboarding,
                invitees=[parse_invitee(f"owner@example.com:owner:{owner_id}")],
            )
            report = build_live_readiness_report(
                root / "live_readiness",
                account_access_plan_path=Path(account_pack["paths"]["account_access_plan"]),
                env={
                    "HOMEPILOT_SUPABASE_URL": "https://live-project.supabase.co",
                    "HOMEPILOT_SUPABASE_SERVICE_KEY": "live-service-key",
                    "HOMEPILOT_SUPABASE_ANON_KEY": "live-anon-runtime-key",
                    "HOMEPILOT_SUPABASE_DB_URL": "postgresql://postgres:live-db-password@db.live-project.supabase.co:5432/postgres",
                    "HOMEPILOT_RLS_WINDOW_PASSWORD": "strong-window-password",
                    "HOMEPILOT_RLS_FACADE_PASSWORD": "strong-facade-password",
                    "HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD": "strong-partner-password",
                    "HOMEPILOT_ACCESS_OWNER_OWNER_EXAMPLE_COM_TOKEN": "customer-token-secret",
                },
            )
            combined_output = "\n".join(path.read_text(encoding="utf-8") for path in (root / "live_readiness").iterdir())

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["ready_to_run_live_cutover"])
        self.assertEqual(report["groups"]["supabase"]["status"], "pass")
        self.assertEqual(report["groups"]["rls_fixture"]["status"], "pass")
        self.assertEqual(report["customer_access"]["status"], "pass")
        self.assertIn("homepilot_production_cutover.py --live", report["commands"]["production_cutover"])
        self.assertNotIn("customer-token-secret", combined_output)
        self.assertNotIn("live-service-key", combined_output)

    def test_readiness_pack_builds_local_evidence_without_claiming_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "readiness"
            report = build_readiness_pack(out_dir, run_qa=False)
            saved_report = json.loads((out_dir / "readiness_report.json").read_text(encoding="utf-8"))
            cleanup_sql_exists = (out_dir / "launch_dry_run" / "cleanup_plan.sql").exists()
            deployment_exists = (out_dir / "deployment_smoke" / "deployment_manifest.json").exists()
            schema_verification_exists = (out_dir / "schema_verification_smoke" / "schema_verification.json").exists()
            account_access_exists = (out_dir / "account_access_smoke" / "account_access_plan.json").exists()
            customer_access_verification_exists = (out_dir / "customer_access_verification_smoke" / "customer_access_verification.json").exists()
            access_lens_matrix_exists = (out_dir / "customer_access_verification_smoke" / "ACCESS_LENS_PROOF_MATRIX.csv").exists()
            live_readiness_exists = (out_dir / "live_readiness_smoke" / "live_readiness.json").exists()
            live_launch_request_exists = (out_dir / "live_launch_request_smoke" / "live_launch_request.json").exists()
            live_launch_checklist_exists = (out_dir / "live_launch_request_smoke" / "LIVE_LAUNCH_CHECKLIST.csv").exists()
            live_launch_env_template_exists = (out_dir / "live_launch_request_smoke" / "live_launch.env.template").exists()
            api_contract_exists = (out_dir / "api_contract_smoke" / "api_contract.json").exists()
            customer_brief_exists = (out_dir / "customer_brief_smoke" / "customer_brief.json").exists()
            campaign_learning_exists = (out_dir / "campaign_learning_smoke" / "campaign_learning.json").exists()
            territory_plan_exists = (out_dir / "territory_plan_smoke" / "territory_plan.json").exists()
            roi_forecast_exists = (out_dir / "roi_forecast_smoke" / "roi_forecast.json").exists()
            opportunity_dossier_exists = (out_dir / "opportunity_dossier_smoke" / "opportunity_dossier.json").exists()
            source_ledger_exists = (out_dir / "source_ledger_smoke" / "source_ledger.json").exists()
            processing_register_exists = (out_dir / "processing_register_smoke" / "processing_register.json").exists()
            dictionary_exists = (out_dir / "data_dictionary_smoke" / "data_dictionary.json").exists()
            package_manifest_exists = (out_dir / "customer_package_smoke" / "package" / "manifest.json").exists()
            package_boardroom_report_exists = (out_dir / "customer_package_smoke" / "package" / "data" / "boardroom_report" / "boardroom_report.json").exists()
            package_boardroom_html_exists = (out_dir / "customer_package_smoke" / "package" / "dashboard" / "boardroom-report.html").exists()
            portal_manifest_exists = (out_dir / "customer_portal_smoke" / "portal_manifest.json").exists()
            portal_live_config_exists = (out_dir / "customer_portal_smoke" / "public" / "live-config.js").exists()
            portal_live_loader_exists = (out_dir / "customer_portal_smoke" / "public" / "live-data.js").exists()
            portal_hosting_exists = (out_dir / "portal_hosting_smoke" / "hosting_manifest.json").exists()
            integration_manifest_exists = (out_dir / "sales_integration_smoke" / "integration_manifest.json").exists()
            integration_sync_exists = (out_dir / "sales_integration_sync_smoke" / "sync_report.json").exists()
            enrichment_plan_exists = (out_dir / "data_vendor_enrichment_smoke" / "data_vendor_plan.json").exists()
            enrichment_refresh_exists = (out_dir / "data_vendor_refresh_smoke" / "enrichment_refresh_report.json").exists()
            demo_room_manifest_exists = (out_dir / "enterprise_demo_room_smoke" / "manifest.json").exists()
            boardroom_report_exists = (out_dir / "boardroom_report_smoke" / "boardroom_report.json").exists()
            boardroom_html_exists = (out_dir / "boardroom_report_smoke" / "dashboard" / "boardroom-report.html").exists()
            boardroom_partner_summary_exists = (out_dir / "boardroom_report_smoke" / "partner_summary.csv").exists()
            partner_cutdown_manifest_exists = (out_dir / "partner_cutdown_smoke" / "partner_cutdown_manifest.json").exists()
            benchmarks_exists = (out_dir / "benchmark_privacy_smoke" / "benchmarks.json").exists()
            quality_exists = (out_dir / "data_quality_smoke" / "data_quality_report.json").exists()
            compliance_exists = (out_dir / "compliance_smoke" / "compliance_report.json").exists()
            retention_exists = (out_dir / "retention_smoke" / "retention_report.json").exists()
            audit_trail_exists = (out_dir / "audit_trail_smoke" / "audit_trail_report.json").exists()
            recovery_exists = (out_dir / "recovery_smoke" / "pack" / "recovery_pack.json").exists()
            visual_intelligence_exists = (out_dir / "visual_intelligence_smoke" / "visual_intelligence.json").exists()
            monitoring_exists = (out_dir / "monitoring_smoke" / "monitoring_plan.json").exists()

        gates = {gate["name"]: gate for gate in report["gates"]}
        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["production_verified"])
        self.assertEqual(gates["local_qa"]["status"], "skipped")
        self.assertEqual(gates["deployment_manifest_smoke"]["status"], "pass")
        self.assertEqual(gates["schema_verification_smoke"]["status"], "pass")
        self.assertEqual(gates["schema_verification_smoke"]["contract_status"], "pass")
        self.assertFalse(gates["schema_verification_smoke"]["production_verified"])
        self.assertEqual(gates["launch_dry_run"]["status"], "pass")
        self.assertEqual(gates["account_access_smoke"]["status"], "pass")
        self.assertEqual(gates["account_access_smoke"]["partner_scoped_memberships"], 1)
        self.assertEqual(gates["customer_access_verification_smoke"]["status"], "pass")
        self.assertEqual(gates["customer_access_verification_smoke"]["access_lens_proof_status"], "review_ready")
        self.assertEqual(gates["customer_access_verification_smoke"]["access_lens_summary"]["missing_lenses"], 0)
        self.assertGreaterEqual(gates["customer_access_verification_smoke"]["access_lens_summary"]["lens_count"], 3)
        self.assertEqual(gates["live_readiness_smoke"]["status"], "pass")
        self.assertEqual(gates["live_readiness_smoke"]["readiness_status"], "action_required")
        self.assertFalse(gates["live_readiness_smoke"]["ready_to_run_live_cutover"])
        self.assertFalse(gates["live_readiness_smoke"]["secrets_written"])
        self.assertEqual(gates["live_launch_request_smoke"]["status"], "pass")
        self.assertEqual(gates["live_launch_request_smoke"]["request_status"], "action_required")
        self.assertGreater(gates["live_launch_request_smoke"]["task_count"], 0)
        self.assertFalse(gates["live_launch_request_smoke"]["secrets_written"])
        self.assertEqual(gates["customer_package_smoke"]["status"], "pass")
        self.assertEqual(gates["customer_package_smoke"]["boardroom_report_status"], "pass")
        self.assertEqual(gates["customer_package_smoke"]["boardroom_report_mode"], "tenant_workspace")
        self.assertEqual(gates["customer_portal_smoke"]["status"], "pass")
        self.assertEqual(gates["customer_portal_smoke"]["live_runtime"], "pass")
        self.assertEqual(gates["customer_portal_smoke"]["live_runtime_status"], "ready_for_customer_auth_config")
        self.assertEqual(gates["portal_hosting_smoke"]["status"], "pass")
        self.assertEqual(gates["portal_hosting_smoke"]["stage_status"], "buyer_review_hosting_ready")
        self.assertFalse(gates["portal_hosting_smoke"]["production_gate"]["verified"])
        self.assertEqual(gates["portal_hosting_smoke"]["checks"]["secret_scan"], "pass")
        self.assertTrue(gates["portal_hosting_smoke"]["summary"]["static_snapshot_present"])
        self.assertEqual(gates["sales_integration_smoke"]["status"], "pass")
        self.assertEqual(gates["sales_integration_sync_smoke"]["status"], "pass")
        self.assertEqual(gates["sales_integration_sync_smoke"]["mode"], "dry_run")
        self.assertFalse(gates["sales_integration_sync_smoke"]["summary"]["live_api_calls_made"])
        self.assertEqual(gates["data_vendor_enrichment_smoke"]["status"], "pass")
        self.assertEqual(gates["data_vendor_refresh_smoke"]["status"], "pass")
        self.assertEqual(gates["data_vendor_refresh_smoke"]["mode"], "dry_run")
        self.assertFalse(gates["data_vendor_refresh_smoke"]["summary"]["live_api_calls_made"])
        self.assertEqual(gates["data_vendor_refresh_smoke"]["tenant_scope"], "pass")
        self.assertEqual(gates["enterprise_demo_room_smoke"]["status"], "pass")
        self.assertGreaterEqual(gates["enterprise_demo_room_smoke"]["properties"], 15)
        self.assertEqual(gates["boardroom_report_smoke"]["status"], "pass")
        self.assertEqual(gates["boardroom_report_smoke"]["mode"], "producer_network")
        self.assertEqual(gates["boardroom_report_smoke"]["summary"]["properties"], 120)
        self.assertEqual(gates["boardroom_report_smoke"]["summary"]["partners"], 10)
        self.assertEqual(gates["boardroom_report_smoke"]["partner_rows"], 10)
        self.assertEqual(gates["boardroom_report_smoke"]["intelligence_lab_status"], "pass")
        self.assertEqual(gates["boardroom_report_smoke"]["intelligence_lab_family_count"], 4)
        self.assertEqual(gates["boardroom_report_smoke"]["intelligence_lab_scope_leakage"], 0)
        self.assertEqual(gates["boardroom_report_smoke"]["intelligence_lab_forbidden_claims"], 0)
        self.assertEqual(gates["partner_cutdown_smoke"]["status"], "pass")
        self.assertEqual(gates["partner_cutdown_smoke"]["summary"]["partners"], 10)
        self.assertEqual(gates["partner_cutdown_smoke"]["summary"]["properties"], 120)
        self.assertEqual(gates["partner_cutdown_smoke"]["failed_partners"], 0)
        self.assertEqual(gates["customer_brief_smoke"]["status"], "pass")
        self.assertEqual(gates["campaign_learning_smoke"]["status"], "pass")
        self.assertEqual(gates["territory_plan_smoke"]["status"], "pass")
        self.assertEqual(gates["roi_forecast_smoke"]["status"], "pass")
        self.assertEqual(gates["opportunity_dossier_smoke"]["status"], "pass")
        self.assertEqual(gates["source_ledger_smoke"]["status"], "pass")
        self.assertEqual(gates["audit_trail_smoke"]["status"], "pass")
        self.assertEqual(gates["recovery_smoke"]["status"], "pass")
        self.assertEqual(gates["api_contract_smoke"]["status"], "pass")
        self.assertEqual(gates["processing_register_smoke"]["status"], "pass")
        self.assertEqual(gates["data_dictionary_smoke"]["status"], "pass")
        self.assertEqual(gates["data_quality_smoke"]["status"], "pass")
        self.assertEqual(gates["compliance_smoke"]["status"], "pass")
        self.assertEqual(gates["retention_smoke"]["status"], "pass")
        self.assertEqual(gates["benchmark_privacy_smoke"]["status"], "pass")
        self.assertEqual(gates["visual_intelligence_smoke"]["status"], "pass")
        self.assertEqual(gates["visual_intelligence_smoke"]["map_strategy"], "clustered_map")
        self.assertEqual(gates["visual_intelligence_smoke"]["graph_strategy"], "budgeted_graph")
        self.assertGreater(gates["visual_intelligence_smoke"]["cluster_count"], 0)
        self.assertEqual(gates["monitoring_smoke"]["status"], "pass")
        self.assertEqual(gates["monitoring_smoke"]["monitoring_status"], "buyer_review_monitoring_ready")
        self.assertFalse(gates["monitoring_smoke"]["production_gate"]["verified"])
        self.assertGreaterEqual(gates["monitoring_smoke"]["summary"]["watches"], 8)
        self.assertFalse(gates["benchmark_privacy_smoke"]["leaks"]["tenant_id"])
        self.assertFalse(gates["benchmark_privacy_smoke"]["leaks"]["property_id"])
        self.assertEqual(saved_report["paths"]["readiness_report"], str(out_dir / "readiness_report.json"))
        self.assertTrue(cleanup_sql_exists)
        self.assertTrue(deployment_exists)
        self.assertTrue(schema_verification_exists)
        self.assertTrue(account_access_exists)
        self.assertTrue(customer_access_verification_exists)
        self.assertTrue(access_lens_matrix_exists)
        self.assertTrue(live_readiness_exists)
        self.assertTrue(live_launch_request_exists)
        self.assertTrue(live_launch_checklist_exists)
        self.assertTrue(live_launch_env_template_exists)
        self.assertTrue(api_contract_exists)
        self.assertTrue(customer_brief_exists)
        self.assertTrue(campaign_learning_exists)
        self.assertTrue(territory_plan_exists)
        self.assertTrue(roi_forecast_exists)
        self.assertTrue(opportunity_dossier_exists)
        self.assertTrue(source_ledger_exists)
        self.assertTrue(processing_register_exists)
        self.assertTrue(dictionary_exists)
        self.assertTrue(package_manifest_exists)
        self.assertTrue(package_boardroom_report_exists)
        self.assertTrue(package_boardroom_html_exists)
        self.assertTrue(portal_manifest_exists)
        self.assertTrue(portal_live_config_exists)
        self.assertTrue(portal_live_loader_exists)
        self.assertTrue(portal_hosting_exists)
        self.assertTrue(integration_manifest_exists)
        self.assertTrue(integration_sync_exists)
        self.assertTrue(enrichment_plan_exists)
        self.assertTrue(enrichment_refresh_exists)
        self.assertTrue(demo_room_manifest_exists)
        self.assertTrue(boardroom_report_exists)
        self.assertTrue(boardroom_html_exists)
        self.assertTrue(boardroom_partner_summary_exists)
        self.assertTrue(partner_cutdown_manifest_exists)
        self.assertTrue(benchmarks_exists)
        self.assertTrue(quality_exists)
        self.assertTrue(compliance_exists)
        self.assertTrue(retention_exists)
        self.assertTrue(audit_trail_exists)
        self.assertTrue(recovery_exists)
        self.assertTrue(visual_intelligence_exists)
        self.assertTrue(monitoring_exists)

    def test_monitoring_pack_builds_alert_matrix_from_readiness_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = build_readiness_pack(root / "readiness", run_qa=False)
            pack = build_monitoring_pack(root / "monitoring", readiness=readiness, release_label="monitoring-test")
            plan = json.loads((root / "monitoring" / "monitoring_plan.json").read_text(encoding="utf-8"))
            alert_matrix = (root / "monitoring" / "alert_matrix.csv").read_text(encoding="utf-8")
            runbook = (root / "monitoring" / "MONITORING_RUNBOOK.md").read_text(encoding="utf-8")
            combined_output = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (root / "monitoring").iterdir() if path.is_file())

        watches = {watch["key"]: watch for watch in plan["watches"]}
        self.assertEqual(pack["status"], "buyer_review_monitoring_ready")
        self.assertEqual(plan["secret_scan"]["status"], "pass")
        self.assertFalse(plan["production_gate"]["verified"])
        self.assertIn("tenant_access_rls", plan["production_gate"]["blockers"])
        self.assertIn("crm_webhook_delivery", watches)
        self.assertEqual(watches["crm_webhook_delivery"]["source_status"], "pass")
        self.assertEqual(watches["crm_webhook_delivery"]["production_status"], "needs_live_customer_crm_run")
        self.assertIn("HomePilot Monitoring Runbook", runbook)
        self.assertIn("alert_condition", alert_matrix)
        self.assertIn("tenant_access_rls", alert_matrix)
        self.assertNotIn("service-role", combined_output.lower())

    def test_operational_healthcheck_warns_without_live_env_but_checks_local_contracts(self) -> None:
        report = build_healthcheck_report(env={}, live=False, require_live=False)
        checks = {check["name"]: check for check in report["checks"]}
        self.assertEqual(report["status"], "warn")
        self.assertEqual(checks["required_files"]["status"], "pass")
        self.assertEqual(checks["env_template"]["status"], "pass")
        self.assertEqual(checks["dashboard_sql"]["status"], "pass")
        self.assertEqual(checks["schema_sql"]["status"], "pass")
        self.assertEqual(checks["client_assets"]["status"], "pass")
        self.assertEqual(checks["environment"]["status"], "warn")

    def test_env_template_documents_required_live_launch_keys_without_real_secrets(self) -> None:
        report = check_env_template()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["secret_like"], [])
        self.assertTrue(report["has_launch_hint"])
        self.assertTrue(report["has_schema_hint"])
        self.assertTrue(report["has_live_readiness_hint"])

    def test_operational_healthcheck_requires_live_env_when_requested(self) -> None:
        report = build_healthcheck_report(env={}, live=False, require_live=True)
        checks = {check["name"]: check for check in report["checks"]}
        self.assertEqual(report["status"], "fail")
        self.assertEqual(checks["environment"]["status"], "fail")
        self.assertEqual(checks["live_supabase"]["status"], "fail")

    def test_release_audit_allows_buyer_review_but_blocks_production_without_live_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness = build_readiness_pack(Path(tmp) / "readiness", run_qa=False)
            for gate in readiness["gates"]:
                if gate["name"] == "local_qa":
                    gate["status"] = "pass"
            due = build_due_diligence_pack(
                Path(tmp) / "due",
                readiness_report_path=Path(readiness["paths"]["readiness_report"]),
                modules=["windowpilot"],
            )
            report = build_release_audit(readiness, due)

        self.assertEqual(report["status"], "buyer_review_ready")
        self.assertEqual(report["decisions"]["buyer_review"], "go")
        self.assertEqual(report["decisions"]["production"], "no_go")
        self.assertTrue(any("Missing live readiness report" in item for item in report["blockers"]["production"]))
        self.assertTrue(any("Missing live schema verification report" in item for item in report["blockers"]["production"]))
        self.assertTrue(any("Missing live launch report" in item for item in report["blockers"]["production"]))

    def test_production_proof_manifest_hashes_evidence_and_blocks_without_live_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = build_readiness_pack(root / "readiness", run_qa=False)
            for gate in readiness["gates"]:
                if gate["name"] == "local_qa":
                    gate["status"] = "pass"
            readiness_path = root / "readiness" / "readiness_report.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            due = build_due_diligence_pack(
                root / "due",
                readiness_report_path=readiness_path,
                modules=["windowpilot"],
            )
            proof = build_production_proof_pack(
                root / "proof",
                readiness_report_path=readiness_path,
                due_diligence_report_path=Path(due["paths"]["due_diligence_report"]),
                release_label="proof-test",
            )
            proof_path = Path(proof["paths"]["production_proof"])
            proof_markdown = Path(proof["paths"]["production_proof_markdown"]).read_text(encoding="utf-8")
            proof_json = json.loads(proof_path.read_text(encoding="utf-8"))
            artifact_map = {artifact["label"]: artifact for artifact in proof_json["artifacts"]}

        self.assertEqual(proof["status"], "buyer_review_ready")
        self.assertEqual(proof["decisions"]["buyer_review"], "go")
        self.assertEqual(proof["decisions"]["production"], "no_go")
        self.assertEqual(proof["artifact_integrity"]["status"], "pass")
        self.assertEqual(proof["redaction"]["status"], "pass")
        self.assertIn("live_readiness_report", proof["production_gate"]["missing_live_artifacts"])
        self.assertIn("schema_verification_report", proof["production_gate"]["missing_live_artifacts"])
        self.assertIn("launch_report", proof["production_gate"]["missing_live_artifacts"])
        self.assertIn("customer_access_report", proof["production_gate"]["missing_live_artifacts"])
        self.assertEqual(artifact_map["readiness_report"]["json_status"], "pass")
        self.assertEqual(len(artifact_map["readiness_report"]["sha256"]), 64)
        self.assertIn("Evidence Hashes", proof_markdown)

    def test_market_readiness_scorecard_translates_release_evidence_for_boardroom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = build_readiness_pack(root / "readiness", run_qa=False)
            for gate in readiness["gates"]:
                if gate["name"] == "local_qa":
                    gate["status"] = "pass"
            readiness_path = root / "readiness" / "readiness_report.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            due = build_due_diligence_pack(
                root / "due",
                readiness_report_path=readiness_path,
                modules=["windowpilot"],
            )
            live_readiness_path = Path(readiness["paths"]["live_readiness_smoke"]) / "live_readiness.json"
            live_launch_request_path = Path(readiness["paths"]["live_launch_request_smoke"]) / "live_launch_request.json"
            release = build_release_evidence_bundle(
                out_dir=root / "release",
                readiness_report_path=readiness_path,
                due_diligence_report_path=Path(due["paths"]["due_diligence_report"]),
                live_readiness_report_path=live_readiness_path,
                release_label="scorecard-test",
                stage="buyer_review",
                env={},
            )
            pack = build_market_readiness_pack(
                root / "market",
                readiness_report_path=readiness_path,
                due_diligence_report_path=Path(due["paths"]["due_diligence_report"]),
                artifact_index_path=Path(release["paths"]["artifact_index"]),
                production_proof_path=Path(release["paths"]["production_proof"]),
                live_readiness_report_path=live_readiness_path,
                live_launch_request_path=live_launch_request_path,
                release_label="scorecard-test",
            )
            scorecard = json.loads((root / "market" / "market_readiness_scorecard.json").read_text(encoding="utf-8"))
            markdown = (root / "market" / "MARKET_READINESS_SCORECARD.md").read_text(encoding="utf-8")
            html = (root / "market" / "market-readiness.html").read_text(encoding="utf-8")
            data_room = (root / "market" / "BOARDROOM_DATA_ROOM_INDEX.md").read_text(encoding="utf-8")
            actions = (root / "market" / "market_readiness_actions.csv").read_text(encoding="utf-8")
            stakeholder_views = (root / "market" / "STAKEHOLDER_VIEWS.md").read_text(encoding="utf-8")
            live_launch_control_room = json.loads((root / "market" / "live_launch_control_room.json").read_text(encoding="utf-8"))
            live_launch_control_markdown = (root / "market" / "LIVE_LAUNCH_CONTROL_ROOM.md").read_text(encoding="utf-8")
            live_launch_action_board = (root / "market" / "LIVE_LAUNCH_ACTION_BOARD.csv").read_text(encoding="utf-8")
            live_credential_handoff = json.loads((root / "market" / "live_credential_handoff.json").read_text(encoding="utf-8"))
            live_credential_markdown = (root / "market" / "LIVE_CREDENTIAL_HANDOFF.md").read_text(encoding="utf-8")
            live_credential_checklist = (root / "market" / "LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv").read_text(encoding="utf-8")
            live_secret_channel_contract = (root / "market" / "LIVE_SECRET_CHANNEL_CONTRACT.csv").read_text(encoding="utf-8")
            live_proof_plan = json.loads((root / "market" / "live_proof_execution_plan.json").read_text(encoding="utf-8"))
            live_proof_markdown = (root / "market" / "LIVE_PROOF_EXECUTION_PLAN.md").read_text(encoding="utf-8")
            live_proof_evidence_map = (root / "market" / "LIVE_PROOF_EVIDENCE_MAP.csv").read_text(encoding="utf-8")
            live_proof_commands = (root / "market" / "LIVE_PROOF_COMMANDS.sh").read_text(encoding="utf-8")
            live_proof_acceptance = json.loads((root / "market" / "live_proof_acceptance_matrix.json").read_text(encoding="utf-8"))
            live_proof_acceptance_markdown = (root / "market" / "LIVE_PROOF_ACCEPTANCE_MATRIX.md").read_text(encoding="utf-8")
            live_proof_acceptance_csv = (root / "market" / "LIVE_PROOF_ACCEPTANCE_MATRIX.csv").read_text(encoding="utf-8")
            live_proof_vault = json.loads((root / "market" / "live_proof_evidence_vault.json").read_text(encoding="utf-8"))
            live_proof_vault_markdown = (root / "market" / "LIVE_PROOF_EVIDENCE_VAULT.md").read_text(encoding="utf-8")
            live_proof_archive_index = (root / "market" / "LIVE_PROOF_ARCHIVE_INDEX.csv").read_text(encoding="utf-8")
            market_ready_audit = json.loads((root / "market" / "market_ready_audit.json").read_text(encoding="utf-8"))
            market_ready_audit_markdown = (root / "market" / "MARKET_READY_GAP_AUDIT.md").read_text(encoding="utf-8")
            market_ready_requirements = (root / "market" / "MARKET_READY_REQUIREMENTS.csv").read_text(encoding="utf-8")
            daw_walkthrough = json.loads((root / "market" / "daw_boardroom_demo_walkthrough.json").read_text(encoding="utf-8"))
            daw_walkthrough_markdown = (root / "market" / "DAW_BOARDROOM_DEMO_WALKTHROUGH.md").read_text(encoding="utf-8")
            daw_demo_checklist = (root / "market" / "DAW_DEMO_CHECKLIST.csv").read_text(encoding="utf-8")
            daw_control_room = json.loads((root / "market" / "daw_first_campaign_control_room.json").read_text(encoding="utf-8"))
            daw_control_room_markdown = (root / "market" / "DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md").read_text(encoding="utf-8")
            daw_action_board = (root / "market" / "DAW_FIRST_CAMPAIGN_ACTION_BOARD.csv").read_text(encoding="utf-8")
            acceptance_plan = json.loads((root / "market" / "customer_acceptance_plan.json").read_text(encoding="utf-8"))
            acceptance_markdown = (root / "market" / "CUSTOMER_ACCEPTANCE_PLAN.md").read_text(encoding="utf-8")
            acceptance_csv = (root / "market" / "ACCEPTANCE_CHECKLIST.csv").read_text(encoding="utf-8")
            rollout_plan = json.loads((root / "market" / "customer_rollout_plan.json").read_text(encoding="utf-8"))
            rollout_markdown = (root / "market" / "CUSTOMER_ROLLOUT_PLAN.md").read_text(encoding="utf-8")
            rollout_csv = (root / "market" / "ROLLOUT_WORKSTREAMS.csv").read_text(encoding="utf-8")
            first_campaign_intake = json.loads((root / "market" / "first_campaign_launch_intake.json").read_text(encoding="utf-8"))
            first_campaign_markdown = (root / "market" / "FIRST_CAMPAIGN_LAUNCH_INTAKE.md").read_text(encoding="utf-8")
            first_campaign_checklist = (root / "market" / "FIRST_CAMPAIGN_LAUNCH_CHECKLIST.csv").read_text(encoding="utf-8")
            customer_input_templates = json.loads((root / "market" / "customer_input_templates.json").read_text(encoding="utf-8"))
            customer_input_templates_markdown = (root / "market" / "CUSTOMER_INPUT_TEMPLATES.md").read_text(encoding="utf-8")
            partner_roster_template = (root / "market" / "PARTNER_ROSTER_TEMPLATE.csv").read_text(encoding="utf-8")
            territory_assignment_template = (root / "market" / "TERRITORY_ASSIGNMENT_TEMPLATE.csv").read_text(encoding="utf-8")
            property_source_template = (root / "market" / "PROPERTY_SOURCE_TEMPLATE.csv").read_text(encoding="utf-8")
            suppression_list_template = (root / "market" / "SUPPRESSION_LIST_TEMPLATE.csv").read_text(encoding="utf-8")
            message_approval_template = (root / "market" / "MESSAGE_APPROVAL_TEMPLATE.csv").read_text(encoding="utf-8")
            partner_capacity_template = (root / "market" / "PARTNER_CAPACITY_TEMPLATE.csv").read_text(encoding="utf-8")
            first_campaign_input_validation = json.loads((root / "market" / "first_campaign_input_validation.json").read_text(encoding="utf-8"))
            first_campaign_input_validation_markdown = (root / "market" / "FIRST_CAMPAIGN_INPUT_VALIDATION.md").read_text(encoding="utf-8")
            first_campaign_input_issues = (root / "market" / "FIRST_CAMPAIGN_INPUT_ISSUES.csv").read_text(encoding="utf-8")
            first_campaign_import_plan = json.loads((root / "market" / "first_campaign_import_plan.json").read_text(encoding="utf-8"))
            first_campaign_import_plan_markdown = (root / "market" / "FIRST_CAMPAIGN_IMPORT_PLAN.md").read_text(encoding="utf-8")
            first_campaign_staging_rows = (root / "market" / "FIRST_CAMPAIGN_STAGING_ROWS.csv").read_text(encoding="utf-8")
            first_wave_launch_gate = json.loads((root / "market" / "first_wave_launch_gate.json").read_text(encoding="utf-8"))
            first_wave_launch_gate_markdown = (root / "market" / "FIRST_WAVE_LAUNCH_GATE.md").read_text(encoding="utf-8")
            first_wave_launch_gate_checklist = (root / "market" / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv").read_text(encoding="utf-8")
            first_wave_database_handoff = json.loads((root / "market" / "first_wave_database_handoff.json").read_text(encoding="utf-8"))
            first_wave_database_handoff_markdown = (root / "market" / "FIRST_WAVE_DATABASE_HANDOFF.md").read_text(encoding="utf-8")
            first_wave_database_handoff_checklist = (root / "market" / "FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv").read_text(encoding="utf-8")
            first_wave_database_review_rows = (root / "market" / "FIRST_WAVE_DATABASE_REVIEW_ROWS.csv").read_text(encoding="utf-8")
            first_wave_database_review_sql = (root / "market" / "FIRST_WAVE_DATABASE_REVIEW.sql").read_text(encoding="utf-8")
            partner_auth_mapping = json.loads((root / "market" / "partner_auth_mapping.json").read_text(encoding="utf-8"))
            partner_auth_mapping_markdown = (root / "market" / "PARTNER_AUTH_MAPPING.md").read_text(encoding="utf-8")
            partner_auth_mapping_template = (root / "market" / "PARTNER_AUTH_MAPPING_TEMPLATE.csv").read_text(encoding="utf-8")
            partner_auth_mapping_rows = (root / "market" / "PARTNER_AUTH_MAPPING_ROWS.csv").read_text(encoding="utf-8")
            partner_auth_mapping_issues = (root / "market" / "PARTNER_AUTH_MAPPING_ISSUES.csv").read_text(encoding="utf-8")
            partner_membership_review_sql = (root / "market" / "PARTNER_MEMBERSHIP_REVIEW.sql").read_text(encoding="utf-8")
            partner_access_reconciliation = json.loads((root / "market" / "partner_access_reconciliation.json").read_text(encoding="utf-8"))
            partner_access_reconciliation_markdown = (root / "market" / "PARTNER_ACCESS_RECONCILIATION.md").read_text(encoding="utf-8")
            partner_access_reconciliation_matrix = (root / "market" / "PARTNER_ACCESS_RECONCILIATION_MATRIX.csv").read_text(encoding="utf-8")
            partner_access_reconciliation_issues = (root / "market" / "PARTNER_ACCESS_RECONCILIATION_ISSUES.csv").read_text(encoding="utf-8")
            example_inputs = json.loads((root / "market" / "example_completed_customer_inputs.json").read_text(encoding="utf-8"))
            example_markdown = (root / "market" / "EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md").read_text(encoding="utf-8")
            example_partner_roster = (root / "market" / "example_completed_customer_inputs" / "PARTNER_ROSTER_TEMPLATE.csv").read_text(encoding="utf-8")
            example_validation = json.loads((root / "market" / "example_completed_customer_inputs" / "first_campaign_input_validation.json").read_text(encoding="utf-8"))
            example_issues = (root / "market" / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_INPUT_ISSUES.csv").read_text(encoding="utf-8")
            example_import_plan = json.loads((root / "market" / "example_completed_customer_inputs" / "first_campaign_import_plan.json").read_text(encoding="utf-8"))
            example_import_plan_markdown = (root / "market" / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_IMPORT_PLAN.md").read_text(encoding="utf-8")
            example_staging_rows = (root / "market" / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_STAGING_ROWS.csv").read_text(encoding="utf-8")
            example_launch_gate = json.loads((root / "market" / "example_completed_customer_inputs" / "first_wave_launch_gate.json").read_text(encoding="utf-8"))
            example_launch_gate_markdown = (root / "market" / "example_completed_customer_inputs" / "FIRST_WAVE_LAUNCH_GATE.md").read_text(encoding="utf-8")
            example_launch_gate_checklist = (root / "market" / "example_completed_customer_inputs" / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv").read_text(encoding="utf-8")
            procurement_review = json.loads((root / "market" / "procurement_security_review.json").read_text(encoding="utf-8"))
            procurement_markdown = (root / "market" / "PROCUREMENT_SECURITY_REVIEW.md").read_text(encoding="utf-8")
            security_questionnaire = (root / "market" / "SECURITY_QUESTIONNAIRE.csv").read_text(encoding="utf-8")
            procurement_risks = (root / "market" / "PROCUREMENT_RISK_REGISTER.csv").read_text(encoding="utf-8")
            support_plan = json.loads((root / "market" / "support_sla_plan.json").read_text(encoding="utf-8"))
            support_markdown = (root / "market" / "SUPPORT_SLA_PLAN.md").read_text(encoding="utf-8")
            support_escalation = (root / "market" / "SUPPORT_ESCALATION_MATRIX.csv").read_text(encoding="utf-8")
            incident_playbook = (root / "market" / "INCIDENT_RESPONSE_PLAYBOOK.md").read_text(encoding="utf-8")
            pilot_proposal = json.loads((root / "market" / "customer_pilot_proposal.json").read_text(encoding="utf-8"))
            pilot_markdown = (root / "market" / "CUSTOMER_PILOT_PROPOSAL.md").read_text(encoding="utf-8")
            pilot_scope = (root / "market" / "PILOT_SCOPE_CHECKLIST.csv").read_text(encoding="utf-8")
            commercial_assumptions = (root / "market" / "COMMERCIAL_ASSUMPTIONS.csv").read_text(encoding="utf-8")
            training_plan = json.loads((root / "market" / "customer_training_plan.json").read_text(encoding="utf-8"))
            training_guide = (root / "market" / "CUSTOMER_TRAINING_GUIDE.md").read_text(encoding="utf-8")
            training_sessions = (root / "market" / "TRAINING_SESSION_PLAN.csv").read_text(encoding="utf-8")
            role_cheatsheet = (root / "market" / "ROLE_CHEATSHEET.csv").read_text(encoding="utf-8")
            value_plan = json.loads((root / "market" / "customer_value_realization_plan.json").read_text(encoding="utf-8"))
            value_markdown = (root / "market" / "CUSTOMER_VALUE_REALIZATION_PLAN.md").read_text(encoding="utf-8")
            value_metrics = (root / "market" / "VALUE_REALIZATION_METRICS.csv").read_text(encoding="utf-8")
            decision_log = (root / "market" / "EXECUTIVE_DECISION_LOG.csv").read_text(encoding="utf-8")
            outcome_contract = json.loads((root / "market" / "outcome_measurement_contract.json").read_text(encoding="utf-8"))
            outcome_markdown = (root / "market" / "OUTCOME_MEASUREMENT_CONTRACT.md").read_text(encoding="utf-8")
            outcome_schema = (root / "market" / "OUTCOME_EVENT_SCHEMA.csv").read_text(encoding="utf-8")
            outcome_template = (root / "market" / "OUTCOME_SYNC_TEMPLATE.csv").read_text(encoding="utf-8")
            outcome_checklist = (root / "market" / "OUTCOME_RECONCILIATION_CHECKLIST.csv").read_text(encoding="utf-8")
            outcome_import = json.loads((root / "market" / "outcome_import_validation.json").read_text(encoding="utf-8"))
            outcome_import_markdown = (root / "market" / "OUTCOME_IMPORT_VALIDATION.md").read_text(encoding="utf-8")
            outcome_import_issues = (root / "market" / "OUTCOME_IMPORT_ISSUES.csv").read_text(encoding="utf-8")
            outcome_import_rows = (root / "market" / "OUTCOME_IMPORT_REVIEW_ROWS.csv").read_text(encoding="utf-8")
            module_plan = json.loads((root / "market" / "customer_module_expansion_plan.json").read_text(encoding="utf-8"))
            module_markdown = (root / "market" / "CUSTOMER_MODULE_EXPANSION_PLAN.md").read_text(encoding="utf-8")
            module_matrix = (root / "market" / "MODULE_VALUE_MATRIX.csv").read_text(encoding="utf-8")
            expansion_tree = (root / "market" / "EXPANSION_DECISION_TREE.csv").read_text(encoding="utf-8")
            module_readiness = json.loads((root / "market" / "module_readiness_matrix.json").read_text(encoding="utf-8"))
            module_readiness_markdown = (root / "market" / "MODULE_READINESS_MATRIX.md").read_text(encoding="utf-8")
            module_readiness_csv = (root / "market" / "MODULE_READINESS_MATRIX.csv").read_text(encoding="utf-8")
            module_metric_coverage = (root / "market" / "MODULE_METRIC_COVERAGE.csv").read_text(encoding="utf-8")
            public_register = json.loads((root / "market" / "customer_public_data_source_register.json").read_text(encoding="utf-8"))
            public_markdown = (root / "market" / "PUBLIC_DATA_SOURCE_REGISTER.md").read_text(encoding="utf-8")
            public_matrix = (root / "market" / "PUBLIC_DATA_SOURCE_MATRIX.csv").read_text(encoding="utf-8")
            blocked_data = (root / "market" / "BLOCKED_DATA_REGISTER.csv").read_text(encoding="utf-8")
            attribution_requirements = (root / "market" / "ATTRIBUTION_REQUIREMENTS.csv").read_text(encoding="utf-8")
            public_intake = json.loads((root / "market" / "public_data_production_intake.json").read_text(encoding="utf-8"))
            public_intake_markdown = (root / "market" / "PUBLIC_DATA_PRODUCTION_INTAKE.md").read_text(encoding="utf-8")
            public_approval_checklist = (root / "market" / "PUBLIC_DATA_APPROVAL_CHECKLIST.csv").read_text(encoding="utf-8")
            public_data_reconciliation = json.loads((root / "market" / "public_data_reconciliation.json").read_text(encoding="utf-8"))
            public_data_reconciliation_markdown = (root / "market" / "PUBLIC_DATA_RECONCILIATION.md").read_text(encoding="utf-8")
            public_data_reconciliation_matrix = (root / "market" / "PUBLIC_DATA_RECONCILIATION_MATRIX.csv").read_text(encoding="utf-8")
            public_data_reconciliation_issues = (root / "market" / "PUBLIC_DATA_RECONCILIATION_ISSUES.csv").read_text(encoding="utf-8")
            customer_signoff_reconciliation = json.loads((root / "market" / "customer_signoff_reconciliation.json").read_text(encoding="utf-8"))
            customer_signoff_reconciliation_markdown = (root / "market" / "CUSTOMER_SIGNOFF_RECONCILIATION.md").read_text(encoding="utf-8")
            customer_signoff_reconciliation_matrix = (root / "market" / "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv").read_text(encoding="utf-8")
            customer_signoff_reconciliation_issues = (root / "market" / "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv").read_text(encoding="utf-8")
            customer_signoff_intake = (root / "market" / "CUSTOMER_SIGNOFF_INTAKE.md").read_text(encoding="utf-8")
            customer_signoff_template = (root / "market" / "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv").read_text(encoding="utf-8")
            customer_view_catalog = json.loads((root / "market" / "customer_view_catalog.json").read_text(encoding="utf-8"))
            customer_view_catalog_markdown = (root / "market" / "CUSTOMER_VIEW_CATALOG.md").read_text(encoding="utf-8")
            customer_view_matrix = (root / "market" / "CUSTOMER_VIEW_MATRIX.csv").read_text(encoding="utf-8")
            data_platform_blueprint = json.loads((root / "market" / "data_platform_blueprint.json").read_text(encoding="utf-8"))
            data_platform_blueprint_markdown = (root / "market" / "DATA_PLATFORM_BLUEPRINT.md").read_text(encoding="utf-8")
            data_platform_scope_matrix = (root / "market" / "DATA_PLATFORM_SCOPE_MATRIX.csv").read_text(encoding="utf-8")
            portable_html = (root / "market" / "portable_data_room" / "index.html").read_text(encoding="utf-8")
            portable_manifest = json.loads((root / "market" / "portable_data_room" / "DATA_ROOM_MANIFEST.json").read_text(encoding="utf-8"))
            with zipfile.ZipFile(root / "market" / "homepilot_boardroom_data_room.zip") as archive:
                portable_zip_names = archive.namelist()
                portable_zip_text = "\n".join(
                    archive.read(name).decode("utf-8", errors="ignore")
                    for name in portable_zip_names
                    if Path(name).suffix in {".csv", ".html", ".js", ".json", ".jsonl", ".md", ".sh", ".sql", ".txt"}
                )

        score_by_key = {row["key"]: row for row in scorecard["scorecard"]}
        self.assertEqual(pack["status"], "market_review_ready")
        self.assertEqual(scorecard["decisions"]["buyer_review"], "go")
        self.assertEqual(scorecard["decisions"]["production"], "no_go")
        self.assertEqual(scorecard["summary"]["readiness_gate_count"], 35)
        self.assertEqual(scorecard["summary"]["live_launch_task_count"], 10)
        self.assertFalse(scorecard["summary"]["secrets_written"])
        self.assertEqual(score_by_key["demo_value"]["status"], "pass")
        self.assertEqual(score_by_key["live_launch"]["status"], "blocked")
        self.assertEqual(score_by_key["production_rollout"]["status"], "blocked")
        self.assertIn("What This Does Not Prove", markdown)
        self.assertIn("Customer Decision Board", markdown)
        self.assertIn("Signed/approved", markdown)
        self.assertIn("Buyer-ready is not customer-approved", markdown)
        self.assertIn("Buyer-review evidence accepted", markdown)
        self.assertIn("Live Proof Cockpit", markdown)
        self.assertIn("Live Credential Handoff", markdown)
        self.assertIn("Live credential checklist", markdown)
        self.assertIn("Live proof acceptance matrix", markdown)
        self.assertIn("Live Proof Evidence Vault", markdown)
        self.assertIn("Live proof archive index", markdown)
        self.assertIn("customer_access_verified", markdown)
        self.assertIn("production_verified=false", markdown)
        self.assertIn("Readiness Matrix", html)
        self.assertIn("Customer Decision Board", html)
        self.assertIn("Signed/approved", html)
        self.assertIn("Buyer-ready is not customer-approved", html)
        self.assertIn("customer-access proof", html)
        self.assertIn("Customer Access Lenses", html)
        self.assertIn("Live Proof Cockpit", html)
        self.assertIn("Live Credential Handoff", html)
        self.assertIn("Secret channel contract", html)
        self.assertIn("Live proof acceptance matrix", html)
        self.assertIn("Live Proof Evidence Vault", html)
        self.assertIn("Evidence vault", html)
        self.assertIn("customer_access_verified", html)
        self.assertIn("production_verified=false", html)
        self.assertIn("Data Platform Blueprint", markdown)
        self.assertIn("Data platform blueprint", markdown)
        self.assertIn("tenant -> modules -> campaigns -> properties -> assessments -> interactions", markdown)
        self.assertIn("Module Readiness Matrix", markdown)
        self.assertIn("Module readiness matrix", markdown)
        self.assertIn("Outcome Measurement Contract", markdown)
        self.assertIn("Outcome Import Dry-Run", markdown)
        self.assertIn("appointments, quotes, won/lost projects", markdown)
        self.assertIn("Data Platform Blueprint", html)
        self.assertIn("One shared property spine", html)
        self.assertIn("Module Readiness Matrix", html)
        self.assertIn("Production-ready still requires tenant entitlement", html)
        self.assertIn("Outcome Measurement Contract", html)
        self.assertIn("Outcome Import Dry-Run", html)
        self.assertIn("Closed-loop measurement", html)
        self.assertIn("production_verified=false", html)
        self.assertIn("Partner renovator assigned-record view", html)
        self.assertIn("Buyer-ready property intelligence", html)
        self.assertIn("file://", html)
        self.assertIn("Production proof", data_room)
        self.assertIn("Production cutover report", data_room)
        self.assertIn("Production cutover runbook", data_room)
        self.assertIn("Intelligence Lab report", data_room)
        self.assertIn("Intelligence Lab JSON evidence", data_room)
        self.assertIn("Live launch control room", data_room)
        self.assertIn("Live launch action board", data_room)
        self.assertIn("Live credential handoff", data_room)
        self.assertIn("Live credential checklist", data_room)
        self.assertIn("Live secret channel contract", data_room)
        self.assertIn("Live proof execution plan", data_room)
        self.assertIn("Live proof evidence map", data_room)
        self.assertIn("Live proof command script", data_room)
        self.assertIn("Live proof acceptance matrix", data_room)
        self.assertIn("Live proof evidence vault", data_room)
        self.assertIn("Live proof archive index", data_room)
        self.assertIn("Market-ready gap audit", data_room)
        self.assertIn("Market-ready requirements CSV", data_room)
        self.assertIn("First wave database handoff", data_room)
        self.assertIn("First wave database review SQL", data_room)
        self.assertIn("Partner Auth mapping", data_room)
        self.assertIn("Partner membership review SQL", data_room)
        self.assertIn("Partner access reconciliation", data_room)
        self.assertIn("Public data reconciliation", data_room)
        self.assertIn("Customer signoff reconciliation", data_room)
        self.assertIn("Customer view catalog", data_room)
        self.assertIn("Customer view matrix", data_room)
        self.assertIn("Data platform blueprint", data_room)
        self.assertIn("Data platform scope matrix", data_room)
        self.assertIn("Module readiness matrix", data_room)
        self.assertIn("Module readiness CSV", data_room)
        self.assertIn("Module metric coverage", data_room)
        self.assertIn("Outcome measurement contract", data_room)
        self.assertIn("Outcome event schema", data_room)
        self.assertIn("Outcome sync template", data_room)
        self.assertIn("Outcome reconciliation checklist", data_room)
        self.assertIn("Outcome import dry-run validation", data_room)
        self.assertIn("Outcome import issues", data_room)
        self.assertIn("Outcome import review rows", data_room)
        self.assertIn("Access lens proof matrix", data_room)
        self.assertIn("Open Intelligence model card", data_room)
        self.assertIn("Open Intelligence boardroom brief", data_room)
        self.assertIn("Open Intelligence decision matrix", data_room)
        self.assertIn("Open Intelligence JSON evidence", data_room)
        self.assertIn("Marketing impact planner", data_room)
        self.assertIn("Open Intelligence measurement loop", data_room)
        self.assertIn("Open Intelligence production gate", data_room)
        self.assertIn("Open Intelligence production gates CSV", data_room)
        self.assertIn("Open Intelligence production runbook", data_room)
        self.assertIn("Configure Supabase URL", actions)
        self.assertIn("Boardroom", stakeholder_views)
        self.assertIn("INTELLIGENCE_LAB.md", stakeholder_views)
        self.assertIn("LIVE_LAUNCH_CONTROL_ROOM.md", stakeholder_views)
        self.assertEqual(live_launch_control_room["status"], "blocked_until_live_inputs")
        self.assertEqual(live_launch_control_room["summary"]["buyer_review_decision"], "go")
        self.assertEqual(live_launch_control_room["summary"]["live_launch_decision"], "no_go")
        self.assertEqual(live_launch_control_room["summary"]["production_decision"], "no_go")
        self.assertEqual(live_launch_control_room["summary"]["live_launch_task_count"], 10)
        self.assertFalse(live_launch_control_room["summary"]["first_wave_launch_authorized"])
        self.assertEqual(live_launch_control_room["summary"]["partner_auth_mapping_status"], "mapping_required")
        self.assertEqual(live_launch_control_room["summary"]["partner_auth_expected_count"], 10)
        self.assertEqual(live_launch_control_room["summary"]["partner_auth_mapped_count"], 0)
        self.assertEqual(live_launch_control_room["summary"]["partner_access_reconciliation_status"], "blocked_until_partner_auth_mapping")
        self.assertEqual(live_launch_control_room["summary"]["partner_access_reconciled_count"], 0)
        self.assertGreaterEqual(live_launch_control_room["summary"]["partner_access_reconciliation_blockers"], 1)
        self.assertEqual(live_launch_control_room["summary"]["public_data_reconciliation_status"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertEqual(live_launch_control_room["summary"]["public_data_approved_source_count"], 0)
        self.assertEqual(live_launch_control_room["summary"]["public_data_registered_source_count"], 7)
        self.assertGreaterEqual(live_launch_control_room["summary"]["public_data_reconciliation_blockers"], 1)
        self.assertFalse(live_launch_control_room["summary"]["public_data_first_wave_required"])
        self.assertEqual(live_launch_control_room["summary"]["customer_signoff_reconciliation_status"], "blocked_until_customer_signoff_and_live_proof")
        self.assertEqual(live_launch_control_room["summary"]["customer_signoff_signed_decision_count"], 0)
        self.assertEqual(live_launch_control_room["summary"]["customer_signoff_decision_count"], 10)
        self.assertGreaterEqual(live_launch_control_room["summary"]["customer_signoff_live_launch_blockers"], 1)
        self.assertGreaterEqual(live_launch_control_room["summary"]["customer_signoff_production_blockers"], 1)
        self.assertFalse(live_launch_control_room["summary"]["production_verified"])
        live_stage_gates = {gate["key"]: gate for gate in live_launch_control_room["stage_gates"]}
        self.assertEqual(live_stage_gates["partner_auth_mapping"]["status"], "blocked")
        self.assertTrue(live_stage_gates["partner_auth_mapping"]["blocks_production"])
        self.assertFalse(live_stage_gates["partner_auth_mapping"]["blocks_live_launch"])
        self.assertEqual(live_stage_gates["partner_access_reconciliation"]["status"], "blocked")
        self.assertTrue(live_stage_gates["partner_access_reconciliation"]["blocks_production"])
        self.assertFalse(live_stage_gates["partner_access_reconciliation"]["blocks_live_launch"])
        self.assertEqual(live_stage_gates["public_data_reconciliation"]["status"], "blocked")
        self.assertTrue(live_stage_gates["public_data_reconciliation"]["blocks_production"])
        self.assertFalse(live_stage_gates["public_data_reconciliation"]["blocks_live_launch"])
        self.assertEqual(live_stage_gates["customer_signoff_reconciliation"]["status"], "blocked")
        self.assertTrue(live_stage_gates["customer_signoff_reconciliation"]["blocks_production"])
        self.assertTrue(live_stage_gates["customer_signoff_reconciliation"]["blocks_live_launch"])
        self.assertTrue(live_launch_control_room["guardrails"]["non_mutating"])
        self.assertTrue(live_launch_control_room["guardrails"]["no_live_writes"])
        self.assertTrue(live_launch_control_room["guardrails"]["stores_env_var_names_only"])
        self.assertFalse(live_launch_control_room["guardrails"]["secret_values_written"])
        self.assertEqual(live_launch_control_room["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Live Launch Control Room", live_launch_control_markdown)
        self.assertIn("production_verified=true", live_launch_control_markdown)
        self.assertIn("HOMEPILOT_SUPABASE_URL", live_launch_action_board)
        self.assertIn("live_inputs", live_launch_action_board)
        self.assertIn("partner_access", live_launch_action_board)
        self.assertIn("partner_access_reconciliation", live_launch_action_board)
        self.assertIn("customer_signoff_reconciliation", live_launch_action_board)
        self.assertIn("first_wave_go_no_go_missing", live_launch_action_board)
        self.assertIn("supabase_user_id_missing", live_launch_action_board)
        self.assertIn("partner_auth_mapping_not_ready", live_launch_action_board)
        self.assertNotIn("@example.com", live_launch_action_board)
        self.assertEqual(live_credential_handoff["handoff_type"], "homepilot_live_credential_handoff")
        self.assertEqual(live_credential_handoff["status"], "handoff_required")
        self.assertEqual(live_credential_handoff["summary"]["task_count"], 10)
        self.assertEqual(live_credential_handoff["secret_scan"]["status"], "pass")
        self.assertTrue(live_credential_handoff["guardrails"]["env_var_names_only"])
        self.assertTrue(live_credential_handoff["guardrails"]["no_raw_contact_data"])
        self.assertIn("HomePilot Live Credential Handoff", live_credential_markdown)
        self.assertIn("production_verified=false", live_credential_markdown)
        self.assertIn("HOMEPILOT_SUPABASE_URL", live_credential_checklist)
        self.assertIn("HOMEPILOT_SUPABASE_SERVICE_KEY", live_secret_channel_contract)
        self.assertIn("portable data room", live_secret_channel_contract)
        self.assertNotIn("@example.com", live_credential_markdown + live_credential_checklist + live_secret_channel_contract)
        self.assertNotIn("service_role=", live_credential_markdown + live_credential_checklist + live_secret_channel_contract)
        self.assertEqual(live_proof_plan["status"], "blocked_until_live_inputs")
        self.assertEqual(live_proof_plan["secret_scan"]["status"], "pass")
        self.assertEqual(live_proof_plan["plan_validation"]["status"], "pass")
        self.assertEqual(live_proof_plan["summary"]["live_launch_task_count"], 10)
        self.assertFalse(live_proof_plan["summary"]["production_verified"])
        self.assertTrue(live_proof_plan["guardrails"]["non_mutating_plan"])
        self.assertTrue(live_proof_plan["guardrails"]["requires_explicit_shell_confirmation"])
        self.assertTrue(live_proof_plan["guardrails"]["plan_validation_required"])
        self.assertIn("HomePilot Live Proof Execution Plan", live_proof_markdown)
        self.assertIn("Plan Validation", live_proof_markdown)
        self.assertIn("stale_live_readiness_not_reused: pass", live_proof_markdown)
        self.assertIn("homepilot_production_cutover.py --live", live_proof_markdown)
        self.assertIn("schema_verification", live_proof_evidence_map)
        self.assertIn("customer_access_verification", live_proof_evidence_map)
        self.assertIn("HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof", live_proof_commands)
        self.assertIn("homepilot_market_readiness.py", live_proof_commands)
        self.assertNotIn("service_role=", live_proof_markdown + live_proof_evidence_map + live_proof_commands)
        acceptance_by_key = {row["key"]: row for row in live_proof_acceptance["criteria"]}
        self.assertEqual(live_proof_acceptance["status"], "acceptance_criteria_ready_live_evidence_blocked")
        self.assertEqual(live_proof_acceptance["secret_scan"]["status"], "pass")
        self.assertEqual(live_proof_acceptance["summary"]["criterion_count"], 12)
        self.assertFalse(live_proof_acceptance["summary"]["production_verified"])
        self.assertEqual(acceptance_by_key["live_proof_plan_self_validated"]["status"], "pass")
        self.assertEqual(acceptance_by_key["customer_access_verified"]["status"], "blocked")
        self.assertEqual(acceptance_by_key["production_proof_gate_verified"]["status"], "blocked")
        live_proof_cockpit = scorecard["live_proof_cockpit"]
        live_proof_cockpit_blocker_keys = {row["key"] for row in live_proof_cockpit["blockers"]}
        self.assertEqual(live_proof_cockpit["summary"]["criterion_count"], 12)
        self.assertFalse(live_proof_cockpit["summary"]["production_verified"])
        self.assertEqual(live_proof_cockpit["summary"]["production_verified_label"], "production_verified=false")
        self.assertIn("customer_access_verified", live_proof_cockpit_blocker_keys)
        self.assertIn("HomePilot Live Proof Acceptance Matrix", live_proof_acceptance_markdown)
        self.assertIn("Customer signoff cannot override failed schema, RLS, or customer-access proof", live_proof_acceptance_markdown)
        self.assertIn("customer_access_verified", live_proof_acceptance_csv)
        self.assertNotIn("service_role=", live_proof_acceptance_markdown + live_proof_acceptance_csv)
        vault_by_key = {row["key"]: row for row in live_proof_vault["evidence_rows"]}
        self.assertEqual(live_proof_vault["status"], "live_proof_blocked")
        self.assertEqual(live_proof_vault["secret_scan"]["status"], "pass")
        self.assertGreaterEqual(live_proof_vault["summary"]["required_count"], 14)
        self.assertFalse(live_proof_vault["summary"]["production_verified"])
        self.assertEqual(live_proof_vault["summary"]["production_verified_label"], "production_verified=false")
        self.assertEqual(vault_by_key["live_proof_execution_plan"]["current_status"], "pass")
        self.assertEqual(vault_by_key["live_proof_acceptance_matrix"]["current_status"], "pass")
        self.assertEqual(vault_by_key["customer_access_report"]["current_status"], "blocked")
        self.assertEqual(vault_by_key["production_proof_gate"]["current_status"], "blocked")
        self.assertTrue(live_proof_vault["guardrails"]["no_secret_values"])
        self.assertTrue(live_proof_vault["guardrails"]["no_raw_contact_data"])
        self.assertIn("HomePilot Live Proof Evidence Vault", live_proof_vault_markdown)
        self.assertIn("schema_verification_report", live_proof_archive_index)
        self.assertIn("customer_access_report", live_proof_archive_index)
        self.assertIn("production_proof_gate", live_proof_archive_index)
        self.assertNotIn("service_role=", live_proof_vault_markdown + live_proof_archive_index)
        requirement_by_key = {row["key"]: row for row in market_ready_audit["requirements"]}
        self.assertEqual(market_ready_audit["status"], "buyer_review_ready_production_blocked")
        self.assertEqual(market_ready_audit["summary"]["requirement_count"], 21)
        self.assertEqual(
            market_ready_audit["summary"]["buyer_review_passed"],
            market_ready_audit["summary"]["buyer_review_total"],
        )
        self.assertGreaterEqual(market_ready_audit["summary"]["production_required_blockers"], 3)
        self.assertTrue(market_ready_audit["guardrails"]["non_mutating"])
        self.assertTrue(market_ready_audit["guardrails"]["no_supabase_writes"])
        self.assertFalse(market_ready_audit["guardrails"]["secret_values_written"])
        self.assertEqual(market_ready_audit["secret_scan"]["status"], "pass")
        self.assertEqual(requirement_by_key["buyer_data_room"]["status"], "pass")
        self.assertEqual(requirement_by_key["data_platform_blueprint"]["status"], "pass")
        self.assertEqual(requirement_by_key["module_readiness_matrix"]["status"], "pass")
        self.assertEqual(requirement_by_key["outcome_measurement_contract"]["status"], "pass")
        self.assertEqual(requirement_by_key["outcome_import_validation"]["status"], "pass")
        self.assertEqual(requirement_by_key["live_proof_plan_validated"]["status"], "pass")
        self.assertEqual(requirement_by_key["live_proof_acceptance_matrix"]["status"], "pass")
        self.assertEqual(requirement_by_key["live_proof_evidence_vault"]["status"], "pass")
        self.assertEqual(requirement_by_key["live_credential_handoff"]["status"], "pass")
        self.assertEqual(requirement_by_key["live_inputs_ready"]["status"], "blocked")
        self.assertEqual(requirement_by_key["live_schema_rls_customer_access"]["status"], "blocked")
        self.assertEqual(requirement_by_key["first_wave_authorization"]["status"], "blocked")
        self.assertIn("HomePilot Market-Ready Gap Audit", market_ready_audit_markdown)
        self.assertIn("Buyer-review ready is not the same as production verified", market_ready_audit_markdown)
        self.assertIn("Live proof execution plan self-validation", market_ready_audit_markdown)
        self.assertIn("live_proof_plan_validated", market_ready_requirements)
        self.assertIn("Live proof customer/IT acceptance matrix", market_ready_audit_markdown)
        self.assertIn("Live proof evidence vault and archive index", market_ready_audit_markdown)
        self.assertIn("Live credential handoff and secret channel contract", market_ready_audit_markdown)
        self.assertIn("Closed-loop outcome measurement contract", market_ready_audit_markdown)
        self.assertIn("Outcome import dry-run validation", market_ready_audit_markdown)
        self.assertIn("Shared data platform blueprint", market_ready_audit_markdown)
        self.assertIn("Pilot module readiness matrix", market_ready_audit_markdown)
        self.assertIn("Pilot module readiness matrix", market_ready_audit_markdown)
        self.assertIn("live_proof_acceptance_matrix", market_ready_requirements)
        self.assertIn("live_proof_evidence_vault", market_ready_requirements)
        self.assertIn("live_credential_handoff", market_ready_requirements)
        self.assertIn("outcome_measurement_contract", market_ready_requirements)
        self.assertIn("outcome_import_validation", market_ready_requirements)
        self.assertIn("data_platform_blueprint", market_ready_requirements)
        self.assertIn("module_readiness_matrix", market_ready_requirements)
        self.assertIn("live_schema_rls_customer_access", market_ready_requirements)
        self.assertNotIn("@example.com", market_ready_audit_markdown)
        self.assertEqual(daw_walkthrough["status"], "buyer_demo_ready")
        self.assertEqual(daw_walkthrough["scenario"]["customer"], "DAW producer network")
        self.assertEqual(daw_walkthrough["scenario"]["module"], "facadepilot")
        self.assertEqual(len(daw_walkthrough["screen_sequence"]), 11)
        self.assertEqual(len(daw_walkthrough["stakeholder_questions"]), 7)
        self.assertIn("INTELLIGENCE_LAB.md", json.dumps(daw_walkthrough))
        self.assertIn("OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md", json.dumps(daw_walkthrough))
        self.assertIn("OPEN_INTELLIGENCE_DECISION_MATRIX.csv", json.dumps(daw_walkthrough))
        self.assertIn("Boardroom decisions cockpit", daw_walkthrough["screen_sequence"][4]["operator_action"])
        self.assertIn("five decision-ready questions", daw_walkthrough["screen_sequence"][4]["success_signal"])
        self.assertTrue(daw_walkthrough["guardrails"]["synthetic_demo_not_live_performance"])
        self.assertTrue(daw_walkthrough["guardrails"]["live_proof_required_before_launch"])
        self.assertIn("HomePilot DAW Boardroom Demo Walkthrough", daw_walkthrough_markdown)
        self.assertIn("Stakeholder Questions", daw_walkthrough_markdown)
        self.assertIn("Open Intelligence decisions", daw_walkthrough_markdown)
        self.assertIn("portable_data_room/index.html", daw_demo_checklist)
        self.assertIn("dashboard/index.html#intelligence", daw_demo_checklist)
        self.assertIn("Open Intelligence decisions", daw_demo_checklist)
        self.assertIn("Boardroom decisions cockpit", daw_demo_checklist)
        self.assertIn("OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md", daw_demo_checklist)
        self.assertIn("OPEN_INTELLIGENCE_DECISION_MATRIX.csv", daw_demo_checklist)
        self.assertIn("five decision-ready questions", daw_demo_checklist)
        self.assertIn("LIVE_LAUNCH_REQUEST.md", daw_demo_checklist)
        self.assertEqual(daw_control_room["status"], "buyer_review_control_ready")
        self.assertEqual(daw_control_room["scenario"]["customer"], "DAW producer network")
        self.assertEqual(daw_control_room["scenario"]["module"], "facadepilot")
        self.assertEqual(daw_control_room["scenario"]["expected_partner_renovators"], 10)
        self.assertEqual(daw_control_room["first_wave_decision"], "blocked_until_customer_inputs_and_live_proof")
        self.assertEqual(daw_control_room["summary"]["launch_lanes"], 6)
        self.assertEqual(daw_control_room["summary"]["partner_waves"], 5)
        self.assertEqual(daw_control_room["summary"]["action_items"], 7)
        self.assertTrue(daw_control_room["guardrails"]["live_proof_required_before_first_wave"])
        self.assertTrue(daw_control_room["guardrails"]["response_rate_denominator_must_be_contacted_records"])
        self.assertIn("HomePilot DAW First Campaign Control Room", daw_control_room_markdown)
        self.assertIn("Partner Wave Plan", daw_control_room_markdown)
        self.assertIn("live_proof", daw_action_board)
        self.assertIn("FIRST_CAMPAIGN_INPUT_VALIDATION.md", daw_action_board)
        self.assertEqual(acceptance_plan["status"], "buyer_review_ready")
        self.assertEqual(acceptance_plan["stage_statuses"]["buyer_review"], "pass")
        self.assertEqual(acceptance_plan["stage_statuses"]["live_launch"], "blocked")
        self.assertEqual(acceptance_plan["stage_statuses"]["production_rollout"], "blocked")
        self.assertIn("HomePilot Customer Acceptance Plan", acceptance_markdown)
        self.assertIn("production_verified=true", acceptance_markdown)
        self.assertIn("Public-data enrichment has a reviewable storage and provenance contract", acceptance_markdown)
        self.assertIn("source-run/geography/public-feature/property-enrichment", acceptance_markdown)
        self.assertIn("Boardroom value story", acceptance_csv)
        self.assertIn("Public-data enrichment", acceptance_csv)
        self.assertEqual(rollout_plan["status"], "buyer_review_ready")
        self.assertEqual(rollout_plan["stage_statuses"]["buyer_review"], "pass")
        self.assertEqual(rollout_plan["stage_statuses"]["live_launch"], "blocked")
        self.assertEqual(rollout_plan["stage_statuses"]["first_campaign"], "blocked")
        self.assertIn("HomePilot Customer Rollout Plan", rollout_markdown)
        self.assertIn("30/60/90-Day Success Plan", rollout_markdown)
        self.assertIn("IT and Supabase launch inputs", rollout_csv)
        self.assertEqual(first_campaign_intake["status"], "first_campaign_inputs_required")
        self.assertEqual(first_campaign_intake["launch_decision"], "blocked_until_customer_inputs_and_live_proof")
        self.assertEqual(first_campaign_intake["scenario"]["default_customer"], "DAW producer network")
        self.assertEqual(first_campaign_intake["scenario"]["initial_module"], "facadepilot")
        self.assertEqual(first_campaign_intake["scenario"]["expected_partner_renovators"], 10)
        self.assertEqual(len(first_campaign_intake["input_requirements"]), 10)
        self.assertEqual(len(first_campaign_intake["go_no_go_gates"]), 6)
        self.assertTrue(first_campaign_intake["guardrails"]["contact_basis_required_before_outreach"])
        self.assertTrue(first_campaign_intake["guardrails"]["partner_scope_required_before_partner_access"])
        self.assertIn("primary_contact_email_or_secret_channel_ref", first_campaign_intake["partner_roster_template_fields"])
        self.assertIn("HomePilot First Campaign Launch Intake", first_campaign_markdown)
        self.assertIn("Partner Roster Template Fields", first_campaign_markdown)
        self.assertIn("blocked_until_customer_inputs_and_live_proof", first_campaign_markdown)
        self.assertIn("Partner renovator roster", first_campaign_checklist)
        self.assertIn("Contact basis and suppression rules", first_campaign_checklist)
        self.assertIn("First-wave launch decision", first_campaign_checklist)
        self.assertEqual(customer_input_templates["status"], "ready_for_customer_input")
        self.assertEqual(customer_input_templates["launch_decision"], "blocked_until_customer_inputs_and_live_proof")
        self.assertEqual(customer_input_templates["summary"]["template_count"], 6)
        self.assertTrue(customer_input_templates["guardrails"]["no_secret_values_in_templates"])
        self.assertTrue(customer_input_templates["guardrails"]["no_raw_personal_contact_data_required"])
        self.assertIn("HomePilot Customer Input Templates", customer_input_templates_markdown)
        self.assertIn("PARTNER_ROSTER_TEMPLATE.csv", customer_input_templates_markdown)
        self.assertIn("SUPPRESSION_LIST_TEMPLATE.csv", customer_input_templates_markdown)
        self.assertIn("primary_contact_email_or_secret_channel_ref", partner_roster_template)
        self.assertIn("secret://daw/partner/renotec-antwerp/contact", partner_roster_template)
        self.assertIn("nearest_partner_then_capacity", territory_assignment_template)
        self.assertIn("daw_facadepilot_wave1_properties.csv", property_source_template)
        self.assertIn("hash_or_customer_property_id", suppression_list_template)
        self.assertIn("no homeowner intent", message_approval_template)
        self.assertIn("do not over-assign", partner_capacity_template)
        self.assertEqual(first_campaign_input_validation["status"], "action_required")
        self.assertEqual(first_campaign_input_validation["first_wave_decision"], "blocked_until_customer_input_fixes")
        self.assertTrue(first_campaign_input_validation["guardrails"]["templates_are_not_customer_approval"])
        self.assertIn("HomePilot First Campaign Input Validation", first_campaign_input_validation_markdown)
        self.assertIn("expected_partner_count_missing", first_campaign_input_issues)
        self.assertIn("message_not_approved", first_campaign_input_issues)
        self.assertIn("live_proof_missing", first_campaign_input_issues)
        self.assertEqual(first_campaign_import_plan["status"], "blocked_until_customer_input_fixes")
        self.assertEqual(first_campaign_import_plan["import_decision"], "do_not_import_customer_inputs_incomplete")
        self.assertTrue(first_campaign_import_plan["guardrails"]["non_mutating_plan"])
        self.assertTrue(first_campaign_import_plan["guardrails"]["no_database_writes"])
        self.assertIn("HomePilot First Campaign Import Plan", first_campaign_import_plan_markdown)
        self.assertIn("do_not_import_customer_inputs_incomplete", first_campaign_staging_rows)
        self.assertEqual(first_wave_launch_gate["status"], "blocked")
        self.assertEqual(first_wave_launch_gate["launch_decision"], "blocked_until_customer_inputs_and_staging_review")
        self.assertFalse(first_wave_launch_gate["launch_authorized"])
        self.assertTrue(first_wave_launch_gate["guardrails"]["non_mutating_gate"])
        self.assertIn("HomePilot First Wave Launch Gate", first_wave_launch_gate_markdown)
        self.assertIn("customer_inputs", first_wave_launch_gate_checklist)
        self.assertEqual(first_wave_database_handoff["status"], "blocked_until_first_wave_launch_authorized")
        self.assertEqual(first_wave_database_handoff["sql_mode"], "comment_only_blocked_gate")
        self.assertFalse(first_wave_database_handoff["launch_authorized"])
        self.assertEqual(first_wave_database_handoff["summary"]["executable_statement_count"], 0)
        self.assertTrue(first_wave_database_handoff["guardrails"]["non_mutating_pack"])
        self.assertTrue(first_wave_database_handoff["guardrails"]["no_executable_sql_when_blocked"])
        self.assertTrue(first_wave_database_handoff["guardrails"]["partner_memberships_deferred_without_auth_user_ids"])
        self.assertFalse(first_wave_database_handoff["guardrails"]["raw_contact_values_written"])
        self.assertFalse(first_wave_database_handoff["guardrails"]["secret_values_written"])
        self.assertIn("HomePilot First Wave Database Handoff", first_wave_database_handoff_markdown)
        self.assertIn("comment-only SQL", first_wave_database_handoff_markdown)
        self.assertIn("launch_authorized", first_wave_database_handoff_checklist)
        self.assertIn("blocked_until_launch_authorized", first_wave_database_review_rows)
        self.assertIn("No executable DML is generated", first_wave_database_review_sql)
        self.assertNotIn("insert into public.", first_wave_database_review_sql.lower())
        self.assertEqual(partner_auth_mapping["status"], "mapping_required")
        self.assertEqual(partner_auth_mapping["sql_mode"], "comment_only_mapping_required")
        self.assertEqual(partner_auth_mapping["summary"]["expected_partner_count"], 10)
        self.assertEqual(partner_auth_mapping["summary"]["mapped_partner_count"], 0)
        self.assertEqual(partner_auth_mapping["summary"]["executable_statement_count"], 0)
        self.assertFalse(partner_auth_mapping["summary"]["raw_contact_values_written"])
        self.assertFalse(partner_auth_mapping["summary"]["secret_values_written"])
        self.assertTrue(partner_auth_mapping["guardrails"]["live_rls_customer_access_required_before_partner_access"])
        self.assertTrue(partner_auth_mapping["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertIn("HomePilot Partner Auth Mapping", partner_auth_mapping_markdown)
        self.assertIn("Supabase Auth user", partner_auth_mapping_markdown)
        self.assertIn("supabase_user_id", partner_auth_mapping_template)
        self.assertIn("customer_to_confirm_09", partner_auth_mapping_template)
        self.assertIn("renotec-antwerp", partner_auth_mapping_rows)
        self.assertIn("supabase_user_id_missing", partner_auth_mapping_issues)
        self.assertIn("No executable membership SQL is generated", partner_membership_review_sql)
        self.assertNotIn("insert into public.homepilot_memberships", partner_membership_review_sql.lower())
        self.assertEqual(partner_access_reconciliation["status"], "blocked_until_partner_auth_mapping")
        self.assertFalse(partner_access_reconciliation["production_ready"])
        self.assertEqual(partner_access_reconciliation["summary"]["expected_partner_count"], 10)
        self.assertEqual(partner_access_reconciliation["summary"]["mapped_partner_count"], 0)
        self.assertEqual(partner_access_reconciliation["summary"]["fully_reconciled_partner_count"], 0)
        self.assertTrue(partner_access_reconciliation["guardrails"]["no_supabase_writes"])
        self.assertEqual(partner_access_reconciliation["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Partner Access Reconciliation", partner_access_reconciliation_markdown)
        self.assertIn("partner_auth_mapping_not_ready", partner_access_reconciliation_issues)
        self.assertIn("renotec-antwerp", partner_access_reconciliation_matrix)
        self.assertNotIn("@example.com", partner_access_reconciliation_markdown + partner_access_reconciliation_matrix)
        self.assertEqual(public_data_reconciliation["status"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertFalse(public_data_reconciliation["production_import_ready"])
        self.assertEqual(public_data_reconciliation["summary"]["registered_source_count"], 7)
        self.assertEqual(public_data_reconciliation["summary"]["approved_source_count"], 0)
        self.assertFalse(public_data_reconciliation["summary"]["first_wave_public_data_required"])
        self.assertEqual(public_data_reconciliation["summary"]["first_wave_public_data_gate_status"], "pass")
        self.assertTrue(public_data_reconciliation["guardrails"]["no_supabase_writes"])
        self.assertEqual(public_data_reconciliation["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Public Data Reconciliation", public_data_reconciliation_markdown)
        self.assertIn("BeSt Addresses", public_data_reconciliation_matrix)
        self.assertIn("OpenStreetMap", public_data_reconciliation_matrix)
        self.assertIn("public_data_import_not_approved", public_data_reconciliation_issues)
        self.assertNotIn("@example.com", public_data_reconciliation_markdown + public_data_reconciliation_matrix)
        self.assertEqual(customer_signoff_reconciliation["status"], "blocked_until_customer_signoff_and_live_proof")
        self.assertFalse(customer_signoff_reconciliation["live_launch_ready"])
        self.assertFalse(customer_signoff_reconciliation["production_signoff_ready"])
        self.assertEqual(customer_signoff_reconciliation["summary"]["decision_count"], 10)
        self.assertEqual(customer_signoff_reconciliation["summary"]["signed_decision_count"], 0)
        self.assertGreaterEqual(customer_signoff_reconciliation["summary"]["live_launch_blockers"], 1)
        self.assertGreaterEqual(customer_signoff_reconciliation["summary"]["production_blockers"], 1)
        self.assertTrue(customer_signoff_reconciliation["guardrails"]["no_supabase_writes"])
        self.assertTrue(customer_signoff_reconciliation["guardrails"]["buyer_review_material_is_not_customer_approval"])
        self.assertEqual(customer_signoff_reconciliation["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Customer Signoff Reconciliation", customer_signoff_reconciliation_markdown)
        self.assertIn("buyer_review_acceptance", customer_signoff_reconciliation_matrix)
        self.assertIn("commercial_pilot_terms", customer_signoff_reconciliation_matrix)
        self.assertIn("first_wave_go_no_go_missing", customer_signoff_reconciliation_issues)
        self.assertIn("live_proof_missing", customer_signoff_reconciliation_issues)
        self.assertIn("HomePilot Customer Signoff Intake", customer_signoff_intake)
        self.assertIn("CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv", customer_signoff_intake)
        self.assertIn("technical proof", customer_signoff_intake.lower())
        self.assertIn("requested_signoff_status", customer_signoff_template)
        self.assertIn("technical_proof_required", customer_signoff_template)
        self.assertNotIn("@example.com", customer_signoff_reconciliation_markdown + customer_signoff_reconciliation_matrix)
        view_by_key = {row["view_key"]: row for row in customer_view_catalog["views"]}
        self.assertEqual(customer_view_catalog["status"], "buyer_review_ready_live_access_blocked")
        self.assertFalse(customer_view_catalog["summary"]["live_access_ready"])
        self.assertTrue(customer_view_catalog["guardrails"]["tenant_id_required"])
        self.assertTrue(customer_view_catalog["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertTrue(customer_view_catalog["guardrails"]["catalog_is_not_runtime_authorization"])
        self.assertIn("assigned records only", view_by_key["partner_renovator"]["partner_scope"].lower())
        self.assertIn("HomePilot Customer View Catalog", customer_view_catalog_markdown)
        self.assertIn("module_only_customer", customer_view_matrix)
        self.assertIn("blocked_until_live_schema_rls_customer_access_proof", customer_view_matrix)
        self.assertNotIn("@example.com", customer_view_catalog_markdown + customer_view_matrix)
        self.assertEqual(data_platform_blueprint["status"], "buyer_review_ready_live_proof_required")
        self.assertEqual(data_platform_blueprint["secret_scan"]["status"], "pass")
        self.assertEqual(data_platform_blueprint["summary"]["module_count"], 7)
        self.assertFalse(data_platform_blueprint["summary"]["production_verified"])
        self.assertEqual(data_platform_blueprint["summary"]["production_verified_label"], "production_verified=false")
        self.assertTrue(data_platform_blueprint["guardrails"]["tenant_id_required"])
        self.assertTrue(data_platform_blueprint["guardrails"]["module_key_required_for_module_rows"])
        self.assertTrue(data_platform_blueprint["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertTrue(data_platform_blueprint["guardrails"]["no_cross_tenant_raw_learning"])
        self.assertIn("HomePilot Data Platform Blueprint", data_platform_blueprint_markdown)
        self.assertIn("FacadePilot", data_platform_blueprint_markdown)
        self.assertIn("DrivewayPilot", data_platform_blueprint_markdown)
        self.assertIn("homepilot_properties", data_platform_blueprint_markdown)
        self.assertIn("partner_renovator", data_platform_scope_matrix)
        self.assertIn("homepilot_property_public_enrichment", data_platform_scope_matrix)
        self.assertNotIn("@example.com", data_platform_blueprint_markdown + data_platform_scope_matrix)
        self.assertEqual(example_inputs["status"], "synthetic_example_ready")
        self.assertEqual(example_inputs["summary"]["partner_count"], 10)
        self.assertTrue(example_inputs["guardrails"]["synthetic_example_only"])
        self.assertTrue(example_inputs["guardrails"]["no_raw_personal_contact_data"])
        self.assertIn("HomePilot Example Completed Customer Inputs", example_markdown)
        self.assertIn("Input validation status: customer_inputs_ready", example_markdown)
        self.assertIn("secret://example/daw/partner/daw-partner-01/contact", example_partner_roster)
        self.assertNotIn("@", example_partner_roster)
        self.assertEqual(example_validation["status"], "customer_inputs_ready")
        self.assertEqual(example_validation["first_wave_decision"], "blocked_until_live_proof")
        self.assertEqual(example_validation["summary"]["partner_count"], 10)
        self.assertEqual(example_validation["summary"]["blockers"], 1)
        self.assertIn("live_proof_missing", example_issues)
        self.assertNotIn("expected_partner_count_missing", example_issues)
        self.assertNotIn("message_not_approved", example_issues)
        self.assertNotIn("raw_personal_contact_data", example_issues)
        self.assertEqual(example_import_plan["status"], "staging_plan_ready_import_blocked")
        self.assertEqual(example_import_plan["import_decision"], "blocked_until_live_proof")
        self.assertEqual(example_import_plan["summary"]["partner_scope_records"], 10)
        self.assertEqual(example_import_plan["summary"]["campaign_records"], 10)
        self.assertEqual(example_import_plan["summary"]["property_source_runs"], 1)
        self.assertFalse(example_import_plan["summary"]["raw_contact_values_written"])
        self.assertFalse(example_import_plan["summary"]["secret_values_written"])
        self.assertIn("homepilot_campaigns", example_import_plan["database_contract"]["planned_tables"])
        self.assertIn("homepilot_campaign_targets", example_import_plan["database_contract"]["deferred_until_property_file_parse"])
        self.assertIn("HomePilot First Campaign Import Plan", example_import_plan_markdown)
        self.assertIn("planned_review", example_staging_rows)
        self.assertIn("homepilot_campaigns", example_staging_rows)
        self.assertNotIn("secret://example", json.dumps(example_import_plan))
        self.assertEqual(example_launch_gate["status"], "blocked")
        self.assertEqual(example_launch_gate["launch_decision"], "blocked_until_live_proof_and_customer_go_no_go")
        self.assertEqual(example_launch_gate["summary"]["campaign_records"], 10)
        self.assertFalse(example_launch_gate["launch_authorized"])
        self.assertIn("HomePilot First Wave Launch Gate", example_launch_gate_markdown)
        self.assertIn("live_proof", example_launch_gate_checklist)
        self.assertEqual(procurement_review["status"], "buyer_review_ready")
        self.assertTrue(procurement_review["not_legal_advice"])
        self.assertEqual(procurement_review["summary"]["blocked"], 1)
        self.assertIn("HomePilot Procurement & Security Review", procurement_markdown)
        self.assertIn("production_verified=true", procurement_markdown)
        self.assertIn("Tenant isolation", security_questionnaire)
        self.assertIn("Live database and RLS proof missing", procurement_risks)
        self.assertEqual(support_plan["status"], "buyer_review_support_ready")
        self.assertTrue(support_plan["not_contractual_sla"])
        self.assertEqual(support_plan["summary"]["priority_tiers"], 4)
        self.assertIn("HomePilot Support & SLA Plan", support_markdown)
        self.assertIn("P1", support_escalation)
        self.assertIn("HomePilot Incident Response Playbook", incident_playbook)
        self.assertEqual(pilot_proposal["status"], "buyer_review_proposal_ready")
        self.assertTrue(pilot_proposal["not_contractual_offer"])
        self.assertEqual(pilot_proposal["recommended_pilot"]["initial_module"], "facadepilot")
        self.assertIn("HomePilot Customer Pilot Proposal", pilot_markdown)
        self.assertIn("not a signed contractual offer", pilot_markdown)
        self.assertIn("M2 live proof", pilot_scope)
        self.assertIn("Pilot pricing", commercial_assumptions)
        self.assertEqual(training_plan["status"], "buyer_review_training_ready")
        self.assertTrue(training_plan["guardrails"]["tenant_module_partner_scope_required"])
        self.assertIn("HomePilot Customer Training Guide", training_guide)
        self.assertIn("DAW producer/network manager session", training_sessions)
        self.assertIn("IT/security proof session", training_sessions)
        self.assertIn("Public-data provenance session", training_sessions)
        self.assertIn("homepilot_source_runs", training_guide)
        self.assertIn("Partner renovator", role_cheatsheet)
        self.assertIn("must_not_see", role_cheatsheet)
        self.assertEqual(value_plan["status"], "buyer_review_value_ready")
        self.assertTrue(value_plan["guardrails"]["response_rate_denominator_required"])
        self.assertIn("HomePilot Value Realization Plan", value_markdown)
        self.assertIn("Response rate pct", value_metrics)
        self.assertIn("Partner response variance", value_metrics)
        self.assertIn("Scale, repeat, or pause", decision_log)
        self.assertEqual(outcome_contract["status"], "buyer_review_ready_live_outcome_sync_blocked")
        self.assertEqual(outcome_contract["secret_scan"]["status"], "pass")
        self.assertFalse(outcome_contract["summary"]["production_verified"])
        self.assertIn("won_project", outcome_contract["summary"]["allowed_outcome_stages"])
        self.assertTrue(outcome_contract["guardrails"]["no_crm_writes"])
        self.assertTrue(outcome_contract["guardrails"]["no_supabase_writes"])
        self.assertIn("HomePilot Outcome Measurement Contract", outcome_markdown)
        self.assertIn("Win rate", outcome_markdown)
        self.assertIn("outcome_stage", outcome_schema)
        self.assertIn("crm://redacted", outcome_template)
        self.assertIn("live_access_proven", outcome_checklist)
        self.assertNotIn("@example.com", outcome_markdown + outcome_schema + outcome_template + outcome_checklist)
        self.assertEqual(outcome_import["status"], "ready_for_customer_review_live_sync_blocked")
        self.assertEqual(outcome_import["sync_decision"], "blocked_until_live_proof")
        self.assertEqual(outcome_import["secret_scan"]["status"], "pass")
        self.assertEqual(outcome_import["summary"]["row_count"], 2)
        self.assertEqual(outcome_import["summary"]["blocker_count"], 0)
        self.assertTrue(outcome_import["guardrails"]["no_supabase_writes"])
        self.assertTrue(outcome_import["guardrails"]["no_crm_writes"])
        self.assertIn("HomePilot Outcome Import Dry-Run Validation", outcome_import_markdown)
        self.assertIn("review_ready_with_warnings", outcome_import_rows)
        self.assertIn("placeholder_reference", outcome_import_issues)
        self.assertNotIn("@example.com", json.dumps(outcome_import).lower() + outcome_import_markdown.lower() + outcome_import_issues.lower() + outcome_import_rows.lower())
        self.assertEqual(module_plan["status"], "buyer_review_expansion_ready")
        self.assertEqual(len(module_plan["modules"]), 7)
        self.assertTrue(module_plan["guardrails"]["tenant_module_scope_required"])
        self.assertIn("HomePilot Module Expansion Plan", module_markdown)
        self.assertIn("WindowPilot", module_matrix)
        self.assertIn("roofpilot", module_matrix)
        self.assertIn("module_activation", expansion_tree)
        module_readiness_by_key = {row["module_key"]: row for row in module_readiness["modules"]}
        self.assertEqual(module_readiness["status"], "buyer_review_ready_live_proof_required")
        self.assertEqual(module_readiness["secret_scan"]["status"], "pass")
        self.assertEqual(module_readiness["summary"]["module_count"], 7)
        self.assertEqual(module_readiness["summary"]["enabled_module_count"], 1)
        self.assertEqual(module_readiness["summary"]["buyer_ready_count"], 7)
        self.assertEqual(module_readiness["summary"]["production_ready_count"], 0)
        self.assertEqual(module_readiness["summary"]["production_verified_label"], "production_verified=false")
        self.assertTrue(module_readiness["guardrails"]["tenant_id_required"])
        self.assertTrue(module_readiness["guardrails"]["module_key_required"])
        self.assertTrue(module_readiness["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertTrue(module_readiness_by_key["windowpilot"]["enabled_in_current_customer_scope"])
        self.assertFalse(module_readiness_by_key["facadepilot"]["enabled_in_current_customer_scope"])
        self.assertIn("HomePilot Module Readiness Matrix", module_readiness_markdown)
        self.assertIn("WindowPilot", module_readiness_markdown)
        self.assertIn("DrivewayPilot", module_readiness_markdown)
        self.assertIn("windowpilot", module_readiness_csv)
        self.assertIn("facade_opportunity_score", module_metric_coverage)
        self.assertNotIn("@example.com", module_readiness_markdown + module_readiness_csv + module_metric_coverage)
        self.assertNotIn("service_role=", module_readiness_markdown + module_readiness_csv + module_metric_coverage)
        self.assertEqual(public_register["status"], "buyer_review_public_data_ready")
        self.assertEqual(len(public_register["sources"]), 7)
        self.assertTrue(public_register["guardrails"]["dataset_level_licence_required"])
        self.assertTrue(public_register["guardrails"]["owner_data_blocked_by_default"])
        self.assertTrue(public_register["guardrails"]["public_enrichment_separate_from_campaign_basis"])
        self.assertEqual(public_register["implementation_contract"]["customer_read_model"], "homepilot_property_public_enrichment")
        contract_tables = {row["table"] for row in public_register["implementation_contract"]["storage_tables"]}
        self.assertIn("homepilot_source_runs", contract_tables)
        self.assertIn("homepilot_property_enrichments", contract_tables)
        self.assertIn("HomePilot Public Data Source Register", public_markdown)
        self.assertIn("Implementation Contract", public_markdown)
        self.assertIn("homepilot_property_public_enrichment", public_markdown)
        self.assertIn("BeSt Addresses", public_matrix)
        self.assertIn("OpenStreetMap", public_matrix)
        self.assertIn("Individual EPC labels by address", blocked_data)
        self.assertIn("Personal contact details from scraping", blocked_data)
        self.assertIn("source_run_metadata", attribution_requirements)
        self.assertEqual(public_intake["status"], "approval_required")
        self.assertEqual(public_intake["production_import_decision"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertEqual(len(public_intake["dataset_approvals"]), 7)
        self.assertEqual(len(public_intake["gate_checklist"]), 7)
        self.assertTrue(public_intake["guardrails"]["production_imports_blocked_until_approved"])
        self.assertTrue(public_intake["guardrails"]["public_context_is_not_homeowner_intent"])
        intake_by_source = {row["source"]: row for row in public_intake["dataset_approvals"]}
        self.assertEqual(intake_by_source["Cadastral parcels monthly situation"]["approval_status"], "legal_review_required")
        self.assertIn("Cadastral owner data", intake_by_source["Cadastral parcels monthly situation"]["blocked_fields"])
        self.assertIn("HomePilot Public Data Production Intake", public_intake_markdown)
        self.assertEqual(public_data_reconciliation["status"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertFalse(public_data_reconciliation["production_import_ready"])
        self.assertEqual(public_data_reconciliation["summary"]["registered_source_count"], 7)
        self.assertEqual(public_data_reconciliation["summary"]["approved_source_count"], 0)
        self.assertFalse(public_data_reconciliation["summary"]["first_wave_public_data_required"])
        self.assertEqual(public_data_reconciliation["summary"]["first_wave_public_data_gate_status"], "pass")
        self.assertTrue(public_data_reconciliation["guardrails"]["public_data_separate_from_contact_basis"])
        self.assertEqual(public_data_reconciliation["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Public Data Reconciliation", public_data_reconciliation_markdown)
        self.assertIn("BeSt Addresses", public_data_reconciliation_matrix)
        self.assertIn("OpenStreetMap", public_data_reconciliation_matrix)
        self.assertIn("public_data_import_not_approved", public_data_reconciliation_issues)
        self.assertEqual(customer_signoff_reconciliation["status"], "blocked_until_customer_signoff_and_live_proof")
        self.assertFalse(customer_signoff_reconciliation["live_launch_ready"])
        self.assertFalse(customer_signoff_reconciliation["production_signoff_ready"])
        self.assertEqual(customer_signoff_reconciliation["summary"]["decision_count"], 10)
        self.assertEqual(customer_signoff_reconciliation["summary"]["signed_decision_count"], 0)
        self.assertEqual(customer_signoff_reconciliation["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Customer Signoff Reconciliation", customer_signoff_reconciliation_markdown)
        self.assertIn("buyer_review_acceptance", customer_signoff_reconciliation_matrix)
        self.assertIn("first_wave_go_no_go_missing", customer_signoff_reconciliation_issues)
        self.assertIn("HomePilot Customer Signoff Intake", customer_signoff_intake)
        self.assertIn("buyer_review_acceptance", customer_signoff_template)
        self.assertIn("Production import decision: blocked_until_dataset_approvals_and_live_proof", public_intake_markdown)
        self.assertIn("BeSt Addresses", public_approval_checklist)
        self.assertIn("dataset_level_approval_required", public_approval_checklist)
        self.assertIn("do_not_import_yet", public_approval_checklist)
        self.assertEqual(pack["portable_data_room"]["status"], "pass")
        self.assertIn("relative links", portable_html)
        self.assertNotIn("file://", portable_html)
        self.assertFalse(portable_manifest["absolute_links_written"])
        self.assertFalse(portable_manifest["source_paths_written"])
        self.assertGreater(portable_manifest["local_path_redaction_count"], 0)
        self.assertGreaterEqual(portable_manifest["copied_file_count"], 45)
        self.assertTrue(all(entry["relative_path"] and entry["sha256"] for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof execution plan" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof evidence map" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome measurement contract" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome event schema" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome sync template" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome reconciliation checklist" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome import dry-run validation" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome import issues" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome import review rows" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof command script" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Data platform blueprint" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Data platform scope matrix" for entry in portable_manifest["entries"]))
        self.assertIn("index.html", portable_zip_names)
        self.assertIn("DATA_ROOM_MANIFEST.json", portable_zip_names)
        self.assertTrue(any(name.startswith("files/") for name in portable_zip_names))
        self.assertTrue(any("customer-acceptance-plan" in name for name in portable_zip_names))
        self.assertTrue(any("acceptance-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("customer-rollout-plan" in name for name in portable_zip_names))
        self.assertTrue(any("rollout-workstreams" in name for name in portable_zip_names))
        self.assertTrue(any("daw-boardroom-demo-walkthrough" in name for name in portable_zip_names))
        self.assertTrue(any("intelligence-lab-report" in name for name in portable_zip_names))
        self.assertTrue(any("intelligence-lab-json-evidence" in name for name in portable_zip_names))
        self.assertTrue(any("live-launch-control-room" in name for name in portable_zip_names))
        self.assertTrue(any("live-launch-action-board" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-execution-plan" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-evidence-map" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-command-script" in name for name in portable_zip_names))
        self.assertTrue(any("market-ready-gap-audit" in name for name in portable_zip_names))
        self.assertTrue(any("market-ready-requirements-csv" in name for name in portable_zip_names))
        self.assertTrue(any("production-cutover-report" in name for name in portable_zip_names))
        self.assertTrue(any("production-cutover-runbook" in name for name in portable_zip_names))
        self.assertTrue(any("daw-demo-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("daw-first-campaign-control-room" in name for name in portable_zip_names))
        self.assertTrue(any("daw-first-campaign-action-board" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-launch-intake" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-launch-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("customer-input-templates" in name for name in portable_zip_names))
        self.assertTrue(any("partner-roster-template" in name for name in portable_zip_names))
        self.assertTrue(any("territory-assignment-template" in name for name in portable_zip_names))
        self.assertTrue(any("property-source-template" in name for name in portable_zip_names))
        self.assertTrue(any("suppression-list-template" in name for name in portable_zip_names))
        self.assertTrue(any("message-approval-template" in name for name in portable_zip_names))
        self.assertTrue(any("partner-capacity-template" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-input-validation" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-input-issues" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-import-plan" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-staging-rows" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-launch-gate" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-launch-gate-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-handoff" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-handoff-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-review-rows" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-review-sql" in name for name in portable_zip_names))
        self.assertTrue(any("partner-auth-mapping" in name for name in portable_zip_names))
        self.assertTrue(any("partner-auth-mapping-template" in name for name in portable_zip_names))
        self.assertTrue(any("partner-auth-mapping-issues" in name for name in portable_zip_names))
        self.assertTrue(any("partner-membership-review-sql" in name for name in portable_zip_names))
        self.assertTrue(any("partner-access-reconciliation" in name for name in portable_zip_names))
        self.assertTrue(any("partner-access-reconciliation-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("partner-access-reconciliation-issues" in name for name in portable_zip_names))
        self.assertTrue(any("example-completed-customer-inputs" in name for name in portable_zip_names))
        self.assertTrue(any("example-partner-roster" in name for name in portable_zip_names))
        self.assertTrue(any("example-territory-assignment" in name for name in portable_zip_names))
        self.assertTrue(any("example-property-source" in name for name in portable_zip_names))
        self.assertTrue(any("example-suppression-list" in name for name in portable_zip_names))
        self.assertTrue(any("example-message-approval" in name for name in portable_zip_names))
        self.assertTrue(any("example-partner-capacity" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-input-validation" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-input-issues" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-import-plan" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-staging-rows" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-wave-launch-gate" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-wave-launch-gate-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("procurement-security-review" in name for name in portable_zip_names))
        self.assertTrue(any("security-questionnaire" in name for name in portable_zip_names))
        self.assertTrue(any("procurement-risk-register" in name for name in portable_zip_names))
        self.assertTrue(any("support-sla-plan" in name for name in portable_zip_names))
        self.assertTrue(any("support-escalation-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("incident-response-playbook" in name for name in portable_zip_names))
        self.assertTrue(any("customer-pilot-proposal" in name for name in portable_zip_names))
        self.assertTrue(any("pilot-scope-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("commercial-assumptions" in name for name in portable_zip_names))
        self.assertTrue(any("customer-training-guide" in name for name in portable_zip_names))
        self.assertTrue(any("training-session-plan" in name for name in portable_zip_names))
        self.assertTrue(any("role-cheatsheet" in name for name in portable_zip_names))
        self.assertTrue(any("value-realization-plan" in name for name in portable_zip_names))
        self.assertTrue(any("value-realization-metrics" in name for name in portable_zip_names))
        self.assertTrue(any("executive-decision-log" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-measurement-contract" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-event-schema" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-sync-template" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-reconciliation-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("module-expansion-plan" in name for name in portable_zip_names))
        self.assertTrue(any("module-value-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("expansion-decision-tree" in name for name in portable_zip_names))
        self.assertTrue(any("data-platform-blueprint" in name for name in portable_zip_names))
        self.assertTrue(any("data-platform-scope-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-evidence-vault" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-archive-index" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-source-register" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-source-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("blocked-data-register" in name for name in portable_zip_names))
        self.assertTrue(any("attribution-requirements" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-production-intake" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-approval-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-reconciliation" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-reconciliation-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-reconciliation-issues" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-reconciliation" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-reconciliation-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-reconciliation-issues" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-intake" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-evidence-template" in name for name in portable_zip_names))
        self.assertIn("HomePilot Intelligence Lab", portable_zip_text)
        self.assertIn("HomePilot Live Launch Control Room", portable_zip_text)
        self.assertIn("HomePilot Live Proof Execution Plan", portable_zip_text)
        self.assertIn("HomePilot Live Proof Evidence Vault", portable_zip_text)
        self.assertIn("HOMEPILOT_LIVE_PROOF_CONFIRM", portable_zip_text)
        self.assertIn("HomePilot Market-Ready Gap Audit", portable_zip_text)
        self.assertIn("HomePilot Outcome Import Dry-Run Validation", portable_zip_text)
        self.assertIn("HomePilot Partner Access Reconciliation", portable_zip_text)
        self.assertIn("HomePilot Public Data Reconciliation", portable_zip_text)
        self.assertIn("HomePilot Customer Signoff Reconciliation", portable_zip_text)
        self.assertIn("HomePilot Customer Signoff Intake", portable_zip_text)
        self.assertIn("HomePilot Data Platform Blueprint", portable_zip_text)
        self.assertIn("tenant -> modules -> campaigns -> properties -> assessments -> interactions", portable_zip_text)
        self.assertIn("HomePilot Production Cutover", portable_zip_text)
        self.assertIn("Production verified: false", portable_zip_text)
        self.assertIn("HomePilot First Wave Database Handoff", portable_zip_text)
        self.assertIn("HomePilot Partner Auth Mapping", portable_zip_text)
        self.assertIn("No executable DML is generated", portable_zip_text)
        self.assertIn("No executable membership SQL is generated", portable_zip_text)
        self.assertIn("buyer_review_ready_production_blocked", portable_zip_text)
        self.assertIn("live_schema_rls_customer_access", portable_zip_text)
        self.assertIn("production_verified=true", portable_zip_text)
        self.assertIn("contacted_count", portable_zip_text)
        self.assertIn("forbidden_claim_count", portable_zip_text)
        self.assertNotIn("/private/tmp", portable_zip_text)
        self.assertNotIn("file:///private/tmp", portable_zip_text)

    def test_release_evidence_bundle_indexes_buyer_ready_handoff_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = build_readiness_pack(root / "readiness", run_qa=False)
            for gate in readiness["gates"]:
                if gate["name"] == "local_qa":
                    gate["status"] = "pass"
            readiness_path = root / "readiness" / "readiness_report.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            due = build_due_diligence_pack(
                root / "due",
                readiness_report_path=readiness_path,
                modules=["windowpilot"],
            )
            live_readiness_path = Path(readiness["paths"]["live_readiness_smoke"]) / "live_readiness.json"
            bundle = build_release_evidence_bundle(
                out_dir=root / "release",
                readiness_report_path=readiness_path,
                due_diligence_report_path=Path(due["paths"]["due_diligence_report"]),
                live_readiness_report_path=live_readiness_path,
                release_label="test-buyer-review",
                stage="buyer_review",
                env={},
            )
            index = json.loads((root / "release" / "artifact_index.json").read_text(encoding="utf-8"))
            notes = (root / "release" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
            checklist = (root / "release" / "HANDOFF_CHECKLIST.md").read_text(encoding="utf-8")
            release_audit_exists = Path(bundle["paths"]["release_audit"]).exists()
            preflight_exists = Path(bundle["paths"]["preflight_report"]).exists()
            ops_status_exists = Path(bundle["paths"]["ops_status"]).exists()
            status_page_exists = Path(bundle["paths"]["status_page"]).exists()
            production_proof = json.loads(Path(bundle["paths"]["production_proof"]).read_text(encoding="utf-8"))
            production_proof_exists = Path(bundle["paths"]["production_proof"]).exists()
            production_proof_markdown_exists = Path(bundle["paths"]["production_proof_markdown"]).exists()
            production_cutover = json.loads(Path(bundle["paths"]["production_cutover_report"]).read_text(encoding="utf-8"))
            production_cutover_exists = Path(bundle["paths"]["production_cutover_report"]).exists()
            production_cutover_runbook_exists = Path(bundle["paths"]["production_cutover_runbook"]).exists()
            production_cutover_runbook = Path(bundle["paths"]["production_cutover_runbook"]).read_text(encoding="utf-8")
            deployment_manifest_exists = Path(bundle["paths"]["deployment_manifest"]).exists()
            sql_apply_plan_exists = Path(bundle["paths"]["sql_apply_plan"]).exists()
            sql_apply_runbook_exists = Path(bundle["paths"]["sql_apply_runbook"]).exists()
            apply_sql_exists = Path(bundle["paths"]["apply_sql"]).exists()
            post_apply_verification_exists = Path(bundle["paths"]["post_apply_verification_sql"]).exists()
            market_readiness_exists = Path(bundle["paths"]["market_readiness_scorecard"]).exists()
            market_readiness_markdown_exists = Path(bundle["paths"]["market_readiness_markdown"]).exists()
            market_readiness_html_exists = Path(bundle["paths"]["market_readiness_html"]).exists()
            data_room_index_exists = Path(bundle["paths"]["boardroom_data_room_index"]).exists()
            market_actions_exists = Path(bundle["paths"]["market_readiness_actions"]).exists()
            stakeholder_views_exists = Path(bundle["paths"]["stakeholder_views"]).exists()
            live_launch_control_room_exists = Path(bundle["paths"]["live_launch_control_room"]).exists()
            live_launch_control_room_markdown_exists = Path(bundle["paths"]["live_launch_control_room_markdown"]).exists()
            live_launch_action_board_exists = Path(bundle["paths"]["live_launch_action_board"]).exists()
            live_credential_handoff_exists = Path(bundle["paths"]["live_credential_handoff"]).exists()
            live_credential_handoff_markdown_exists = Path(bundle["paths"]["live_credential_handoff_markdown"]).exists()
            live_credential_handoff_checklist_exists = Path(bundle["paths"]["live_credential_handoff_checklist"]).exists()
            live_secret_channel_contract_exists = Path(bundle["paths"]["live_secret_channel_contract"]).exists()
            live_proof_plan_exists = Path(bundle["paths"]["live_proof_plan"]).exists()
            live_proof_markdown_exists = Path(bundle["paths"]["live_proof_plan_markdown"]).exists()
            live_proof_evidence_map_exists = Path(bundle["paths"]["live_proof_evidence_map"]).exists()
            live_proof_commands_exists = Path(bundle["paths"]["live_proof_commands"]).exists()
            live_proof_acceptance_exists = Path(bundle["paths"]["live_proof_acceptance"]).exists()
            live_proof_acceptance_markdown_exists = Path(bundle["paths"]["live_proof_acceptance_markdown"]).exists()
            live_proof_acceptance_csv_exists = Path(bundle["paths"]["live_proof_acceptance_csv"]).exists()
            live_proof_vault_exists = Path(bundle["paths"]["live_proof_evidence_vault"]).exists()
            live_proof_vault_markdown_exists = Path(bundle["paths"]["live_proof_evidence_vault_markdown"]).exists()
            live_proof_archive_index_exists = Path(bundle["paths"]["live_proof_archive_index"]).exists()
            market_ready_audit_exists = Path(bundle["paths"]["market_ready_audit"]).exists()
            market_ready_audit_markdown_exists = Path(bundle["paths"]["market_ready_audit_markdown"]).exists()
            market_ready_requirements_exists = Path(bundle["paths"]["market_ready_requirements"]).exists()
            daw_walkthrough_exists = Path(bundle["paths"]["daw_boardroom_demo_walkthrough"]).exists()
            daw_walkthrough_markdown_exists = Path(bundle["paths"]["daw_boardroom_demo_walkthrough_markdown"]).exists()
            daw_demo_checklist_exists = Path(bundle["paths"]["daw_demo_checklist"]).exists()
            daw_control_room_exists = Path(bundle["paths"]["daw_first_campaign_control_room"]).exists()
            daw_control_room_markdown_exists = Path(bundle["paths"]["daw_first_campaign_control_room_markdown"]).exists()
            daw_action_board_exists = Path(bundle["paths"]["daw_first_campaign_action_board"]).exists()
            customer_acceptance_exists = Path(bundle["paths"]["customer_acceptance_plan"]).exists()
            customer_acceptance_markdown_exists = Path(bundle["paths"]["customer_acceptance_plan_markdown"]).exists()
            acceptance_checklist_exists = Path(bundle["paths"]["acceptance_checklist"]).exists()
            customer_rollout_exists = Path(bundle["paths"]["customer_rollout_plan"]).exists()
            customer_rollout_markdown_exists = Path(bundle["paths"]["customer_rollout_plan_markdown"]).exists()
            rollout_workstreams_exists = Path(bundle["paths"]["rollout_workstreams"]).exists()
            first_campaign_launch_intake_exists = Path(bundle["paths"]["first_campaign_launch_intake"]).exists()
            first_campaign_launch_intake_markdown_exists = Path(bundle["paths"]["first_campaign_launch_intake_markdown"]).exists()
            first_campaign_launch_checklist_exists = Path(bundle["paths"]["first_campaign_launch_checklist"]).exists()
            customer_input_templates_exists = Path(bundle["paths"]["customer_input_templates"]).exists()
            customer_input_templates_markdown_exists = Path(bundle["paths"]["customer_input_templates_markdown"]).exists()
            partner_roster_template_exists = Path(bundle["paths"]["partner_roster_template"]).exists()
            territory_assignment_template_exists = Path(bundle["paths"]["territory_assignment_template"]).exists()
            property_source_template_exists = Path(bundle["paths"]["property_source_template"]).exists()
            suppression_list_template_exists = Path(bundle["paths"]["suppression_list_template"]).exists()
            message_approval_template_exists = Path(bundle["paths"]["message_approval_template"]).exists()
            partner_capacity_template_exists = Path(bundle["paths"]["partner_capacity_template"]).exists()
            first_campaign_input_validation_exists = Path(bundle["paths"]["first_campaign_input_validation"]).exists()
            first_campaign_input_validation_markdown_exists = Path(bundle["paths"]["first_campaign_input_validation_markdown"]).exists()
            first_campaign_input_issues_exists = Path(bundle["paths"]["first_campaign_input_issues"]).exists()
            first_campaign_import_plan_exists = Path(bundle["paths"]["first_campaign_import_plan"]).exists()
            first_campaign_import_plan_markdown_exists = Path(bundle["paths"]["first_campaign_import_plan_markdown"]).exists()
            first_campaign_staging_rows_exists = Path(bundle["paths"]["first_campaign_staging_rows"]).exists()
            first_wave_launch_gate_exists = Path(bundle["paths"]["first_wave_launch_gate"]).exists()
            first_wave_launch_gate_markdown_exists = Path(bundle["paths"]["first_wave_launch_gate_markdown"]).exists()
            first_wave_launch_gate_checklist_exists = Path(bundle["paths"]["first_wave_launch_gate_checklist"]).exists()
            first_wave_database_handoff_exists = Path(bundle["paths"]["first_wave_database_handoff"]).exists()
            first_wave_database_handoff_markdown_exists = Path(bundle["paths"]["first_wave_database_handoff_markdown"]).exists()
            first_wave_database_handoff_checklist_exists = Path(bundle["paths"]["first_wave_database_handoff_checklist"]).exists()
            first_wave_database_review_rows_exists = Path(bundle["paths"]["first_wave_database_review_rows"]).exists()
            first_wave_database_review_sql_exists = Path(bundle["paths"]["first_wave_database_review_sql"]).exists()
            partner_auth_mapping_exists = Path(bundle["paths"]["partner_auth_mapping"]).exists()
            partner_auth_mapping_markdown_exists = Path(bundle["paths"]["partner_auth_mapping_markdown"]).exists()
            partner_auth_mapping_template_exists = Path(bundle["paths"]["partner_auth_mapping_template"]).exists()
            partner_auth_mapping_rows_exists = Path(bundle["paths"]["partner_auth_mapping_rows"]).exists()
            partner_auth_mapping_issues_exists = Path(bundle["paths"]["partner_auth_mapping_issues"]).exists()
            partner_membership_review_sql_exists = Path(bundle["paths"]["partner_membership_review_sql"]).exists()
            partner_access_reconciliation_exists = Path(bundle["paths"]["partner_access_reconciliation"]).exists()
            partner_access_reconciliation_markdown_exists = Path(bundle["paths"]["partner_access_reconciliation_markdown"]).exists()
            partner_access_reconciliation_matrix_exists = Path(bundle["paths"]["partner_access_reconciliation_matrix"]).exists()
            partner_access_reconciliation_issues_exists = Path(bundle["paths"]["partner_access_reconciliation_issues"]).exists()
            example_completed_inputs_exists = Path(bundle["paths"]["example_completed_customer_inputs"]).exists()
            example_completed_inputs_markdown_exists = Path(bundle["paths"]["example_completed_customer_inputs_markdown"]).exists()
            example_completed_partner_roster_exists = Path(bundle["paths"]["example_completed_partner_roster"]).exists()
            example_completed_territory_assignment_exists = Path(bundle["paths"]["example_completed_territory_assignment"]).exists()
            example_completed_property_source_exists = Path(bundle["paths"]["example_completed_property_source"]).exists()
            example_completed_suppression_list_exists = Path(bundle["paths"]["example_completed_suppression_list"]).exists()
            example_completed_message_approval_exists = Path(bundle["paths"]["example_completed_message_approval"]).exists()
            example_completed_partner_capacity_exists = Path(bundle["paths"]["example_completed_partner_capacity"]).exists()
            example_first_campaign_input_validation_exists = Path(bundle["paths"]["example_first_campaign_input_validation"]).exists()
            example_first_campaign_input_validation_markdown_exists = Path(bundle["paths"]["example_first_campaign_input_validation_markdown"]).exists()
            example_first_campaign_input_issues_exists = Path(bundle["paths"]["example_first_campaign_input_issues"]).exists()
            example_first_campaign_import_plan_exists = Path(bundle["paths"]["example_first_campaign_import_plan"]).exists()
            example_first_campaign_import_plan_markdown_exists = Path(bundle["paths"]["example_first_campaign_import_plan_markdown"]).exists()
            example_first_campaign_staging_rows_exists = Path(bundle["paths"]["example_first_campaign_staging_rows"]).exists()
            example_first_wave_launch_gate_exists = Path(bundle["paths"]["example_first_wave_launch_gate"]).exists()
            example_first_wave_launch_gate_markdown_exists = Path(bundle["paths"]["example_first_wave_launch_gate_markdown"]).exists()
            example_first_wave_launch_gate_checklist_exists = Path(bundle["paths"]["example_first_wave_launch_gate_checklist"]).exists()
            procurement_exists = Path(bundle["paths"]["procurement_review"]).exists()
            procurement_markdown_exists = Path(bundle["paths"]["procurement_review_markdown"]).exists()
            security_questionnaire_exists = Path(bundle["paths"]["security_questionnaire"]).exists()
            procurement_risk_register_exists = Path(bundle["paths"]["procurement_risk_register"]).exists()
            support_sla_exists = Path(bundle["paths"]["support_sla_plan"]).exists()
            support_sla_markdown_exists = Path(bundle["paths"]["support_sla_plan_markdown"]).exists()
            support_escalation_exists = Path(bundle["paths"]["support_escalation_matrix"]).exists()
            incident_playbook_exists = Path(bundle["paths"]["incident_response_playbook"]).exists()
            customer_pilot_exists = Path(bundle["paths"]["customer_pilot_proposal"]).exists()
            customer_pilot_markdown_exists = Path(bundle["paths"]["customer_pilot_proposal_markdown"]).exists()
            pilot_scope_checklist_exists = Path(bundle["paths"]["pilot_scope_checklist"]).exists()
            commercial_assumptions_exists = Path(bundle["paths"]["commercial_assumptions"]).exists()
            customer_training_exists = Path(bundle["paths"]["customer_training_plan"]).exists()
            customer_training_guide_exists = Path(bundle["paths"]["customer_training_guide"]).exists()
            training_session_plan_exists = Path(bundle["paths"]["training_session_plan"]).exists()
            role_cheatsheet_exists = Path(bundle["paths"]["role_cheatsheet"]).exists()
            value_plan_exists = Path(bundle["paths"]["value_realization_plan"]).exists()
            value_plan_markdown_exists = Path(bundle["paths"]["value_realization_plan_markdown"]).exists()
            value_metrics_exists = Path(bundle["paths"]["value_realization_metrics"]).exists()
            executive_decision_log_exists = Path(bundle["paths"]["executive_decision_log"]).exists()
            outcome_contract_exists = Path(bundle["paths"]["outcome_measurement_contract"]).exists()
            outcome_contract_markdown_exists = Path(bundle["paths"]["outcome_measurement_contract_markdown"]).exists()
            outcome_event_schema_exists = Path(bundle["paths"]["outcome_event_schema"]).exists()
            outcome_sync_template_exists = Path(bundle["paths"]["outcome_sync_template"]).exists()
            outcome_reconciliation_checklist_exists = Path(bundle["paths"]["outcome_reconciliation_checklist"]).exists()
            outcome_import_exists = Path(bundle["paths"]["outcome_import_validation"]).exists()
            outcome_import_markdown_exists = Path(bundle["paths"]["outcome_import_validation_markdown"]).exists()
            outcome_import_issues_exists = Path(bundle["paths"]["outcome_import_issues"]).exists()
            outcome_import_review_rows_exists = Path(bundle["paths"]["outcome_import_review_rows"]).exists()
            module_expansion_exists = Path(bundle["paths"]["module_expansion_plan"]).exists()
            module_expansion_markdown_exists = Path(bundle["paths"]["module_expansion_plan_markdown"]).exists()
            module_value_matrix_exists = Path(bundle["paths"]["module_value_matrix"]).exists()
            expansion_decision_tree_exists = Path(bundle["paths"]["expansion_decision_tree"]).exists()
            module_readiness_exists = Path(bundle["paths"]["module_readiness_matrix"]).exists()
            module_readiness_markdown_exists = Path(bundle["paths"]["module_readiness_matrix_markdown"]).exists()
            module_readiness_csv_exists = Path(bundle["paths"]["module_readiness_matrix_csv"]).exists()
            module_metric_coverage_exists = Path(bundle["paths"]["module_metric_coverage"]).exists()
            public_register_exists = Path(bundle["paths"]["public_data_source_register"]).exists()
            public_register_markdown_exists = Path(bundle["paths"]["public_data_source_register_markdown"]).exists()
            public_matrix_exists = Path(bundle["paths"]["public_data_source_matrix"]).exists()
            blocked_data_exists = Path(bundle["paths"]["blocked_data_register"]).exists()
            attribution_requirements_exists = Path(bundle["paths"]["attribution_requirements"]).exists()
            public_data_production_intake_exists = Path(bundle["paths"]["public_data_production_intake"]).exists()
            public_data_production_intake_markdown_exists = Path(bundle["paths"]["public_data_production_intake_markdown"]).exists()
            public_data_approval_checklist_exists = Path(bundle["paths"]["public_data_approval_checklist"]).exists()
            public_data_reconciliation_exists = Path(bundle["paths"]["public_data_reconciliation"]).exists()
            public_data_reconciliation_markdown_exists = Path(bundle["paths"]["public_data_reconciliation_markdown"]).exists()
            public_data_reconciliation_matrix_exists = Path(bundle["paths"]["public_data_reconciliation_matrix"]).exists()
            public_data_reconciliation_issues_exists = Path(bundle["paths"]["public_data_reconciliation_issues"]).exists()
            customer_signoff_reconciliation_exists = Path(bundle["paths"]["customer_signoff_reconciliation"]).exists()
            customer_signoff_reconciliation_markdown_exists = Path(bundle["paths"]["customer_signoff_reconciliation_markdown"]).exists()
            customer_signoff_reconciliation_matrix_exists = Path(bundle["paths"]["customer_signoff_reconciliation_matrix"]).exists()
            customer_signoff_reconciliation_issues_exists = Path(bundle["paths"]["customer_signoff_reconciliation_issues"]).exists()
            customer_signoff_intake_exists = Path(bundle["paths"]["customer_signoff_intake_markdown"]).exists()
            customer_signoff_template_exists = Path(bundle["paths"]["customer_signoff_evidence_template"]).exists()
            customer_view_catalog_exists = Path(bundle["paths"]["customer_view_catalog"]).exists()
            customer_view_catalog_markdown_exists = Path(bundle["paths"]["customer_view_catalog_markdown"]).exists()
            customer_view_matrix_exists = Path(bundle["paths"]["customer_view_matrix"]).exists()
            data_platform_blueprint_exists = Path(bundle["paths"]["data_platform_blueprint"]).exists()
            data_platform_blueprint_markdown_exists = Path(bundle["paths"]["data_platform_blueprint_markdown"]).exists()
            data_platform_scope_matrix_exists = Path(bundle["paths"]["data_platform_scope_matrix"]).exists()
            portable_html_exists = Path(bundle["paths"]["portable_data_room_html"]).exists()
            portable_manifest_exists = Path(bundle["paths"]["portable_data_room_manifest"]).exists()
            portable_zip_exists = Path(bundle["paths"]["portable_data_room_zip"]).exists()
            market_readiness = json.loads(Path(bundle["paths"]["market_readiness_scorecard"]).read_text(encoding="utf-8"))
            market_readiness_markdown = Path(bundle["paths"]["market_readiness_markdown"]).read_text(encoding="utf-8")
            market_readiness_html = Path(bundle["paths"]["market_readiness_html"]).read_text(encoding="utf-8")
            live_launch_control_room = json.loads(Path(bundle["paths"]["live_launch_control_room"]).read_text(encoding="utf-8"))
            live_launch_control_markdown = Path(bundle["paths"]["live_launch_control_room_markdown"]).read_text(encoding="utf-8")
            live_launch_action_board = Path(bundle["paths"]["live_launch_action_board"]).read_text(encoding="utf-8")
            live_credential_handoff = json.loads(Path(bundle["paths"]["live_credential_handoff"]).read_text(encoding="utf-8"))
            live_credential_markdown = Path(bundle["paths"]["live_credential_handoff_markdown"]).read_text(encoding="utf-8")
            live_credential_checklist = Path(bundle["paths"]["live_credential_handoff_checklist"]).read_text(encoding="utf-8")
            live_secret_channel_contract = Path(bundle["paths"]["live_secret_channel_contract"]).read_text(encoding="utf-8")
            live_proof_plan = json.loads(Path(bundle["paths"]["live_proof_plan"]).read_text(encoding="utf-8"))
            live_proof_markdown = Path(bundle["paths"]["live_proof_plan_markdown"]).read_text(encoding="utf-8")
            live_proof_evidence_map = Path(bundle["paths"]["live_proof_evidence_map"]).read_text(encoding="utf-8")
            live_proof_commands = Path(bundle["paths"]["live_proof_commands"]).read_text(encoding="utf-8")
            live_proof_acceptance = json.loads(Path(bundle["paths"]["live_proof_acceptance"]).read_text(encoding="utf-8"))
            live_proof_acceptance_markdown = Path(bundle["paths"]["live_proof_acceptance_markdown"]).read_text(encoding="utf-8")
            live_proof_acceptance_csv = Path(bundle["paths"]["live_proof_acceptance_csv"]).read_text(encoding="utf-8")
            live_proof_vault = json.loads(Path(bundle["paths"]["live_proof_evidence_vault"]).read_text(encoding="utf-8"))
            live_proof_vault_markdown = Path(bundle["paths"]["live_proof_evidence_vault_markdown"]).read_text(encoding="utf-8")
            live_proof_archive_index = Path(bundle["paths"]["live_proof_archive_index"]).read_text(encoding="utf-8")
            market_ready_audit = json.loads(Path(bundle["paths"]["market_ready_audit"]).read_text(encoding="utf-8"))
            market_ready_audit_markdown = Path(bundle["paths"]["market_ready_audit_markdown"]).read_text(encoding="utf-8")
            market_ready_requirements = Path(bundle["paths"]["market_ready_requirements"]).read_text(encoding="utf-8")
            daw_walkthrough = json.loads(Path(bundle["paths"]["daw_boardroom_demo_walkthrough"]).read_text(encoding="utf-8"))
            daw_walkthrough_markdown = Path(bundle["paths"]["daw_boardroom_demo_walkthrough_markdown"]).read_text(encoding="utf-8")
            daw_demo_checklist = Path(bundle["paths"]["daw_demo_checklist"]).read_text(encoding="utf-8")
            daw_control_room = json.loads(Path(bundle["paths"]["daw_first_campaign_control_room"]).read_text(encoding="utf-8"))
            daw_control_room_markdown = Path(bundle["paths"]["daw_first_campaign_control_room_markdown"]).read_text(encoding="utf-8")
            daw_action_board = Path(bundle["paths"]["daw_first_campaign_action_board"]).read_text(encoding="utf-8")
            customer_acceptance = json.loads(Path(bundle["paths"]["customer_acceptance_plan"]).read_text(encoding="utf-8"))
            customer_rollout = json.loads(Path(bundle["paths"]["customer_rollout_plan"]).read_text(encoding="utf-8"))
            first_campaign_launch = json.loads(Path(bundle["paths"]["first_campaign_launch_intake"]).read_text(encoding="utf-8"))
            first_campaign_checklist = Path(bundle["paths"]["first_campaign_launch_checklist"]).read_text(encoding="utf-8")
            customer_input_templates = json.loads(Path(bundle["paths"]["customer_input_templates"]).read_text(encoding="utf-8"))
            partner_roster_template = Path(bundle["paths"]["partner_roster_template"]).read_text(encoding="utf-8")
            suppression_list_template = Path(bundle["paths"]["suppression_list_template"]).read_text(encoding="utf-8")
            first_campaign_input_validation = json.loads(Path(bundle["paths"]["first_campaign_input_validation"]).read_text(encoding="utf-8"))
            first_campaign_input_issues = Path(bundle["paths"]["first_campaign_input_issues"]).read_text(encoding="utf-8")
            first_campaign_import_plan = json.loads(Path(bundle["paths"]["first_campaign_import_plan"]).read_text(encoding="utf-8"))
            first_campaign_staging_rows = Path(bundle["paths"]["first_campaign_staging_rows"]).read_text(encoding="utf-8")
            first_wave_launch_gate = json.loads(Path(bundle["paths"]["first_wave_launch_gate"]).read_text(encoding="utf-8"))
            first_wave_launch_gate_checklist = Path(bundle["paths"]["first_wave_launch_gate_checklist"]).read_text(encoding="utf-8")
            first_wave_database_handoff = json.loads(Path(bundle["paths"]["first_wave_database_handoff"]).read_text(encoding="utf-8"))
            first_wave_database_handoff_markdown = Path(bundle["paths"]["first_wave_database_handoff_markdown"]).read_text(encoding="utf-8")
            first_wave_database_handoff_checklist = Path(bundle["paths"]["first_wave_database_handoff_checklist"]).read_text(encoding="utf-8")
            first_wave_database_review_rows = Path(bundle["paths"]["first_wave_database_review_rows"]).read_text(encoding="utf-8")
            first_wave_database_review_sql = Path(bundle["paths"]["first_wave_database_review_sql"]).read_text(encoding="utf-8")
            partner_auth_mapping = json.loads(Path(bundle["paths"]["partner_auth_mapping"]).read_text(encoding="utf-8"))
            partner_auth_mapping_markdown = Path(bundle["paths"]["partner_auth_mapping_markdown"]).read_text(encoding="utf-8")
            partner_auth_mapping_template = Path(bundle["paths"]["partner_auth_mapping_template"]).read_text(encoding="utf-8")
            partner_auth_mapping_issues = Path(bundle["paths"]["partner_auth_mapping_issues"]).read_text(encoding="utf-8")
            partner_membership_review_sql = Path(bundle["paths"]["partner_membership_review_sql"]).read_text(encoding="utf-8")
            partner_access_reconciliation = json.loads(Path(bundle["paths"]["partner_access_reconciliation"]).read_text(encoding="utf-8"))
            partner_access_reconciliation_markdown = Path(bundle["paths"]["partner_access_reconciliation_markdown"]).read_text(encoding="utf-8")
            partner_access_reconciliation_matrix = Path(bundle["paths"]["partner_access_reconciliation_matrix"]).read_text(encoding="utf-8")
            partner_access_reconciliation_issues = Path(bundle["paths"]["partner_access_reconciliation_issues"]).read_text(encoding="utf-8")
            example_inputs = json.loads(Path(bundle["paths"]["example_completed_customer_inputs"]).read_text(encoding="utf-8"))
            example_partner_roster = Path(bundle["paths"]["example_completed_partner_roster"]).read_text(encoding="utf-8")
            example_validation = json.loads(Path(bundle["paths"]["example_first_campaign_input_validation"]).read_text(encoding="utf-8"))
            example_issues = Path(bundle["paths"]["example_first_campaign_input_issues"]).read_text(encoding="utf-8")
            example_import_plan = json.loads(Path(bundle["paths"]["example_first_campaign_import_plan"]).read_text(encoding="utf-8"))
            example_staging_rows = Path(bundle["paths"]["example_first_campaign_staging_rows"]).read_text(encoding="utf-8")
            example_launch_gate = json.loads(Path(bundle["paths"]["example_first_wave_launch_gate"]).read_text(encoding="utf-8"))
            example_launch_gate_checklist = Path(bundle["paths"]["example_first_wave_launch_gate_checklist"]).read_text(encoding="utf-8")
            procurement_review = json.loads(Path(bundle["paths"]["procurement_review"]).read_text(encoding="utf-8"))
            support_sla = json.loads(Path(bundle["paths"]["support_sla_plan"]).read_text(encoding="utf-8"))
            customer_pilot = json.loads(Path(bundle["paths"]["customer_pilot_proposal"]).read_text(encoding="utf-8"))
            customer_training = json.loads(Path(bundle["paths"]["customer_training_plan"]).read_text(encoding="utf-8"))
            value_realization = json.loads(Path(bundle["paths"]["value_realization_plan"]).read_text(encoding="utf-8"))
            outcome_contract = json.loads(Path(bundle["paths"]["outcome_measurement_contract"]).read_text(encoding="utf-8"))
            outcome_markdown = Path(bundle["paths"]["outcome_measurement_contract_markdown"]).read_text(encoding="utf-8")
            outcome_schema = Path(bundle["paths"]["outcome_event_schema"]).read_text(encoding="utf-8")
            outcome_template = Path(bundle["paths"]["outcome_sync_template"]).read_text(encoding="utf-8")
            outcome_checklist = Path(bundle["paths"]["outcome_reconciliation_checklist"]).read_text(encoding="utf-8")
            outcome_import = json.loads(Path(bundle["paths"]["outcome_import_validation"]).read_text(encoding="utf-8"))
            outcome_import_markdown = Path(bundle["paths"]["outcome_import_validation_markdown"]).read_text(encoding="utf-8")
            outcome_import_issues = Path(bundle["paths"]["outcome_import_issues"]).read_text(encoding="utf-8")
            outcome_import_rows = Path(bundle["paths"]["outcome_import_review_rows"]).read_text(encoding="utf-8")
            module_expansion = json.loads(Path(bundle["paths"]["module_expansion_plan"]).read_text(encoding="utf-8"))
            module_readiness = json.loads(Path(bundle["paths"]["module_readiness_matrix"]).read_text(encoding="utf-8"))
            module_readiness_markdown = Path(bundle["paths"]["module_readiness_matrix_markdown"]).read_text(encoding="utf-8")
            module_readiness_csv = Path(bundle["paths"]["module_readiness_matrix_csv"]).read_text(encoding="utf-8")
            module_metric_coverage = Path(bundle["paths"]["module_metric_coverage"]).read_text(encoding="utf-8")
            public_register = json.loads(Path(bundle["paths"]["public_data_source_register"]).read_text(encoding="utf-8"))
            public_data_intake = json.loads(Path(bundle["paths"]["public_data_production_intake"]).read_text(encoding="utf-8"))
            public_data_approval_checklist = Path(bundle["paths"]["public_data_approval_checklist"]).read_text(encoding="utf-8")
            public_data_reconciliation = json.loads(Path(bundle["paths"]["public_data_reconciliation"]).read_text(encoding="utf-8"))
            public_data_reconciliation_markdown = Path(bundle["paths"]["public_data_reconciliation_markdown"]).read_text(encoding="utf-8")
            public_data_reconciliation_matrix = Path(bundle["paths"]["public_data_reconciliation_matrix"]).read_text(encoding="utf-8")
            public_data_reconciliation_issues = Path(bundle["paths"]["public_data_reconciliation_issues"]).read_text(encoding="utf-8")
            customer_signoff_reconciliation = json.loads(Path(bundle["paths"]["customer_signoff_reconciliation"]).read_text(encoding="utf-8"))
            customer_signoff_reconciliation_markdown = Path(bundle["paths"]["customer_signoff_reconciliation_markdown"]).read_text(encoding="utf-8")
            customer_signoff_reconciliation_matrix = Path(bundle["paths"]["customer_signoff_reconciliation_matrix"]).read_text(encoding="utf-8")
            customer_signoff_reconciliation_issues = Path(bundle["paths"]["customer_signoff_reconciliation_issues"]).read_text(encoding="utf-8")
            customer_signoff_intake = Path(bundle["paths"]["customer_signoff_intake_markdown"]).read_text(encoding="utf-8")
            customer_signoff_template = Path(bundle["paths"]["customer_signoff_evidence_template"]).read_text(encoding="utf-8")
            customer_view_catalog = json.loads(Path(bundle["paths"]["customer_view_catalog"]).read_text(encoding="utf-8"))
            customer_view_catalog_markdown = Path(bundle["paths"]["customer_view_catalog_markdown"]).read_text(encoding="utf-8")
            customer_view_matrix = Path(bundle["paths"]["customer_view_matrix"]).read_text(encoding="utf-8")
            data_platform_blueprint = json.loads(Path(bundle["paths"]["data_platform_blueprint"]).read_text(encoding="utf-8"))
            data_platform_blueprint_markdown = Path(bundle["paths"]["data_platform_blueprint_markdown"]).read_text(encoding="utf-8")
            data_platform_scope_matrix = Path(bundle["paths"]["data_platform_scope_matrix"]).read_text(encoding="utf-8")
            portable_manifest = json.loads(Path(bundle["paths"]["portable_data_room_manifest"]).read_text(encoding="utf-8"))
            portable_html = Path(bundle["paths"]["portable_data_room_html"]).read_text(encoding="utf-8")
            with zipfile.ZipFile(bundle["paths"]["portable_data_room_zip"]) as archive:
                portable_zip_names = archive.namelist()
                portable_zip_text = "\n".join(
                    archive.read(name).decode("utf-8", errors="ignore")
                    for name in portable_zip_names
                    if Path(name).suffix in {".csv", ".html", ".js", ".json", ".jsonl", ".md", ".sh", ".sql", ".txt"}
                )

        self.assertEqual(bundle["stage_status"], "pass")
        self.assertEqual(bundle["decisions"]["buyer_review"], "go")
        self.assertEqual(bundle["decisions"]["production"], "no_go")
        self.assertTrue(release_audit_exists)
        self.assertTrue(preflight_exists)
        self.assertTrue(ops_status_exists)
        self.assertTrue(status_page_exists)
        self.assertTrue(production_proof_exists)
        self.assertTrue(production_proof_markdown_exists)
        self.assertEqual(production_proof["status"], "buyer_review_ready")
        self.assertEqual(production_proof["redaction"]["status"], "pass")
        self.assertTrue(production_cutover_exists)
        self.assertTrue(production_cutover_runbook_exists)
        self.assertEqual(production_cutover["status"], "dry_run_ready")
        self.assertEqual(production_cutover["mode"], "dry_run")
        self.assertFalse(production_cutover["production_verified"])
        self.assertEqual(production_cutover["decisions"]["production"], "no_go")
        cutover_steps = {step["name"]: step for step in production_cutover["steps"]}
        self.assertEqual(cutover_steps["schema_verification"]["production_verified"], False)
        self.assertEqual(cutover_steps["rls_launch"]["production_verified"], False)
        self.assertEqual(cutover_steps["customer_access_verification"]["production_verified"], False)
        self.assertIn("HomePilot Production Cutover", production_cutover_runbook)
        self.assertIn("Mode: dry_run", production_cutover_runbook)
        self.assertTrue(deployment_manifest_exists)
        self.assertTrue(sql_apply_plan_exists)
        self.assertTrue(sql_apply_runbook_exists)
        self.assertTrue(apply_sql_exists)
        self.assertTrue(post_apply_verification_exists)
        self.assertTrue(market_readiness_exists)
        self.assertTrue(market_readiness_markdown_exists)
        self.assertTrue(market_readiness_html_exists)
        self.assertIn("Customer Decision Board", market_readiness_markdown)
        self.assertIn("Signed/approved", market_readiness_markdown)
        self.assertIn("Buyer-ready is not customer-approved", market_readiness_markdown)
        self.assertIn("Live Proof Cockpit", market_readiness_markdown)
        self.assertIn("Live proof acceptance matrix", market_readiness_markdown)
        self.assertIn("customer_access_verified", market_readiness_markdown)
        self.assertIn("production_verified=false", market_readiness_markdown)
        self.assertIn("Data Platform Blueprint", market_readiness_markdown)
        self.assertIn("tenant -> modules -> campaigns -> properties -> assessments -> interactions", market_readiness_markdown)
        self.assertIn("Outcome Measurement Contract", market_readiness_markdown)
        self.assertIn("Outcome Import Dry-Run", market_readiness_markdown)
        self.assertIn("appointments, quotes, won/lost projects", market_readiness_markdown)
        self.assertIn("Customer Decision Board", market_readiness_html)
        self.assertIn("Signed/approved", market_readiness_html)
        self.assertIn("customer-access proof", market_readiness_html)
        self.assertIn("Live Proof Cockpit", market_readiness_html)
        self.assertIn("Live Credential Handoff", market_readiness_html)
        self.assertIn("Live proof acceptance matrix", market_readiness_html)
        self.assertIn("customer_access_verified", market_readiness_html)
        self.assertIn("production_verified=false", market_readiness_html)
        self.assertIn("Data Platform Blueprint", market_readiness_html)
        self.assertIn("One shared property spine", market_readiness_html)
        self.assertIn("Outcome Measurement Contract", market_readiness_html)
        self.assertIn("Outcome Import Dry-Run", market_readiness_html)
        self.assertIn("Closed-loop measurement", market_readiness_html)
        self.assertTrue(data_room_index_exists)
        self.assertTrue(market_actions_exists)
        self.assertTrue(stakeholder_views_exists)
        self.assertTrue(live_launch_control_room_exists)
        self.assertTrue(live_launch_control_room_markdown_exists)
        self.assertTrue(live_launch_action_board_exists)
        self.assertTrue(live_credential_handoff_exists)
        self.assertTrue(live_credential_handoff_markdown_exists)
        self.assertTrue(live_credential_handoff_checklist_exists)
        self.assertTrue(live_secret_channel_contract_exists)
        self.assertTrue(live_proof_plan_exists)
        self.assertTrue(live_proof_markdown_exists)
        self.assertTrue(live_proof_evidence_map_exists)
        self.assertTrue(live_proof_commands_exists)
        self.assertTrue(live_proof_acceptance_exists)
        self.assertTrue(live_proof_acceptance_markdown_exists)
        self.assertTrue(live_proof_acceptance_csv_exists)
        self.assertTrue(live_proof_vault_exists)
        self.assertTrue(live_proof_vault_markdown_exists)
        self.assertTrue(live_proof_archive_index_exists)
        self.assertTrue(market_ready_audit_exists)
        self.assertTrue(market_ready_audit_markdown_exists)
        self.assertTrue(market_ready_requirements_exists)
        self.assertTrue(daw_walkthrough_exists)
        self.assertTrue(daw_walkthrough_markdown_exists)
        self.assertTrue(daw_demo_checklist_exists)
        self.assertTrue(daw_control_room_exists)
        self.assertTrue(daw_control_room_markdown_exists)
        self.assertTrue(daw_action_board_exists)
        self.assertTrue(customer_acceptance_exists)
        self.assertTrue(customer_acceptance_markdown_exists)
        self.assertTrue(acceptance_checklist_exists)
        self.assertTrue(customer_rollout_exists)
        self.assertTrue(customer_rollout_markdown_exists)
        self.assertTrue(rollout_workstreams_exists)
        self.assertTrue(first_campaign_launch_intake_exists)
        self.assertTrue(first_campaign_launch_intake_markdown_exists)
        self.assertTrue(first_campaign_launch_checklist_exists)
        self.assertTrue(customer_input_templates_exists)
        self.assertTrue(customer_input_templates_markdown_exists)
        self.assertTrue(partner_roster_template_exists)
        self.assertTrue(territory_assignment_template_exists)
        self.assertTrue(property_source_template_exists)
        self.assertTrue(suppression_list_template_exists)
        self.assertTrue(message_approval_template_exists)
        self.assertTrue(partner_capacity_template_exists)
        self.assertTrue(first_campaign_input_validation_exists)
        self.assertTrue(first_campaign_input_validation_markdown_exists)
        self.assertTrue(first_campaign_input_issues_exists)
        self.assertTrue(first_campaign_import_plan_exists)
        self.assertTrue(first_campaign_import_plan_markdown_exists)
        self.assertTrue(first_campaign_staging_rows_exists)
        self.assertTrue(first_wave_launch_gate_exists)
        self.assertTrue(first_wave_launch_gate_markdown_exists)
        self.assertTrue(first_wave_launch_gate_checklist_exists)
        self.assertTrue(first_wave_database_handoff_exists)
        self.assertTrue(first_wave_database_handoff_markdown_exists)
        self.assertTrue(first_wave_database_handoff_checklist_exists)
        self.assertTrue(first_wave_database_review_rows_exists)
        self.assertTrue(first_wave_database_review_sql_exists)
        self.assertTrue(partner_auth_mapping_exists)
        self.assertTrue(partner_auth_mapping_markdown_exists)
        self.assertTrue(partner_auth_mapping_template_exists)
        self.assertTrue(partner_auth_mapping_rows_exists)
        self.assertTrue(partner_auth_mapping_issues_exists)
        self.assertTrue(partner_membership_review_sql_exists)
        self.assertTrue(partner_access_reconciliation_exists)
        self.assertTrue(partner_access_reconciliation_markdown_exists)
        self.assertTrue(partner_access_reconciliation_matrix_exists)
        self.assertTrue(partner_access_reconciliation_issues_exists)
        self.assertTrue(example_completed_inputs_exists)
        self.assertTrue(example_completed_inputs_markdown_exists)
        self.assertTrue(example_completed_partner_roster_exists)
        self.assertTrue(example_completed_territory_assignment_exists)
        self.assertTrue(example_completed_property_source_exists)
        self.assertTrue(example_completed_suppression_list_exists)
        self.assertTrue(example_completed_message_approval_exists)
        self.assertTrue(example_completed_partner_capacity_exists)
        self.assertTrue(example_first_campaign_input_validation_exists)
        self.assertTrue(example_first_campaign_input_validation_markdown_exists)
        self.assertTrue(example_first_campaign_input_issues_exists)
        self.assertTrue(example_first_campaign_import_plan_exists)
        self.assertTrue(example_first_campaign_import_plan_markdown_exists)
        self.assertTrue(example_first_campaign_staging_rows_exists)
        self.assertTrue(example_first_wave_launch_gate_exists)
        self.assertTrue(example_first_wave_launch_gate_markdown_exists)
        self.assertTrue(example_first_wave_launch_gate_checklist_exists)
        self.assertTrue(procurement_exists)
        self.assertTrue(procurement_markdown_exists)
        self.assertTrue(security_questionnaire_exists)
        self.assertTrue(procurement_risk_register_exists)
        self.assertTrue(support_sla_exists)
        self.assertTrue(support_sla_markdown_exists)
        self.assertTrue(support_escalation_exists)
        self.assertTrue(incident_playbook_exists)
        self.assertTrue(customer_pilot_exists)
        self.assertTrue(customer_pilot_markdown_exists)
        self.assertTrue(pilot_scope_checklist_exists)
        self.assertTrue(commercial_assumptions_exists)
        self.assertTrue(customer_training_exists)
        self.assertTrue(customer_training_guide_exists)
        self.assertTrue(training_session_plan_exists)
        self.assertTrue(role_cheatsheet_exists)
        self.assertTrue(value_plan_exists)
        self.assertTrue(value_plan_markdown_exists)
        self.assertTrue(value_metrics_exists)
        self.assertTrue(executive_decision_log_exists)
        self.assertTrue(outcome_contract_exists)
        self.assertTrue(outcome_contract_markdown_exists)
        self.assertTrue(outcome_event_schema_exists)
        self.assertTrue(outcome_sync_template_exists)
        self.assertTrue(outcome_reconciliation_checklist_exists)
        self.assertTrue(outcome_import_exists)
        self.assertTrue(outcome_import_markdown_exists)
        self.assertTrue(outcome_import_issues_exists)
        self.assertTrue(outcome_import_review_rows_exists)
        self.assertTrue(module_expansion_exists)
        self.assertTrue(module_expansion_markdown_exists)
        self.assertTrue(module_value_matrix_exists)
        self.assertTrue(expansion_decision_tree_exists)
        self.assertTrue(module_readiness_exists)
        self.assertTrue(module_readiness_markdown_exists)
        self.assertTrue(module_readiness_csv_exists)
        self.assertTrue(module_metric_coverage_exists)
        self.assertTrue(public_register_exists)
        self.assertTrue(public_register_markdown_exists)
        self.assertTrue(public_matrix_exists)
        self.assertTrue(blocked_data_exists)
        self.assertTrue(attribution_requirements_exists)
        self.assertTrue(public_data_production_intake_exists)
        self.assertTrue(public_data_production_intake_markdown_exists)
        self.assertTrue(public_data_approval_checklist_exists)
        self.assertTrue(public_data_reconciliation_exists)
        self.assertTrue(public_data_reconciliation_markdown_exists)
        self.assertTrue(public_data_reconciliation_matrix_exists)
        self.assertTrue(public_data_reconciliation_issues_exists)
        self.assertTrue(customer_signoff_reconciliation_exists)
        self.assertTrue(customer_signoff_reconciliation_markdown_exists)
        self.assertTrue(customer_signoff_reconciliation_matrix_exists)
        self.assertTrue(customer_signoff_reconciliation_issues_exists)
        self.assertTrue(customer_signoff_intake_exists)
        self.assertTrue(customer_signoff_template_exists)
        self.assertTrue(customer_view_catalog_exists)
        self.assertTrue(customer_view_catalog_markdown_exists)
        self.assertTrue(customer_view_matrix_exists)
        self.assertTrue(data_platform_blueprint_exists)
        self.assertTrue(data_platform_blueprint_markdown_exists)
        self.assertTrue(data_platform_scope_matrix_exists)
        self.assertTrue(portable_html_exists)
        self.assertTrue(portable_manifest_exists)
        self.assertTrue(portable_zip_exists)
        self.assertEqual(market_readiness["status"], "market_review_ready")
        self.assertEqual(market_readiness["decisions"]["buyer_review"], "go")
        self.assertEqual(market_readiness["decisions"]["production"], "no_go")
        self.assertEqual(live_launch_control_room["status"], "blocked_until_live_inputs")
        self.assertEqual(live_launch_control_room["summary"]["live_launch_task_count"], 10)
        self.assertFalse(live_launch_control_room["summary"]["first_wave_launch_authorized"])
        self.assertEqual(live_launch_control_room["summary"]["partner_auth_mapping_status"], "mapping_required")
        self.assertEqual(live_launch_control_room["summary"]["partner_auth_expected_count"], 10)
        self.assertEqual(live_launch_control_room["summary"]["partner_auth_mapped_count"], 0)
        self.assertEqual(live_launch_control_room["summary"]["partner_access_reconciliation_status"], "blocked_until_partner_auth_mapping")
        self.assertEqual(live_launch_control_room["summary"]["partner_access_reconciled_count"], 0)
        self.assertEqual(live_launch_control_room["summary"]["public_data_reconciliation_status"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertEqual(live_launch_control_room["summary"]["public_data_approved_source_count"], 0)
        self.assertEqual(live_launch_control_room["summary"]["public_data_registered_source_count"], 7)
        self.assertGreaterEqual(live_launch_control_room["summary"]["public_data_reconciliation_blockers"], 1)
        self.assertFalse(live_launch_control_room["summary"]["public_data_first_wave_required"])
        self.assertEqual(live_launch_control_room["summary"]["customer_signoff_reconciliation_status"], "blocked_until_customer_signoff_and_live_proof")
        self.assertEqual(live_launch_control_room["summary"]["customer_signoff_signed_decision_count"], 0)
        self.assertEqual(live_launch_control_room["summary"]["customer_signoff_decision_count"], 10)
        self.assertGreaterEqual(live_launch_control_room["summary"]["customer_signoff_live_launch_blockers"], 1)
        self.assertGreaterEqual(live_launch_control_room["summary"]["customer_signoff_production_blockers"], 1)
        self.assertFalse(live_launch_control_room["summary"]["production_verified"])
        live_stage_gates = {gate["key"]: gate for gate in live_launch_control_room["stage_gates"]}
        self.assertEqual(live_stage_gates["partner_auth_mapping"]["status"], "blocked")
        self.assertTrue(live_stage_gates["partner_auth_mapping"]["blocks_production"])
        self.assertFalse(live_stage_gates["partner_auth_mapping"]["blocks_live_launch"])
        self.assertEqual(live_stage_gates["partner_access_reconciliation"]["status"], "blocked")
        self.assertTrue(live_stage_gates["partner_access_reconciliation"]["blocks_production"])
        self.assertFalse(live_stage_gates["partner_access_reconciliation"]["blocks_live_launch"])
        self.assertEqual(live_stage_gates["public_data_reconciliation"]["status"], "blocked")
        self.assertTrue(live_stage_gates["public_data_reconciliation"]["blocks_production"])
        self.assertFalse(live_stage_gates["public_data_reconciliation"]["blocks_live_launch"])
        self.assertEqual(live_stage_gates["customer_signoff_reconciliation"]["status"], "blocked")
        self.assertTrue(live_stage_gates["customer_signoff_reconciliation"]["blocks_production"])
        self.assertTrue(live_stage_gates["customer_signoff_reconciliation"]["blocks_live_launch"])
        self.assertTrue(live_launch_control_room["guardrails"]["no_live_writes"])
        self.assertFalse(live_launch_control_room["guardrails"]["secret_values_written"])
        self.assertEqual(live_launch_control_room["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Live Launch Control Room", live_launch_control_markdown)
        self.assertIn("production_verified=true", live_launch_control_markdown)
        self.assertIn("HOMEPILOT_SUPABASE_URL", live_launch_action_board)
        self.assertIn("partner_access", live_launch_action_board)
        self.assertIn("partner_access_reconciliation", live_launch_action_board)
        self.assertIn("customer_signoff_reconciliation", live_launch_action_board)
        self.assertIn("first_wave_go_no_go_missing", live_launch_action_board)
        self.assertIn("supabase_user_id_missing", live_launch_action_board)
        self.assertIn("partner_auth_mapping_not_ready", live_launch_action_board)
        self.assertNotIn("@example.com", live_launch_action_board)
        self.assertEqual(live_credential_handoff["handoff_type"], "homepilot_live_credential_handoff")
        self.assertEqual(live_credential_handoff["summary"]["task_count"], 10)
        self.assertEqual(live_credential_handoff["secret_scan"]["status"], "pass")
        self.assertTrue(live_credential_handoff["guardrails"]["env_var_names_only"])
        self.assertIn("HomePilot Live Credential Handoff", live_credential_markdown)
        self.assertIn("HOMEPILOT_SUPABASE_URL", live_credential_checklist)
        self.assertIn("HOMEPILOT_SUPABASE_SERVICE_KEY", live_secret_channel_contract)
        self.assertNotIn("@example.com", live_credential_markdown + live_credential_checklist + live_secret_channel_contract)
        self.assertNotIn("service_role=", live_credential_markdown + live_credential_checklist + live_secret_channel_contract)
        self.assertEqual(live_proof_plan["status"], "blocked_until_live_inputs")
        self.assertEqual(live_proof_plan["secret_scan"]["status"], "pass")
        self.assertEqual(live_proof_plan["plan_validation"]["status"], "pass")
        self.assertFalse(live_proof_plan["summary"]["production_verified"])
        self.assertIn("HomePilot Live Proof Execution Plan", live_proof_markdown)
        self.assertIn("Plan Validation", live_proof_markdown)
        self.assertIn("stale_live_readiness_not_reused: pass", live_proof_markdown)
        self.assertIn("homepilot_production_cutover.py --live", live_proof_markdown)
        self.assertIn("schema_verification", live_proof_evidence_map)
        self.assertIn("customer_access_verification", live_proof_evidence_map)
        self.assertIn("HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof", live_proof_commands)
        self.assertNotIn("service_role=", live_proof_markdown + live_proof_evidence_map + live_proof_commands)
        live_acceptance_by_key = {row["key"]: row for row in live_proof_acceptance["criteria"]}
        self.assertEqual(live_proof_acceptance["status"], "acceptance_criteria_ready_live_evidence_blocked")
        self.assertEqual(live_proof_acceptance["secret_scan"]["status"], "pass")
        self.assertEqual(live_proof_acceptance["summary"]["criterion_count"], 12)
        self.assertFalse(live_proof_acceptance["summary"]["production_verified"])
        self.assertEqual(live_acceptance_by_key["live_proof_plan_self_validated"]["status"], "pass")
        self.assertEqual(live_acceptance_by_key["customer_access_verified"]["status"], "blocked")
        self.assertEqual(live_acceptance_by_key["production_proof_gate_verified"]["status"], "blocked")
        live_proof_cockpit = market_readiness["live_proof_cockpit"]
        live_proof_cockpit_blocker_keys = {row["key"] for row in live_proof_cockpit["blockers"]}
        self.assertEqual(live_proof_cockpit["summary"]["criterion_count"], 12)
        self.assertFalse(live_proof_cockpit["summary"]["production_verified"])
        self.assertEqual(live_proof_cockpit["summary"]["production_verified_label"], "production_verified=false")
        self.assertIn("customer_access_verified", live_proof_cockpit_blocker_keys)
        self.assertIn("HomePilot Live Proof Acceptance Matrix", live_proof_acceptance_markdown)
        self.assertIn("Customer signoff cannot override failed schema, RLS, or customer-access proof", live_proof_acceptance_markdown)
        self.assertIn("customer_access_verified", live_proof_acceptance_csv)
        self.assertNotIn("service_role=", live_proof_acceptance_markdown + live_proof_acceptance_csv)
        live_vault_by_key = {row["key"]: row for row in live_proof_vault["evidence_rows"]}
        self.assertEqual(live_proof_vault["status"], "live_proof_blocked")
        self.assertEqual(live_proof_vault["secret_scan"]["status"], "pass")
        self.assertFalse(live_proof_vault["summary"]["production_verified"])
        self.assertEqual(live_proof_vault["summary"]["production_verified_label"], "production_verified=false")
        self.assertEqual(live_vault_by_key["live_proof_execution_plan"]["current_status"], "pass")
        self.assertEqual(live_vault_by_key["live_proof_acceptance_matrix"]["current_status"], "pass")
        self.assertEqual(live_vault_by_key["customer_access_report"]["current_status"], "blocked")
        self.assertEqual(live_vault_by_key["production_proof_gate"]["current_status"], "blocked")
        self.assertIn("HomePilot Live Proof Evidence Vault", live_proof_vault_markdown)
        self.assertIn("schema_verification_report", live_proof_archive_index)
        self.assertIn("customer_access_report", live_proof_archive_index)
        self.assertIn("production_proof_gate", live_proof_archive_index)
        self.assertNotIn("service_role=", live_proof_vault_markdown + live_proof_archive_index)
        self.assertEqual(outcome_import["status"], "ready_for_customer_review_live_sync_blocked")
        self.assertEqual(outcome_import["sync_decision"], "blocked_until_live_proof")
        self.assertEqual(outcome_import["secret_scan"]["status"], "pass")
        self.assertEqual(outcome_import["summary"]["row_count"], 2)
        self.assertEqual(outcome_import["summary"]["blocker_count"], 0)
        self.assertIn("HomePilot Outcome Import Dry-Run Validation", outcome_import_markdown)
        self.assertIn("review_ready_with_warnings", outcome_import_rows)
        self.assertIn("placeholder_reference", outcome_import_issues)
        self.assertNotIn("@example.com", json.dumps(outcome_import).lower() + outcome_import_markdown.lower() + outcome_import_issues.lower() + outcome_import_rows.lower())
        release_requirement_by_key = {row["key"]: row for row in market_ready_audit["requirements"]}
        self.assertEqual(market_ready_audit["status"], "buyer_review_ready_production_blocked")
        self.assertEqual(market_ready_audit["summary"]["requirement_count"], 21)
        self.assertEqual(
            market_ready_audit["summary"]["buyer_review_passed"],
            market_ready_audit["summary"]["buyer_review_total"],
        )
        self.assertEqual(market_ready_audit["secret_scan"]["status"], "pass")
        self.assertTrue(market_ready_audit["guardrails"]["non_mutating"])
        self.assertTrue(market_ready_audit["guardrails"]["no_supabase_writes"])
        self.assertFalse(market_ready_audit["guardrails"]["secret_values_written"])
        self.assertEqual(release_requirement_by_key["tenant_module_partner_scope"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["data_platform_blueprint"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["module_readiness_matrix"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["outcome_measurement_contract"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["outcome_import_validation"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["live_proof_plan_validated"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["live_proof_acceptance_matrix"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["live_proof_evidence_vault"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["live_credential_handoff"]["status"], "pass")
        self.assertEqual(release_requirement_by_key["live_schema_rls_customer_access"]["status"], "blocked")
        self.assertIn("HomePilot Market-Ready Gap Audit", market_ready_audit_markdown)
        self.assertIn("Outcome import dry-run validation", market_ready_audit_markdown)
        self.assertIn("Live proof execution plan self-validation", market_ready_audit_markdown)
        self.assertIn("live_proof_plan_validated", market_ready_requirements)
        self.assertIn("Live proof customer/IT acceptance matrix", market_ready_audit_markdown)
        self.assertIn("Live proof evidence vault and archive index", market_ready_audit_markdown)
        self.assertIn("Live credential handoff and secret channel contract", market_ready_audit_markdown)
        self.assertIn("Closed-loop outcome measurement contract", market_ready_audit_markdown)
        self.assertIn("Shared data platform blueprint", market_ready_audit_markdown)
        self.assertIn("live_proof_acceptance_matrix", market_ready_requirements)
        self.assertIn("live_proof_evidence_vault", market_ready_requirements)
        self.assertIn("live_credential_handoff", market_ready_requirements)
        self.assertIn("outcome_measurement_contract", market_ready_requirements)
        self.assertIn("outcome_import_validation", market_ready_requirements)
        self.assertIn("data_platform_blueprint", market_ready_requirements)
        self.assertIn("module_readiness_matrix", market_ready_requirements)
        self.assertIn("live_schema_rls_customer_access", market_ready_requirements)
        self.assertNotIn("@example.com", market_ready_audit_markdown)
        self.assertEqual(daw_walkthrough["status"], "buyer_demo_ready")
        self.assertEqual(daw_walkthrough["scenario"]["customer"], "DAW producer network")
        self.assertEqual(len(daw_walkthrough["screen_sequence"]), 11)
        self.assertEqual(len(daw_walkthrough["follow_up_decisions"]), 5)
        self.assertIn("INTELLIGENCE_LAB.md", json.dumps(daw_walkthrough))
        self.assertIn("OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md", json.dumps(daw_walkthrough))
        self.assertIn("OPEN_INTELLIGENCE_DECISION_MATRIX.csv", json.dumps(daw_walkthrough))
        self.assertIn("Boardroom decisions cockpit", daw_walkthrough["screen_sequence"][4]["operator_action"])
        self.assertIn("HomePilot DAW Boardroom Demo Walkthrough", daw_walkthrough_markdown)
        self.assertIn("Open Intelligence decisions", daw_walkthrough_markdown)
        self.assertIn("dashboard/index.html", daw_demo_checklist)
        self.assertIn("dashboard/index.html#intelligence", daw_demo_checklist)
        self.assertIn("Open Intelligence decisions", daw_demo_checklist)
        self.assertIn("Boardroom decisions cockpit", daw_demo_checklist)
        self.assertIn("OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md", daw_demo_checklist)
        self.assertIn("OPEN_INTELLIGENCE_DECISION_MATRIX.csv", daw_demo_checklist)
        self.assertIn("five decision-ready questions", daw_demo_checklist)
        self.assertIn("DAW_BOARDROOM_DEMO_WALKTHROUGH.md", checklist)
        self.assertIn("DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md", checklist)
        self.assertEqual(daw_control_room["status"], "buyer_review_control_ready")
        self.assertEqual(daw_control_room["first_wave_decision"], "blocked_until_customer_inputs_and_live_proof")
        self.assertEqual(daw_control_room["summary"]["launch_lanes"], 6)
        self.assertEqual(daw_control_room["summary"]["action_items"], 7)
        self.assertEqual(daw_control_room["scenario"]["expected_partner_renovators"], 10)
        self.assertTrue(daw_control_room["guardrails"]["live_proof_required_before_first_wave"])
        self.assertIn("HomePilot DAW First Campaign Control Room", daw_control_room_markdown)
        self.assertIn("Partner Wave Plan", daw_control_room_markdown)
        self.assertIn("campaign_compliance", daw_action_board)
        self.assertIn("LIVE_LAUNCH_REQUEST.md", daw_action_board)
        self.assertEqual(customer_acceptance["status"], "buyer_review_ready")
        self.assertEqual(customer_acceptance["stage_statuses"]["buyer_review"], "pass")
        self.assertEqual(customer_acceptance["stage_statuses"]["live_launch"], "blocked")
        self.assertEqual(customer_acceptance["stage_statuses"]["production_rollout"], "blocked")
        self.assertEqual(customer_rollout["status"], "buyer_review_ready")
        self.assertEqual(customer_rollout["stage_statuses"]["buyer_review"], "pass")
        self.assertEqual(customer_rollout["stage_statuses"]["production_rollout"], "blocked")
        self.assertEqual(first_campaign_launch["status"], "first_campaign_inputs_required")
        self.assertEqual(first_campaign_launch["launch_decision"], "blocked_until_customer_inputs_and_live_proof")
        self.assertEqual(first_campaign_launch["summary"]["input_requirements"], 10)
        self.assertEqual(first_campaign_launch["summary"]["go_no_go_gates"], 6)
        self.assertTrue(first_campaign_launch["guardrails"]["message_claims_require_customer_approval"])
        self.assertIn("Partner renovator roster", first_campaign_checklist)
        self.assertIn("First-wave launch decision", first_campaign_checklist)
        self.assertEqual(customer_input_templates["status"], "ready_for_customer_input")
        self.assertEqual(customer_input_templates["summary"]["template_count"], 6)
        self.assertTrue(customer_input_templates["guardrails"]["templates_are_not_customer_approval"])
        self.assertIn("secret://daw/partner/renotec-antwerp/contact", partner_roster_template)
        self.assertIn("do not include raw personal contact data", suppression_list_template)
        self.assertEqual(first_campaign_input_validation["status"], "action_required")
        self.assertEqual(first_campaign_input_validation["first_wave_decision"], "blocked_until_customer_input_fixes")
        self.assertIn("expected_partner_count_missing", first_campaign_input_issues)
        self.assertIn("live_proof_missing", first_campaign_input_issues)
        self.assertEqual(first_campaign_import_plan["status"], "blocked_until_customer_input_fixes")
        self.assertEqual(first_campaign_import_plan["import_decision"], "do_not_import_customer_inputs_incomplete")
        self.assertTrue(first_campaign_import_plan["guardrails"]["no_database_writes"])
        self.assertIn("do_not_import_customer_inputs_incomplete", first_campaign_staging_rows)
        self.assertEqual(first_wave_launch_gate["launch_decision"], "blocked_until_customer_inputs_and_staging_review")
        self.assertFalse(first_wave_launch_gate["launch_authorized"])
        self.assertIn("customer_inputs", first_wave_launch_gate_checklist)
        self.assertEqual(first_wave_database_handoff["status"], "blocked_until_first_wave_launch_authorized")
        self.assertEqual(first_wave_database_handoff["sql_mode"], "comment_only_blocked_gate")
        self.assertFalse(first_wave_database_handoff["launch_authorized"])
        self.assertEqual(first_wave_database_handoff["summary"]["executable_statement_count"], 0)
        self.assertTrue(first_wave_database_handoff["guardrails"]["no_executable_sql_when_blocked"])
        self.assertFalse(first_wave_database_handoff["guardrails"]["raw_contact_values_written"])
        self.assertFalse(first_wave_database_handoff["guardrails"]["secret_values_written"])
        self.assertIn("HomePilot First Wave Database Handoff", first_wave_database_handoff_markdown)
        self.assertIn("launch_authorized", first_wave_database_handoff_checklist)
        self.assertIn("blocked_until_launch_authorized", first_wave_database_review_rows)
        self.assertIn("No executable DML is generated", first_wave_database_review_sql)
        self.assertNotIn("insert into public.", first_wave_database_review_sql.lower())
        self.assertEqual(partner_auth_mapping["status"], "mapping_required")
        self.assertEqual(partner_auth_mapping["summary"]["expected_partner_count"], 10)
        self.assertEqual(partner_auth_mapping["summary"]["mapped_partner_count"], 0)
        self.assertFalse(partner_auth_mapping["guardrails"]["raw_contact_values_written"])
        self.assertIn("HomePilot Partner Auth Mapping", partner_auth_mapping_markdown)
        self.assertIn("supabase_user_id", partner_auth_mapping_template)
        self.assertIn("supabase_user_id_missing", partner_auth_mapping_issues)
        self.assertIn("No executable membership SQL is generated", partner_membership_review_sql)
        self.assertNotIn("insert into public.homepilot_memberships", partner_membership_review_sql.lower())
        self.assertEqual(partner_access_reconciliation["status"], "blocked_until_partner_auth_mapping")
        self.assertFalse(partner_access_reconciliation["production_ready"])
        self.assertEqual(partner_access_reconciliation["summary"]["expected_partner_count"], 10)
        self.assertIn("HomePilot Partner Access Reconciliation", partner_access_reconciliation_markdown)
        self.assertIn("partner_auth_mapping_not_ready", partner_access_reconciliation_issues)
        self.assertIn("renotec-antwerp", partner_access_reconciliation_matrix)
        self.assertEqual(example_inputs["status"], "synthetic_example_ready")
        self.assertEqual(example_inputs["summary"]["partner_count"], 10)
        self.assertTrue(example_inputs["guardrails"]["synthetic_example_only"])
        self.assertIn("secret://example/daw/partner/daw-partner-01/contact", example_partner_roster)
        self.assertEqual(example_validation["status"], "customer_inputs_ready")
        self.assertEqual(example_validation["first_wave_decision"], "blocked_until_live_proof")
        self.assertEqual(example_validation["summary"]["partner_count"], 10)
        self.assertEqual(example_validation["summary"]["blockers"], 1)
        self.assertIn("live_proof_missing", example_issues)
        self.assertNotIn("expected_partner_count_missing", example_issues)
        self.assertEqual(example_import_plan["status"], "staging_plan_ready_import_blocked")
        self.assertEqual(example_import_plan["summary"]["campaign_records"], 10)
        self.assertIn("homepilot_campaigns", example_staging_rows)
        self.assertNotIn("secret://example", json.dumps(example_import_plan))
        self.assertEqual(example_launch_gate["launch_decision"], "blocked_until_live_proof_and_customer_go_no_go")
        self.assertEqual(example_launch_gate["summary"]["campaign_records"], 10)
        self.assertIn("customer_go_no_go", example_launch_gate_checklist)
        self.assertIn("EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md", checklist)
        self.assertIn("FIRST_WAVE_LAUNCH_GATE.md", checklist)
        self.assertEqual(procurement_review["status"], "buyer_review_ready")
        self.assertTrue(procurement_review["guardrails"]["production_requires_live_proof"])
        self.assertEqual(support_sla["status"], "buyer_review_support_ready")
        self.assertTrue(support_sla["guardrails"]["production_requires_live_proof"])
        self.assertEqual(customer_pilot["status"], "buyer_review_proposal_ready")
        self.assertTrue(customer_pilot["guardrails"]["pricing_requires_customer_agreement"])
        self.assertEqual(customer_training["status"], "buyer_review_training_ready")
        self.assertTrue(customer_training["guardrails"]["production_requires_live_proof"])
        self.assertEqual(value_realization["status"], "buyer_review_value_ready")
        self.assertTrue(value_realization["guardrails"]["tenant_private_value_metrics"])
        self.assertEqual(outcome_contract["status"], "buyer_review_ready_live_outcome_sync_blocked")
        self.assertEqual(outcome_contract["secret_scan"]["status"], "pass")
        self.assertFalse(outcome_contract["summary"]["production_verified"])
        self.assertIn("won_project", outcome_contract["summary"]["allowed_outcome_stages"])
        self.assertTrue(outcome_contract["guardrails"]["no_crm_writes"])
        self.assertTrue(outcome_contract["guardrails"]["no_supabase_writes"])
        self.assertIn("HomePilot Outcome Measurement Contract", outcome_markdown)
        self.assertIn("outcome_stage", outcome_schema)
        self.assertIn("crm://redacted", outcome_template)
        self.assertIn("live_access_proven", outcome_checklist)
        self.assertNotIn("@example.com", outcome_markdown + outcome_schema + outcome_template + outcome_checklist)
        self.assertEqual(module_expansion["status"], "buyer_review_expansion_ready")
        self.assertEqual(len(module_expansion["modules"]), 7)
        module_readiness_by_key = {row["module_key"]: row for row in module_readiness["modules"]}
        self.assertEqual(module_readiness["status"], "buyer_review_ready_live_proof_required")
        self.assertEqual(module_readiness["secret_scan"]["status"], "pass")
        self.assertEqual(module_readiness["summary"]["module_count"], 7)
        self.assertEqual(module_readiness["summary"]["buyer_ready_count"], 7)
        self.assertEqual(module_readiness["summary"]["production_ready_count"], 0)
        self.assertEqual(module_readiness["summary"]["production_verified_label"], "production_verified=false")
        self.assertTrue(module_readiness["guardrails"]["tenant_id_required"])
        self.assertTrue(module_readiness["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertTrue(module_readiness_by_key["windowpilot"]["enabled_in_current_customer_scope"])
        self.assertFalse(module_readiness_by_key["facadepilot"]["enabled_in_current_customer_scope"])
        self.assertIn("HomePilot Module Readiness Matrix", module_readiness_markdown)
        self.assertIn("WindowPilot", module_readiness_markdown)
        self.assertIn("drivewaypilot", module_readiness_csv)
        self.assertIn("facade_opportunity_score", module_metric_coverage)
        self.assertNotIn("@example.com", module_readiness_markdown + module_readiness_csv + module_metric_coverage)
        self.assertEqual(public_register["status"], "buyer_review_public_data_ready")
        self.assertEqual(len(public_register["sources"]), 7)
        self.assertTrue(public_register["guardrails"]["contact_scraping_blocked_by_default"])
        self.assertEqual(public_data_intake["status"], "approval_required")
        self.assertEqual(public_data_intake["production_import_decision"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertTrue(public_data_intake["guardrails"]["scraped_contact_data_blocked"])
        self.assertIn("OpenStreetMap", public_data_approval_checklist)
        self.assertIn("legal_review_required", public_data_approval_checklist)
        self.assertEqual(public_data_reconciliation["status"], "blocked_until_dataset_approvals_and_live_proof")
        self.assertFalse(public_data_reconciliation["production_import_ready"])
        self.assertEqual(public_data_reconciliation["summary"]["registered_source_count"], 7)
        self.assertEqual(public_data_reconciliation["summary"]["approved_source_count"], 0)
        self.assertFalse(public_data_reconciliation["summary"]["first_wave_public_data_required"])
        self.assertEqual(public_data_reconciliation["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Public Data Reconciliation", public_data_reconciliation_markdown)
        self.assertIn("BeSt Addresses", public_data_reconciliation_matrix)
        self.assertIn("public_data_import_not_approved", public_data_reconciliation_issues)
        self.assertEqual(customer_signoff_reconciliation["status"], "blocked_until_customer_signoff_and_live_proof")
        self.assertFalse(customer_signoff_reconciliation["live_launch_ready"])
        self.assertFalse(customer_signoff_reconciliation["production_signoff_ready"])
        self.assertEqual(customer_signoff_reconciliation["summary"]["decision_count"], 10)
        self.assertEqual(customer_signoff_reconciliation["summary"]["signed_decision_count"], 0)
        self.assertEqual(customer_signoff_reconciliation["secret_scan"]["status"], "pass")
        self.assertIn("HomePilot Customer Signoff Reconciliation", customer_signoff_reconciliation_markdown)
        self.assertIn("buyer_review_acceptance", customer_signoff_reconciliation_matrix)
        self.assertIn("first_wave_go_no_go_missing", customer_signoff_reconciliation_issues)
        self.assertIn("HomePilot Customer Signoff Intake", customer_signoff_intake)
        self.assertIn("technical proof", customer_signoff_intake.lower())
        self.assertIn("technical_proof_required", customer_signoff_template)
        self.assertEqual(customer_view_catalog["status"], "buyer_review_ready_live_access_blocked")
        self.assertEqual(customer_view_catalog["secret_scan"]["status"], "pass")
        self.assertFalse(customer_view_catalog["summary"]["live_access_ready"])
        self.assertIn("HomePilot Customer View Catalog", customer_view_catalog_markdown)
        self.assertIn("partner_renovator", customer_view_matrix)
        self.assertIn("assigned-record view", customer_view_matrix)
        self.assertEqual(data_platform_blueprint["status"], "buyer_review_ready_live_proof_required")
        self.assertEqual(data_platform_blueprint["secret_scan"]["status"], "pass")
        self.assertFalse(data_platform_blueprint["summary"]["production_verified"])
        self.assertEqual(data_platform_blueprint["summary"]["production_verified_label"], "production_verified=false")
        self.assertTrue(data_platform_blueprint["guardrails"]["tenant_id_required"])
        self.assertTrue(data_platform_blueprint["guardrails"]["partner_id_limits_partner_visibility"])
        self.assertIn("HomePilot Data Platform Blueprint", data_platform_blueprint_markdown)
        self.assertIn("DrivewayPilot", data_platform_blueprint_markdown)
        self.assertIn("homepilot_campaign_targets", data_platform_blueprint_markdown)
        self.assertIn("partner_renovator", data_platform_scope_matrix)
        self.assertNotIn("@example.com", data_platform_blueprint_markdown + data_platform_scope_matrix)
        self.assertEqual(market_readiness["portable_data_room"]["status"], "pass")
        self.assertEqual(portable_manifest["status"], "pass")
        self.assertEqual(portable_manifest["link_mode"], "relative")
        self.assertFalse(portable_manifest["absolute_links_written"])
        self.assertFalse(portable_manifest["source_paths_written"])
        self.assertGreater(portable_manifest["local_path_redaction_count"], 0)
        self.assertTrue(any(entry["label"] == "Access lens proof matrix" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Open Intelligence model card" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Open Intelligence boardroom brief" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Open Intelligence decision matrix" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome measurement contract" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome event schema" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome sync template" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome reconciliation checklist" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome import dry-run validation" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome import issues" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Outcome import review rows" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Marketing impact planner" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Open Intelligence measurement loop" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Open Intelligence production gate" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Open Intelligence production gates CSV" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Open Intelligence production runbook" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof execution plan" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof evidence map" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof command script" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof acceptance matrix" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof acceptance CSV" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof evidence vault" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Live proof archive index" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Data platform blueprint" for entry in portable_manifest["entries"]))
        self.assertTrue(any(entry["label"] == "Data platform scope matrix" for entry in portable_manifest["entries"]))
        self.assertNotIn("file://", portable_html)
        self.assertIn("Customer-shareable evidence room", portable_html)
        self.assertIn("DATA_ROOM_MANIFEST.json", portable_zip_names)
        self.assertIn("index.html", portable_zip_names)
        self.assertTrue(any(name.startswith("files/") for name in portable_zip_names))
        self.assertTrue(any("public-data-source-register" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-source-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("blocked-data-register" in name for name in portable_zip_names))
        self.assertTrue(any("attribution-requirements" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-production-intake" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-approval-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-reconciliation" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-reconciliation-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("public-data-reconciliation-issues" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-reconciliation" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-reconciliation-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-reconciliation-issues" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-intake" in name for name in portable_zip_names))
        self.assertTrue(any("customer-signoff-evidence-template" in name for name in portable_zip_names))
        self.assertTrue(any("customer-view-catalog" in name for name in portable_zip_names))
        self.assertTrue(any("customer-view-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("data-platform-blueprint" in name for name in portable_zip_names))
        self.assertTrue(any("data-platform-scope-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("access-lens-proof-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("open-intelligence-model-card" in name for name in portable_zip_names))
        self.assertTrue(any("open-intelligence-boardroom-brief" in name for name in portable_zip_names))
        self.assertTrue(any("open-intelligence-decision-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("marketing-impact-planner" in name for name in portable_zip_names))
        self.assertTrue(any("open-intelligence-measurement-loop" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-measurement-contract" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-event-schema" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-sync-template" in name for name in portable_zip_names))
        self.assertTrue(any("outcome-reconciliation-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-execution-plan" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-evidence-map" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-command-script" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-acceptance-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("live-proof-acceptance-csv" in name for name in portable_zip_names))
        self.assertIn("HomePilot Live Proof Acceptance Matrix", portable_zip_text)
        self.assertIn("customer_access_verified", portable_zip_text)
        self.assertIn("HomePilot Data Platform Blueprint", portable_zip_text)
        self.assertIn("tenant -> modules -> campaigns -> properties -> assessments -> interactions", portable_zip_text)
        self.assertIn("partner_renovator", portable_zip_text)
        self.assertIn("HomePilot Open Intelligence", portable_zip_text)
        self.assertIn("HomePilot Open Intelligence Boardroom Brief", portable_zip_text)
        self.assertIn("where_to_focus_first_wave", portable_zip_text)
        self.assertIn("intelligence_beyond_identity", portable_zip_text)
        self.assertIn("HomePilot Outcome Measurement Contract", portable_zip_text)
        self.assertIn("outcome_stage", portable_zip_text)
        self.assertIn("crm://redacted", portable_zip_text)
        self.assertTrue(any("daw-boardroom-demo-walkthrough" in name for name in portable_zip_names))
        self.assertTrue(any("intelligence-lab-report" in name for name in portable_zip_names))
        self.assertTrue(any("intelligence-lab-json-evidence" in name for name in portable_zip_names))
        self.assertTrue(any("live-launch-control-room" in name for name in portable_zip_names))
        self.assertTrue(any("live-launch-action-board" in name for name in portable_zip_names))
        self.assertTrue(any("market-ready-gap-audit" in name for name in portable_zip_names))
        self.assertTrue(any("market-ready-requirements-csv" in name for name in portable_zip_names))
        self.assertTrue(any("production-cutover-report" in name for name in portable_zip_names))
        self.assertTrue(any("production-cutover-runbook" in name for name in portable_zip_names))
        self.assertTrue(any("daw-demo-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("daw-first-campaign-control-room" in name for name in portable_zip_names))
        self.assertTrue(any("daw-first-campaign-action-board" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-launch-intake" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-launch-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("customer-input-templates" in name for name in portable_zip_names))
        self.assertTrue(any("partner-roster-template" in name for name in portable_zip_names))
        self.assertTrue(any("suppression-list-template" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-input-validation" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-input-issues" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-import-plan" in name for name in portable_zip_names))
        self.assertTrue(any("first-campaign-staging-rows" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-launch-gate" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-launch-gate-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-handoff" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-handoff-checklist" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-review-rows" in name for name in portable_zip_names))
        self.assertTrue(any("first-wave-database-review-sql" in name for name in portable_zip_names))
        self.assertTrue(any("partner-auth-mapping" in name for name in portable_zip_names))
        self.assertTrue(any("partner-auth-mapping-template" in name for name in portable_zip_names))
        self.assertTrue(any("partner-auth-mapping-issues" in name for name in portable_zip_names))
        self.assertTrue(any("partner-membership-review-sql" in name for name in portable_zip_names))
        self.assertTrue(any("partner-access-reconciliation" in name for name in portable_zip_names))
        self.assertTrue(any("partner-access-reconciliation-matrix" in name for name in portable_zip_names))
        self.assertTrue(any("partner-access-reconciliation-issues" in name for name in portable_zip_names))
        self.assertTrue(any("example-completed-customer-inputs" in name for name in portable_zip_names))
        self.assertTrue(any("example-partner-roster" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-input-validation" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-input-issues" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-import-plan" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-campaign-staging-rows" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-wave-launch-gate" in name for name in portable_zip_names))
        self.assertTrue(any("example-first-wave-launch-gate-checklist" in name for name in portable_zip_names))
        self.assertIn("HomePilot Intelligence Lab", portable_zip_text)
        self.assertIn("HomePilot Live Launch Control Room", portable_zip_text)
        self.assertIn("HomePilot Live Proof Execution Plan", portable_zip_text)
        self.assertIn("HOMEPILOT_LIVE_PROOF_CONFIRM", portable_zip_text)
        self.assertIn("HomePilot Market-Ready Gap Audit", portable_zip_text)
        self.assertIn("HomePilot Outcome Import Dry-Run Validation", portable_zip_text)
        self.assertIn("HomePilot Partner Access Reconciliation", portable_zip_text)
        self.assertIn("HomePilot Public Data Reconciliation", portable_zip_text)
        self.assertIn("HomePilot Customer Signoff Reconciliation", portable_zip_text)
        self.assertIn("HomePilot Customer Signoff Intake", portable_zip_text)
        self.assertIn("HomePilot Production Cutover", portable_zip_text)
        self.assertIn("Production verified: false", portable_zip_text)
        self.assertIn("HomePilot First Wave Database Handoff", portable_zip_text)
        self.assertIn("HomePilot Partner Auth Mapping", portable_zip_text)
        self.assertIn("No executable DML is generated", portable_zip_text)
        self.assertIn("No executable membership SQL is generated", portable_zip_text)
        self.assertIn("buyer_review_ready_production_blocked", portable_zip_text)
        self.assertIn("live_schema_rls_customer_access", portable_zip_text)
        self.assertIn("production_verified=true", portable_zip_text)
        self.assertIn("contacted_count", portable_zip_text)
        self.assertIn("forbidden_claim_count", portable_zip_text)
        self.assertNotIn("/private/tmp", portable_zip_text)
        self.assertNotIn("file:///private/tmp", portable_zip_text)
        self.assertIn("ops_status", index["generated_evidence"])
        self.assertIn("production_proof", index["generated_evidence"])
        self.assertIn("production_proof_markdown", index["generated_evidence"])
        self.assertIn("production_cutover_report", index["generated_evidence"])
        self.assertIn("production_cutover_runbook", index["generated_evidence"])
        self.assertIn("sql_apply_plan", index["generated_evidence"])
        self.assertIn("sql_apply_runbook", index["generated_evidence"])
        self.assertIn("apply_sql", index["generated_evidence"])
        self.assertIn("live_launch_control_room", index["generated_evidence"])
        self.assertIn("live_launch_control_room_markdown", index["generated_evidence"])
        self.assertIn("live_launch_action_board", index["generated_evidence"])
        self.assertIn("live_credential_handoff", index["generated_evidence"])
        self.assertIn("live_credential_handoff_markdown", index["generated_evidence"])
        self.assertIn("live_credential_handoff_checklist", index["generated_evidence"])
        self.assertIn("live_secret_channel_contract", index["generated_evidence"])
        self.assertIn("market_ready_audit", index["generated_evidence"])
        self.assertIn("market_ready_audit_markdown", index["generated_evidence"])
        self.assertIn("market_ready_requirements", index["generated_evidence"])
        self.assertIn("post_apply_verification_sql", index["generated_evidence"])
        self.assertIn("market_readiness_scorecard", index["generated_evidence"])
        self.assertIn("market_readiness_markdown", index["generated_evidence"])
        self.assertIn("market_readiness_html", index["generated_evidence"])
        self.assertIn("boardroom_data_room_index", index["generated_evidence"])
        self.assertIn("market_readiness_actions", index["generated_evidence"])
        self.assertIn("stakeholder_views", index["generated_evidence"])
        self.assertIn("daw_boardroom_demo_walkthrough", index["generated_evidence"])
        self.assertIn("daw_boardroom_demo_walkthrough_markdown", index["generated_evidence"])
        self.assertIn("daw_demo_checklist", index["generated_evidence"])
        self.assertIn("daw_first_campaign_control_room", index["generated_evidence"])
        self.assertIn("daw_first_campaign_control_room_markdown", index["generated_evidence"])
        self.assertIn("daw_first_campaign_action_board", index["generated_evidence"])
        self.assertIn("customer_acceptance_plan", index["generated_evidence"])
        self.assertIn("customer_acceptance_plan_markdown", index["generated_evidence"])
        self.assertIn("acceptance_checklist", index["generated_evidence"])
        self.assertIn("customer_rollout_plan", index["generated_evidence"])
        self.assertIn("customer_rollout_plan_markdown", index["generated_evidence"])
        self.assertIn("rollout_workstreams", index["generated_evidence"])
        self.assertIn("first_campaign_launch_intake", index["generated_evidence"])
        self.assertIn("first_campaign_launch_intake_markdown", index["generated_evidence"])
        self.assertIn("first_campaign_launch_checklist", index["generated_evidence"])
        self.assertIn("customer_input_templates", index["generated_evidence"])
        self.assertIn("customer_input_templates_markdown", index["generated_evidence"])
        self.assertIn("partner_roster_template", index["generated_evidence"])
        self.assertIn("territory_assignment_template", index["generated_evidence"])
        self.assertIn("property_source_template", index["generated_evidence"])
        self.assertIn("suppression_list_template", index["generated_evidence"])
        self.assertIn("message_approval_template", index["generated_evidence"])
        self.assertIn("partner_capacity_template", index["generated_evidence"])
        self.assertIn("first_campaign_input_validation", index["generated_evidence"])
        self.assertIn("first_campaign_input_validation_markdown", index["generated_evidence"])
        self.assertIn("first_campaign_input_issues", index["generated_evidence"])
        self.assertIn("first_campaign_import_plan", index["generated_evidence"])
        self.assertIn("first_campaign_import_plan_markdown", index["generated_evidence"])
        self.assertIn("first_campaign_staging_rows", index["generated_evidence"])
        self.assertIn("first_wave_launch_gate", index["generated_evidence"])
        self.assertIn("first_wave_launch_gate_markdown", index["generated_evidence"])
        self.assertIn("first_wave_launch_gate_checklist", index["generated_evidence"])
        self.assertIn("first_wave_database_handoff", index["generated_evidence"])
        self.assertIn("first_wave_database_handoff_markdown", index["generated_evidence"])
        self.assertIn("first_wave_database_handoff_checklist", index["generated_evidence"])
        self.assertIn("first_wave_database_review_rows", index["generated_evidence"])
        self.assertIn("first_wave_database_review_sql", index["generated_evidence"])
        self.assertIn("partner_auth_mapping", index["generated_evidence"])
        self.assertIn("partner_auth_mapping_markdown", index["generated_evidence"])
        self.assertIn("partner_auth_mapping_template", index["generated_evidence"])
        self.assertIn("partner_auth_mapping_rows", index["generated_evidence"])
        self.assertIn("partner_auth_mapping_issues", index["generated_evidence"])
        self.assertIn("partner_membership_review_sql", index["generated_evidence"])
        self.assertIn("partner_access_reconciliation", index["generated_evidence"])
        self.assertIn("partner_access_reconciliation_markdown", index["generated_evidence"])
        self.assertIn("partner_access_reconciliation_matrix", index["generated_evidence"])
        self.assertIn("partner_access_reconciliation_issues", index["generated_evidence"])
        self.assertIn("example_completed_customer_inputs", index["generated_evidence"])
        self.assertIn("example_completed_customer_inputs_markdown", index["generated_evidence"])
        self.assertIn("example_completed_partner_roster", index["generated_evidence"])
        self.assertIn("example_first_campaign_input_validation", index["generated_evidence"])
        self.assertIn("example_first_campaign_input_validation_markdown", index["generated_evidence"])
        self.assertIn("example_first_campaign_input_issues", index["generated_evidence"])
        self.assertIn("example_first_campaign_import_plan", index["generated_evidence"])
        self.assertIn("example_first_campaign_import_plan_markdown", index["generated_evidence"])
        self.assertIn("example_first_campaign_staging_rows", index["generated_evidence"])
        self.assertIn("example_first_wave_launch_gate", index["generated_evidence"])
        self.assertIn("example_first_wave_launch_gate_markdown", index["generated_evidence"])
        self.assertIn("example_first_wave_launch_gate_checklist", index["generated_evidence"])
        self.assertIn("procurement_review", index["generated_evidence"])
        self.assertIn("procurement_review_markdown", index["generated_evidence"])
        self.assertIn("security_questionnaire", index["generated_evidence"])
        self.assertIn("procurement_risk_register", index["generated_evidence"])
        self.assertIn("support_sla_plan", index["generated_evidence"])
        self.assertIn("support_sla_plan_markdown", index["generated_evidence"])
        self.assertIn("support_escalation_matrix", index["generated_evidence"])
        self.assertIn("incident_response_playbook", index["generated_evidence"])
        self.assertIn("customer_pilot_proposal", index["generated_evidence"])
        self.assertIn("customer_pilot_proposal_markdown", index["generated_evidence"])
        self.assertIn("pilot_scope_checklist", index["generated_evidence"])
        self.assertIn("commercial_assumptions", index["generated_evidence"])
        self.assertIn("customer_training_plan", index["generated_evidence"])
        self.assertIn("customer_training_guide", index["generated_evidence"])
        self.assertIn("training_session_plan", index["generated_evidence"])
        self.assertIn("role_cheatsheet", index["generated_evidence"])
        self.assertIn("value_realization_plan", index["generated_evidence"])
        self.assertIn("value_realization_plan_markdown", index["generated_evidence"])
        self.assertIn("value_realization_metrics", index["generated_evidence"])
        self.assertIn("executive_decision_log", index["generated_evidence"])
        self.assertIn("outcome_measurement_contract", index["generated_evidence"])
        self.assertIn("outcome_measurement_contract_markdown", index["generated_evidence"])
        self.assertIn("outcome_event_schema", index["generated_evidence"])
        self.assertIn("outcome_sync_template", index["generated_evidence"])
        self.assertIn("outcome_reconciliation_checklist", index["generated_evidence"])
        self.assertIn("outcome_import_validation", index["generated_evidence"])
        self.assertIn("outcome_import_validation_markdown", index["generated_evidence"])
        self.assertIn("outcome_import_issues", index["generated_evidence"])
        self.assertIn("outcome_import_review_rows", index["generated_evidence"])
        self.assertIn("module_expansion_plan", index["generated_evidence"])
        self.assertIn("module_expansion_plan_markdown", index["generated_evidence"])
        self.assertIn("module_value_matrix", index["generated_evidence"])
        self.assertIn("expansion_decision_tree", index["generated_evidence"])
        self.assertIn("module_readiness_matrix", index["generated_evidence"])
        self.assertIn("module_readiness_matrix_markdown", index["generated_evidence"])
        self.assertIn("module_readiness_matrix_csv", index["generated_evidence"])
        self.assertIn("module_metric_coverage", index["generated_evidence"])
        self.assertIn("data_platform_blueprint", index["generated_evidence"])
        self.assertIn("data_platform_blueprint_markdown", index["generated_evidence"])
        self.assertIn("data_platform_scope_matrix", index["generated_evidence"])
        self.assertIn("public_data_source_register", index["generated_evidence"])
        self.assertIn("public_data_source_register_markdown", index["generated_evidence"])
        self.assertIn("public_data_source_matrix", index["generated_evidence"])
        self.assertIn("blocked_data_register", index["generated_evidence"])
        self.assertIn("attribution_requirements", index["generated_evidence"])
        self.assertIn("public_data_production_intake", index["generated_evidence"])
        self.assertIn("public_data_production_intake_markdown", index["generated_evidence"])
        self.assertIn("public_data_approval_checklist", index["generated_evidence"])
        self.assertIn("public_data_reconciliation", index["generated_evidence"])
        self.assertIn("public_data_reconciliation_markdown", index["generated_evidence"])
        self.assertIn("public_data_reconciliation_matrix", index["generated_evidence"])
        self.assertIn("public_data_reconciliation_issues", index["generated_evidence"])
        self.assertIn("customer_signoff_reconciliation", index["generated_evidence"])
        self.assertIn("customer_signoff_reconciliation_markdown", index["generated_evidence"])
        self.assertIn("customer_signoff_reconciliation_matrix", index["generated_evidence"])
        self.assertIn("customer_signoff_reconciliation_issues", index["generated_evidence"])
        self.assertIn("customer_signoff_intake_markdown", index["generated_evidence"])
        self.assertIn("customer_signoff_evidence_template", index["generated_evidence"])
        self.assertIn("live_proof_plan", index["generated_evidence"])
        self.assertIn("live_proof_plan_markdown", index["generated_evidence"])
        self.assertIn("live_proof_acceptance", index["generated_evidence"])
        self.assertIn("live_proof_acceptance_markdown", index["generated_evidence"])
        self.assertIn("live_proof_acceptance_csv", index["generated_evidence"])
        self.assertIn("live_proof_evidence_map", index["generated_evidence"])
        self.assertIn("live_proof_commands", index["generated_evidence"])
        self.assertIn("live_proof_evidence_vault", index["generated_evidence"])
        self.assertIn("live_proof_evidence_vault_markdown", index["generated_evidence"])
        self.assertIn("live_proof_archive_index", index["generated_evidence"])
        self.assertIn("portable_data_room_html", index["generated_evidence"])
        self.assertIn("portable_data_room_manifest", index["generated_evidence"])
        self.assertIn("portable_data_room_zip", index["generated_evidence"])
        self.assertTrue(index["referenced_artifacts"]["data_dictionary_exists"])
        self.assertTrue(index["referenced_artifacts"]["api_contract_markdown_exists"])
        self.assertTrue(index["referenced_artifacts"]["processing_register_markdown_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_manifest_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_readme_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_live_config_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_live_loader_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_hosting_manifest_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_hosting_runbook_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_hosting_asset_manifest_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_hosting_cache_policy_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_hosting_deployment_checklist_exists"])
        self.assertTrue(index["referenced_artifacts"]["customer_portal_hosting_rollback_manifest_exists"])
        self.assertTrue(index["referenced_artifacts"]["sales_integration_manifest_exists"])
        self.assertTrue(index["referenced_artifacts"]["sales_integration_runbook_exists"])
        self.assertTrue(index["referenced_artifacts"]["sales_integration_sync_report_exists"])
        self.assertTrue(index["referenced_artifacts"]["sales_integration_sync_runbook_exists"])
        self.assertTrue(index["referenced_artifacts"]["data_vendor_plan_exists"])
        self.assertTrue(index["referenced_artifacts"]["data_vendor_plan_markdown_exists"])
        self.assertTrue(index["referenced_artifacts"]["data_vendor_refresh_report_exists"])
        self.assertTrue(index["referenced_artifacts"]["data_vendor_refresh_runbook_exists"])
        self.assertTrue(index["referenced_artifacts"]["data_vendor_refresh_jobs_exists"])
        self.assertTrue(index["referenced_artifacts"]["data_vendor_refresh_dead_letter_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_manifest_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_readme_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_dashboard_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_open_intelligence_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_open_intelligence_markdown_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_open_intelligence_boardroom_brief_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_open_intelligence_decision_matrix_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_marketing_impact_planner_exists"])
        self.assertTrue(index["referenced_artifacts"]["enterprise_demo_room_measurement_loop_exists"])
        self.assertTrue(index["referenced_artifacts"]["visual_intelligence_exists"])
        self.assertTrue(index["referenced_artifacts"]["visual_intelligence_runbook_exists"])
        self.assertTrue(index["referenced_artifacts"]["visual_intelligence_map_clusters_exists"])
        self.assertTrue(index["referenced_artifacts"]["monitoring_plan_exists"])
        self.assertTrue(index["referenced_artifacts"]["monitoring_runbook_exists"])
        self.assertTrue(index["referenced_artifacts"]["monitoring_alert_matrix_exists"])
        self.assertTrue(index["referenced_artifacts"]["live_launch_request_exists"])
        self.assertTrue(index["referenced_artifacts"]["live_launch_request_markdown_exists"])
        self.assertTrue(index["referenced_artifacts"]["live_launch_checklist_exists"])
        self.assertTrue(index["referenced_artifacts"]["live_launch_env_template_exists"])
        self.assertTrue(index["referenced_artifacts"]["live_launch_request_email_exists"])
        self.assertEqual(index["summary"]["schema_deployment_status"], "pass")
        self.assertIsNone(index["summary"]["schema_verification_status"])
        self.assertIn("Missing live launch report", notes)
        self.assertIn("production_proof", notes)
        self.assertIn("market_readiness_scorecard", notes)
        self.assertIn("processing_register", notes)
        self.assertIn("CUSTOMER_SIGNOFF_RECONCILIATION.md", notes)
        self.assertIn("CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv", notes)
        self.assertIn("MARKET_READINESS_SCORECARD.md", checklist)
        self.assertIn("homepilot_boardroom_data_room.zip", checklist)
        self.assertIn("CUSTOMER_ACCEPTANCE_PLAN.md", checklist)
        self.assertIn("ACCEPTANCE_CHECKLIST.csv", checklist)
        self.assertIn("CUSTOMER_ROLLOUT_PLAN.md", checklist)
        self.assertIn("ROLLOUT_WORKSTREAMS.csv", checklist)
        self.assertIn("CUSTOMER_SIGNOFF_RECONCILIATION.md", checklist)
        self.assertIn("CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv", checklist)
        self.assertIn("PROCUREMENT_SECURITY_REVIEW.md", checklist)
        self.assertIn("SECURITY_QUESTIONNAIRE.csv", checklist)
        self.assertIn("PROCUREMENT_RISK_REGISTER.csv", checklist)
        self.assertIn("SUPPORT_SLA_PLAN.md", checklist)
        self.assertIn("SUPPORT_ESCALATION_MATRIX.csv", checklist)
        self.assertIn("INCIDENT_RESPONSE_PLAYBOOK.md", checklist)
        self.assertIn("CUSTOMER_PILOT_PROPOSAL.md", checklist)
        self.assertIn("PILOT_SCOPE_CHECKLIST.csv", checklist)
        self.assertIn("COMMERCIAL_ASSUMPTIONS.csv", checklist)
        self.assertIn("CUSTOMER_TRAINING_GUIDE.md", checklist)
        self.assertIn("TRAINING_SESSION_PLAN.csv", checklist)
        self.assertIn("ROLE_CHEATSHEET.csv", checklist)
        self.assertIn("CUSTOMER_VALUE_REALIZATION_PLAN.md", checklist)
        self.assertIn("VALUE_REALIZATION_METRICS.csv", checklist)
        self.assertIn("EXECUTIVE_DECISION_LOG.csv", checklist)
        self.assertIn("CUSTOMER_MODULE_EXPANSION_PLAN.md", checklist)
        self.assertIn("MODULE_VALUE_MATRIX.csv", checklist)
        self.assertIn("EXPANSION_DECISION_TREE.csv", checklist)
        self.assertIn("MODULE_READINESS_MATRIX.md", checklist)
        self.assertIn("MODULE_READINESS_MATRIX.csv", checklist)
        self.assertIn("MODULE_METRIC_COVERAGE.csv", checklist)
        self.assertIn("PUBLIC_DATA_SOURCE_REGISTER.md", checklist)
        self.assertIn("PUBLIC_DATA_SOURCE_MATRIX.csv", checklist)
        self.assertIn("BLOCKED_DATA_REGISTER.csv", checklist)
        self.assertIn("ATTRIBUTION_REQUIREMENTS.csv", checklist)
        self.assertIn("BOARDROOM_DATA_ROOM_INDEX.md", checklist)
        self.assertIn("STAKEHOLDER_VIEWS.md", checklist)
        self.assertIn("Production is go only after live readiness is ready", checklist)
        self.assertIn("PRODUCTION_PROOF.md", checklist)
        self.assertIn("SQL_APPLY_PLAN.md", checklist)
        self.assertIn("apply.sql", checklist)
        self.assertIn("post_apply_verification.sql", checklist)
        self.assertIn("LIVE_READINESS.md", checklist)
        self.assertIn("LIVE_LAUNCH_REQUEST.md", checklist)
        self.assertIn("LIVE_LAUNCH_CHECKLIST.csv", checklist)
        self.assertIn("LIVE_LAUNCH_REQUEST_EMAIL.txt", checklist)
        self.assertIn("LIVE_PROOF_EXECUTION_PLAN.md", checklist)
        self.assertIn("LIVE_PROOF_EVIDENCE_MAP.csv", checklist)
        self.assertIn("LIVE_PROOF_COMMANDS.sh", checklist)
        self.assertIn("LIVE_CREDENTIAL_HANDOFF.md", checklist)
        self.assertIn("LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv", checklist)
        self.assertIn("LIVE_SECRET_CHANNEL_CONTRACT.csv", checklist)
        self.assertIn("LIVE_PROOF_EVIDENCE_VAULT.md", checklist)
        self.assertIn("LIVE_PROOF_ARCHIVE_INDEX.csv", checklist)
        self.assertIn("HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof", checklist)
        self.assertIn("live_launch.env.template", checklist)
        self.assertIn("live_cutover.env.template", checklist)
        self.assertIn("homepilot_live_schema_verification.py --live", checklist)
        self.assertIn("ACCOUNT_ACCESS_PLAN.md", checklist)
        self.assertIn("CUSTOMER_ACCESS_VERIFICATION.md", checklist)
        self.assertIn("PORTAL_README.md", checklist)
        self.assertIn("HOSTING_RUNBOOK.md", checklist)
        self.assertIn("deployment_checklist.csv", checklist)
        self.assertIn("INTEGRATION_RUNBOOK.md", checklist)
        self.assertIn("SYNC_RUNBOOK.md", checklist)
        self.assertIn("VISUAL_INTELLIGENCE.md", checklist)
        self.assertIn("map_clusters.csv", checklist)
        self.assertIn("MONITORING_RUNBOOK.md", checklist)
        self.assertIn("alert_matrix.csv", checklist)
        self.assertIn("DATA_VENDOR_PLAN.md", checklist)
        self.assertIn("ENRICHMENT_REFRESH_RUNBOOK.md", checklist)
        self.assertIn("refresh_jobs.csv", checklist)
        self.assertIn("enterprise demo room README/dashboard", checklist)
        self.assertIn("PROCESSING_REGISTER.md", checklist)
        self.assertIn("CUSTOMER_BRIEF.md", checklist)
        self.assertIn("CAMPAIGN_LEARNING.md", checklist)
        self.assertIn("TERRITORY_PLAN.md", checklist)
        self.assertIn("ROI_FORECAST.md", checklist)
        self.assertIn("OPPORTUNITY_DOSSIER.md", checklist)
        self.assertIn("SOURCE_LEDGER.md", checklist)

    def test_production_docs_explain_guarded_live_proof_operator_route(self) -> None:
        docs = {
            "README.md": (HOME_ROOT / "platform" / "README.md").read_text(encoding="utf-8"),
            "PRODUCTION_LAUNCH.md": (HOME_ROOT / "platform" / "PRODUCTION_LAUNCH.md").read_text(
                encoding="utf-8"
            ),
            "PRODUCTION_READINESS.md": (HOME_ROOT / "platform" / "PRODUCTION_READINESS.md").read_text(
                encoding="utf-8"
            ),
        }
        combined = "\n".join(docs.values())

        self.assertIn("homepilot_live_proof_plan.py", docs["README.md"])
        self.assertIn("homepilot_live_proof_plan.py", docs["PRODUCTION_LAUNCH.md"])
        self.assertIn("homepilot_live_proof_plan.py", docs["PRODUCTION_READINESS.md"])
        self.assertIn("LIVE_PROOF_EXECUTION_PLAN.md", combined)
        self.assertIn("LIVE_PROOF_EVIDENCE_MAP.csv", combined)
        self.assertIn("LIVE_PROOF_COMMANDS.sh", combined)
        self.assertIn("HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof", combined)
        self.assertIn("production_verified=true", combined)
        self.assertIn("no secrets or live writes", docs["README.md"])

    def test_ops_status_pack_separates_buyer_readiness_from_production_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = build_readiness_pack(root / "readiness", run_qa=False)
            for gate in readiness["gates"]:
                if gate["name"] == "local_qa":
                    gate["status"] = "pass"
            readiness_path = root / "readiness" / "readiness_report.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            due = build_due_diligence_pack(
                root / "due",
                readiness_report_path=readiness_path,
                modules=["windowpilot"],
            )
            pack = build_ops_status_pack(
                out_dir=root / "ops",
                readiness_report_path=readiness_path,
                due_diligence_report_path=Path(due["paths"]["due_diligence_report"]),
                release_label="ops-test",
                stage="buyer_review",
                env={},
            )
            report = json.loads(Path(pack["paths"]["ops_status"]).read_text(encoding="utf-8"))
            status_page = Path(pack["paths"]["status_page"]).read_text(encoding="utf-8")
            runbook = Path(pack["paths"]["ops_runbook"]).read_text(encoding="utf-8")
        self.assertEqual(pack["status"], "buyer_review_ready")
        self.assertEqual(report["decisions"]["buyer_review"], "go")
        self.assertEqual(report["decisions"]["production"], "no_go")
        self.assertTrue(any("production_verified=true" in blocker for blocker in report["production_blockers"]))
        self.assertIn("HomePilot Operational Status", status_page)
        self.assertIn("configure_live_environment", json.dumps(report["open_actions"]))
        self.assertIn("Standard Cadence", runbook)

    def test_release_audit_requires_passed_live_rls_probe_for_production(self) -> None:
        readiness = {
            "status": "pass",
            "production_verified": False,
            "gates": [{"name": "local_qa", "status": "pass"}],
        }
        due = {
            "status": "local_ready",
            "production_gate": {"verified": False},
            "redaction": {"status": "pass"},
            "source_manifest_summary": {"missing": []},
        }
        launch = {
            "status": "pass",
            "production_verified": True,
            "rls_probe": {"status": "pass"},
            "cleanup": {"status": "ready_for_review"},
        }
        customer_access = {
            "status": "pass",
            "production_verified": True,
            "rls_probe": {"status": "pass"},
        }
        schema_verification = {
            "status": "pass",
            "production_verified": True,
            "contract_status": "pass",
            "live_status": "pass",
        }
        live_readiness = {
            "status": "ready",
            "ready_to_run_live_cutover": True,
            "guardrails": {"secrets_written": False},
        }
        missing_live_readiness = build_release_audit(
            readiness=readiness,
            due_diligence=due,
            launch=launch,
            customer_access=customer_access,
            schema_verification=schema_verification,
        )
        missing_customer_access = build_release_audit(readiness=readiness, due_diligence=due, live_readiness=live_readiness, launch=launch)
        missing_schema = build_release_audit(readiness=readiness, due_diligence=due, live_readiness=live_readiness, launch=launch, customer_access=customer_access)
        report = build_release_audit(
            readiness=readiness,
            due_diligence=due,
            live_readiness=live_readiness,
            launch=launch,
            customer_access=customer_access,
            schema_verification=schema_verification,
        )
        self.assertEqual(missing_live_readiness["decisions"]["production"], "no_go")
        self.assertTrue(any("Missing live readiness" in item for item in missing_live_readiness["blockers"]["production"]))
        self.assertEqual(missing_customer_access["decisions"]["production"], "no_go")
        self.assertTrue(any("Missing customer access verification" in item for item in missing_customer_access["blockers"]["production"]))
        self.assertEqual(missing_schema["decisions"]["production"], "no_go")
        self.assertTrue(any("Missing live schema verification" in item for item in missing_schema["blockers"]["production"]))
        self.assertEqual(report["status"], "production_ready")
        self.assertEqual(report["decisions"], {"buyer_review": "go", "production": "go"})
        self.assertEqual(report["evidence"]["production_proof_source"], "live readiness + live schema verification + live launch report + customer access verification report")

    def test_preflight_allows_buyer_review_without_live_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readiness = build_readiness_pack(Path(tmp) / "readiness", run_qa=False)
            for gate in readiness["gates"]:
                if gate["name"] == "local_qa":
                    gate["status"] = "pass"
            due = build_due_diligence_pack(
                Path(tmp) / "due",
                readiness_report_path=Path(readiness["paths"]["readiness_report"]),
                modules=["windowpilot"],
            )
            report = build_preflight_report(readiness, due, env={}, stage="buyer_review")

        self.assertEqual(report["stage_status"], "pass")
        self.assertEqual(report["status"], "buyer_review_ready")
        self.assertEqual(report["decisions"]["buyer_review"], "go")
        self.assertEqual(report["decisions"]["live_launch"], "no_go")
        self.assertTrue(any("Healthcheck environment" in item for item in report["blockers"]["live_launch"]))

    def test_preflight_live_launch_requires_live_environment(self) -> None:
        readiness = {
            "status": "pass",
            "production_verified": False,
            "gates": [{"name": "local_qa", "status": "pass"}],
        }
        due = {
            "status": "local_ready",
            "production_gate": {"verified": False},
            "redaction": {"status": "pass"},
            "source_manifest_summary": {"missing": []},
        }
        report = build_preflight_report(readiness, due, env={}, stage="live_launch")
        self.assertEqual(report["stage_status"], "fail")
        self.assertEqual(report["decisions"]["buyer_review"], "go")
        self.assertEqual(report["decisions"]["live_launch"], "no_go")
        self.assertTrue(any("Healthcheck environment" in item for item in report["blockers"]["live_launch"]))


    def test_launch_runner_dry_run_builds_evidence_without_production_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "launch"
            with contextlib.redirect_stdout(io.StringIO()):
                report = run_live_rls_launch(out_dir=out_dir, dry_run=True)
            launch_report = json.loads((out_dir / "launch_report.json").read_text(encoding="utf-8"))
            probe_report = json.loads((out_dir / "rls_probe_report.json").read_text(encoding="utf-8"))
            cleanup_json_exists = (out_dir / "cleanup_plan.json").exists()
            cleanup_sql_exists = (out_dir / "cleanup_plan.sql").exists()

        self.assertEqual(report["status"], "dry_run")
        self.assertFalse(report["production_verified"])
        self.assertEqual(report["rls_probe"]["status"], "skipped_dry_run")
        self.assertEqual(probe_report["status"], "skipped_dry_run")
        self.assertEqual(launch_report["fixture_manifest"]["status"], "ready")
        self.assertEqual(launch_report["fixture_manifest"]["record_counts"]["memberships"], 3)
        self.assertEqual(launch_report["imports"]["onboarding"]["memberships"], 3)
        self.assertEqual(launch_report["imports"]["payload"]["exports"], 3)
        self.assertEqual(launch_report["cleanup"]["status"], "ready_for_review")
        self.assertTrue(cleanup_json_exists)
        self.assertTrue(cleanup_sql_exists)

    def test_launch_runner_refuses_live_placeholder_passwords(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_live_rls_launch(
                    out_dir=Path(tmp),
                    url="https://example.supabase.co",
                    service_key="service",
                    anon_key="anon",
                    dry_run=False,
                )

    def test_auth_admin_dry_run_user_ids_are_stable(self) -> None:
        admin = SupabaseAuthAdmin(url="", service_key="", dry_run=True)
        first = admin.ensure_user("window", "window@example.com", "secret")
        second = admin.ensure_user("window", "window@example.com", "secret")
        other = admin.ensure_user("facade", "facade@example.com", "secret")
        self.assertEqual(first["status"], "dry_run")
        self.assertEqual(first["user_id"], second["user_id"])
        self.assertNotEqual(first["user_id"], other["user_id"])

    def test_fixture_cleanup_plan_deletes_only_marked_fixture_tenants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "fixture"
            manifest = build_live_fixture(
                out_dir=out_dir,
                window_user_id="11111111-1111-4111-8111-111111111111",
                facade_user_id="22222222-2222-4222-8222-222222222222",
                facade_partner_user_id="33333333-3333-4333-8333-333333333333",
            )
            plan = build_fixture_cleanup_plan(
                {
                    "fixture_manifest": manifest,
                    "auth_users": [
                        {
                            "label": "window_customer",
                            "email": "window@example.com",
                            "user_id": "11111111-1111-4111-8111-111111111111",
                            "status": "created",
                        }
                    ],
                },
                include_auth_users=True,
            )

        sql = "\n".join(plan["sql"])
        self.assertEqual(plan["status"], "ready_for_review")
        self.assertEqual(plan["tenant_count"], 2)
        self.assertEqual(len(plan["auth_users"]), 1)
        self.assertIn("delete from public.homepilot_tenants", sql)
        self.assertIn("settings ->> 'fixture'", sql)
        self.assertIn("homepilot_live_fixture", sql)

    def test_live_fixture_builds_two_tenant_rls_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "fixture"
            manifest = build_live_fixture(
                out_dir=out_dir,
                window_user_id="11111111-1111-4111-8111-111111111111",
                facade_user_id="22222222-2222-4222-8222-222222222222",
                facade_partner_user_id="33333333-3333-4333-8333-333333333333",
            )
            onboarding = json.loads((out_dir / "onboarding.json").read_text(encoding="utf-8"))
            payload = json.loads((out_dir / "payload.json").read_text(encoding="utf-8"))
            probe_config = load_probe_config(out_dir / "rls_probe_config.json")

        self.assertEqual(manifest["status"], "ready")
        self.assertEqual(manifest["record_counts"]["tenants"], 2)
        self.assertEqual(manifest["record_counts"]["memberships"], 3)
        self.assertEqual({row["module_key"] for row in onboarding["tenant_modules"]}, {"windowpilot", "facadepilot"})
        self.assertEqual({row["module_key"] for row in payload["assessments"]}, {"windowpilot", "facadepilot"})
        self.assertEqual(probe_config["identities"][0]["modules"], ["windowpilot"])
        self.assertEqual(probe_config["identities"][1]["modules"], ["facadepilot"])
        self.assertEqual(probe_config["identities"][2]["partner_id"], "renotec-antwerp")
        self.assertEqual(onboarding["memberships"][2]["partner_id"], "renotec-antwerp")
        self.assertEqual(manifest["record_counts"]["properties"], 3)
        self.assertNotEqual(probe_config["identities"][0]["tenant_id"], probe_config["identities"][1]["tenant_id"])
        validate_payload(payload)

    def test_live_fixture_flags_missing_membership_user_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "fixture"
            manifest = build_live_fixture(out_dir=out_dir)
            onboarding = json.loads((out_dir / "onboarding.json").read_text(encoding="utf-8"))
            readme = (out_dir / "README.md").read_text(encoding="utf-8")
        self.assertEqual(manifest["status"], "needs_user_ids")
        self.assertEqual(manifest["record_counts"]["memberships"], 0)
        self.assertEqual(onboarding["memberships"], [])
        self.assertIn("Missing membership user IDs", readme)

    def test_live_fixture_module_payload_is_seeded_for_required_probe_views(self) -> None:
        payload = build_module_payload(
            tenant_slug="fixture-test",
            module_key="windowpilot",
            campaign_key="window-test",
            address="Fixturelaan 1",
            city="Leuven",
            lat=50.88,
            lon=4.7,
            score=92,
        )
        validate_payload(payload)
        self.assertEqual(len(payload["properties"]), 1)
        self.assertEqual(len(payload["assessments"]), 1)
        self.assertEqual(len(payload["campaign_targets"]), 1)
        self.assertEqual(len(payload["interactions"]), 1)
        self.assertEqual(len(payload["response_insights"]), 1)
        self.assertEqual(len(payload["exports"]), 1)
        self.assertEqual(payload["assessments"][0]["module_key"], "windowpilot")

    def test_rls_probe_detects_tenant_and_module_leaks(self) -> None:
        tenant_id = canonical_tenant_id("tenant_a")
        identity = {"label": "window", "tenant_id": tenant_id, "modules": ["windowpilot"]}
        endpoint = ProbeEndpoint(
            name="homepilot_assessments",
            path="homepilot_assessments",
            tenant_field="tenant_id",
            module_field="module_key",
        )
        passing = evaluate_rows(endpoint, [
            {"tenant_id": tenant_id, "module_key": "windowpilot"},
        ], identity)
        self.assertEqual(passing["status"], "pass")

        failing = evaluate_rows(endpoint, [
            {"tenant_id": canonical_tenant_id("tenant_b"), "module_key": "windowpilot"},
            {"tenant_id": tenant_id, "module_key": "facadepilot"},
        ], identity)
        self.assertEqual(failing["status"], "fail")
        self.assertTrue(any("exposes tenant" in issue for issue in failing["issues"]))
        self.assertTrue(any("exposes module facadepilot" in issue for issue in failing["issues"]))

        partner_endpoint = ProbeEndpoint(
            name="homepilot_campaign_targets",
            path="homepilot_campaign_targets",
            tenant_field="tenant_id",
            module_field="module_key",
            partner_fields=("metadata.partner_id",),
        )
        partner_identity = {
            "label": "renotec",
            "tenant_id": tenant_id,
            "modules": ["facadepilot"],
            "partner_id": "renotec-antwerp",
        }
        partner_failing = evaluate_rows(partner_endpoint, [
            {"tenant_id": tenant_id, "module_key": "facadepilot", "metadata": {"partner_id": "other-partner"}},
        ], partner_identity)
        self.assertEqual(partner_failing["status"], "fail")
        self.assertTrue(any("exposes partner other-partner" in issue for issue in partner_failing["issues"]))

    def test_rls_probe_identity_aggregates_endpoint_failures(self) -> None:
        tenant_id = canonical_tenant_id("tenant_a")
        identity = {"label": "window", "tenant_id": tenant_id, "modules": ["windowpilot"]}

        def fake_get(path: str) -> list[dict]:
            if path.startswith("homepilot_assessments"):
                return [{"tenant_id": tenant_id, "module_key": "facadepilot"}]
            if path.startswith("homepilot_properties"):
                return [{"tenant_id": canonical_tenant_id("tenant_b")}]
            return []

        report = probe_identity(identity, fake_get, allow_empty=True)
        self.assertEqual(report["status"], "fail")
        issues = "\n".join(
            issue
            for check in report["checks"]
            for issue in check["issues"]
        )
        self.assertIn("facadepilot", issues)
        self.assertIn(canonical_tenant_id("tenant_b"), issues)

    def test_rls_probe_template_config_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rls_probe_config.json"
            write_template(path)
            config = load_probe_config(path)
        self.assertEqual(len(config["identities"]), 2)
        self.assertEqual(config["identities"][0]["modules"], ["windowpilot"])
        self.assertEqual(config["identities"][1]["partner_id"], "renotec-antwerp")

    def test_dashboard_sql_views_remain_rls_invoker_views(self) -> None:
        sql = (PLATFORM / "dashboard_views.sql").read_text(encoding="utf-8").lower()
        for view in (
            "homepilot_property_intelligence",
            "homepilot_property_export",
            "homepilot_property_public_enrichment",
            "homepilot_campaign_metrics",
            "homepilot_module_metrics",
            "homepilot_second_brain_edges",
        ):
            self.assertIn(f"view public.{view}", sql)
        self.assertIn("function public.homepilot_metrics_for_customer", sql)
        self.assertIn("homepilot_metrics_for_customer(a.module_key, a.metrics) as metrics", sql)
        self.assertGreaterEqual(sql.count("security_invoker = true"), 6)
        self.assertIn("homepilot_has_tenant_access", sql)
        self.assertIn("homepilot_has_module_access", sql)
        self.assertIn("partner_id", sql)
        self.assertIn("homepilot_property_enrichments", sql)
        self.assertIn("homepilot_partner_scope_matches", sql)
        self.assertIn("public_fields", sql)
        self.assertIn("licence", sql)
        self.assertIn("allowed_use", sql)
        self.assertIn("target_response_rate_pct", sql)
        self.assertIn("contacted_count", sql)
        self.assertIn("/ count(*) filter (where ct.status in ('sent','scanned','clicked','responded','appointment','customer','no_response'))::numeric", sql)
        schema = (PLATFORM / "supabase_schema.sql").read_text(encoding="utf-8").lower()
        self.assertIn("homepilot_audit_events", schema)
        self.assertIn("homepilot_source_runs", schema)
        self.assertIn("homepilot_geographies", schema)
        self.assertIn("homepilot_public_features", schema)
        self.assertIn("homepilot_property_enrichments", schema)
        self.assertIn("homepilot property enrichments read own", schema)
        self.assertIn("homepilot public features read own", schema)
        self.assertIn("homepilot source runs write managers", schema)
        self.assertIn("partner_id text", schema)
        self.assertIn("partner_name text", schema)
        self.assertIn("metadata jsonb not null default '{}'::jsonb", schema)
        self.assertIn("'landing_page_scan'", schema)
        self.assertIn("'appointment'", schema)
        self.assertIn("homepilot_partner_scope_matches", schema)
        self.assertIn("homepilot_membership_partner_id", schema)
        self.assertIn("homepilot audit events read own", schema)

    def test_public_enrichment_schema_keeps_public_data_separate_from_campaign_basis(self) -> None:
        schema = (PLATFORM / "supabase_schema.sql").read_text(encoding="utf-8").lower()
        sql = (PLATFORM / "dashboard_views.sql").read_text(encoding="utf-8").lower()
        self.assertIn("public_fields jsonb not null default '{}'::jsonb", schema)
        self.assertIn("provenance jsonb not null default '{}'::jsonb", schema)
        self.assertIn("licence text not null", schema)
        self.assertIn("allowed_use text not null", schema)
        self.assertIn("homepilot_property_public_enrichment", sql)
        self.assertIn("source_run_id", sql)
        self.assertIn("homepilot_partner_scope_matches", sql)
        self.assertNotIn("owner_name", schema)
        self.assertNotIn("owner_email", schema)


if __name__ == "__main__":
    unittest.main()
