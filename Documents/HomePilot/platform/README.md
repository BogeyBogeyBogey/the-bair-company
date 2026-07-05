# HomePilot Platform

Shared property intelligence layer for the Pilot modules. This directory holds the contracts that make FacadePilot, WindowPilot, RoofPilot, PoolPilot, GardenPilot, PorchPilot, and DrivewayPilot behave as modules in one tenant-safe database.

Core files:

- `homepilot_access_audit.py`: local tenant/module leakage audit for payloads, snapshots, and exports.
- `homepilot_account_access.py`: builds reviewable customer account access, invitation, role, membership SQL, and revocation packs.
- `homepilot_customer_access_verification.py`: verifies planned customer invitees against live tenant/module RLS with credentials read only from environment variables.
- `homepilot_api_contract.py`: builds the customer API/read-model contract for Supabase/PostgREST views, filters, headers, and RLS guarantees.
- `homepilot_audit_trail.py`: builds reviewable audit events for package generation, exports, access audits, RLS probes, and operator handoffs.
- `homepilot_benchmarks.py`: builds privacy-safe aggregate benchmark rows with minimum cohort thresholds.
- `homepilot_boardroom_report.py`: builds the executive boardroom report, dashboard HTML report, and producer-network partner summary CSV from the same tenant/module-scoped snapshot.
- `homepilot_campaign_learning.py`: builds tenant-scoped campaign learning reports with funnel, segment, objection, and experiment-backlog insights.
- `homepilot_customer_package.py`: builds a customer-ready dashboard/export/audit handoff package.
- `homepilot_compliance.py`: audits outreach provenance, contact basis, opt-out propagation, retention review, and safe lead-claim language.
- `homepilot_customer_brief.py`: builds a boardroom-ready customer intelligence brief from the tenant/module-scoped dashboard snapshot.
- `homepilot_data_dictionary.py`: builds the enterprise dictionary for modules, metrics, exports, tables, views, surfaces, and privacy rules.
- `homepilot_data_quality.py`: audits score, geocode, evidence, target, response, and duplicate coverage before import/customer handoff.
- `homepilot_deployment.py`: builds schema deployment manifests with SQL checksums, apply order, marker validation, and post-apply checks.
- `homepilot_demo_room.py`: builds a synthetic all-module enterprise demo room with dashboard, exports, portal, CRM handoff, enrichment plan, access audit, audit trail, and data dictionary.
- `homepilot_enrichment.py`: builds data vendor/source-layer readiness packs with coverage, licensing/freshness guardrails, and enrichment backlog CSVs.
- `homepilot_enrichment_refresh.py`: dry-runs or executes vendor/API enrichment refresh batches with env-only credentials, idempotency, retry accounting, dead-letter output, and secret-safe reports.
- `homepilot_due_diligence.py`: builds a buyer/security evidence pack with readiness gates, access matrices, source hashes, and redaction scan.
- `homepilot_entitlements.py`: scopes canonical payloads to exactly the tenant and enabled modules a customer may see.
- `homepilot_metric_access.py`: defines customer/export/benchmark metric visibility and role-based product access matrices.
- `homepilot_platform.py`: module catalog, metric definitions, canonical IDs, and FacadePilot CSV conversion.
- `homepilot_preflight.py`: combines local health, readiness, due-diligence, release, and optional launch evidence into one operator go/no-go report.
- `homepilot_production_proof.py`: builds a tamper-evident production proof manifest with artifact hashes, freshness, missing live proof, and secret-scan status.
- `homepilot_portal.py`: builds deployable customer portal bundles with public dashboard assets, exports, live Auth/RLS runtime config, security headers, redirects, route map, and manifest checks.
- `homepilot_hosting.py`: builds portal hosting evidence with asset hashes, cache policy, provider configs, deployment checklist, rollback manifest, private-access guardrails, and secret scan.
- `homepilot_processing_register.py`: builds the data processing/privacy register for enterprise review, including activities, categories, controls, risks, retention, and data-subject workflows.
- `homepilot_release_pack.py`: builds the release evidence bundle with audit, preflight, production proof, dry-run production cutover evidence, market-ready gap audit, artifact index, release notes, handoff checklist, and deployment manifest.
- `homepilot_recovery.py`: builds backup manifests, tenant-guarded rollback SQL, and operator recovery runbooks for import evidence.
- `homepilot_pilot_csv.py`: generic CSV adapter for canonical module metric columns across all pilots.
- `homepilot_store.py`: Supabase/PostgREST import and validation layer.
- `homepilot_sync.py`: repeatable pilot-to-HomePilot sync commands.
- `homepilot_territory_plan.py`: builds tenant-scoped territory and next-batch planning reports from customer dashboard snapshots.
- `homepilot_visual_intelligence.py`: builds clustered map models, second-brain graph render budgets, visual scale evidence, and boardroom runbooks.
- `homepilot_autoresearch.py`: runs a non-mutating second-brain graph layout research loop and writes reviewable graph readability evidence.
- `homepilot_lead_autoresearch.py`: runs a non-mutating opportunity-prioritization research loop and writes reviewable lead-priority model evidence.
- `homepilot_partner_assignment_autoresearch.py`: runs a non-mutating producer-network partner wave research loop and writes reviewable scope-safe assignment evidence.
- `homepilot_campaign_segmentation_autoresearch.py`: runs a non-mutating campaign segmentation research loop and writes denominator-safe segment evidence.
- `homepilot_message_strategy_autoresearch.py`: runs a non-mutating message-strategy research loop and writes compliant draft-message evidence for review.
- `homepilot_intelligence_lab.py`: orchestrates the non-mutating autoresearch stack for enterprise packages and attaches lead, partner, segmentation, and message evidence to the tenant-scoped snapshot.
- `homepilot_snapshot.py`: converts canonical payloads into customer dashboard snapshots.
- `homepilot_onboarding.py`: builds/imports tenant, membership, and enabled-module records.
- `homepilot_open_intelligence.py`: builds the Open Intelligence model card, model lab, data collaboration room, marketing-impact planner, channel mix, measurement loop, activation paths, outcome loop, and guardrails for enterprise buyer review.
- `homepilot_outcome_measurement_contract.py`: builds the closed-loop appointment, quote, won/lost, value, and loss-reason outcome contract with event schema, sync template, reconciliation checklist, no live writes, and no raw contact data.
- `homepilot_outcome_import_validation.py`: validates customer-approved CRM/sheet outcome rows in a dry run before live sync, checking tenant/module/partner scope, stages, idempotency, source references, amounts, approvals, loss reasons, secrets, and raw-contact leakage without live writes.
- `homepilot_module_readiness_matrix.py`: builds the buyer/IT module-readiness matrix across all Pilot modules, including metric visibility, export readiness, public-data lanes, scope filters, and live-production gates.
- `homepilot_partner_cutdown.py`: builds partner-specific customer packages for producer networks, with partner-scope leakage evidence.
- `homepilot_partner_access_reconciliation.py`: reconciles partner Auth mappings, account-access membership rows, and customer-access verification into a non-mutating production gate before partner portal access.
- `homepilot_public_data_reconciliation.py`: reconciles public-data source registers, dataset approval intake, first-wave public-data need, and live-proof status before any production public-data import.
- `homepilot_opportunity_dossier.py`: builds customer-safe explainability dossiers for prioritized properties, evidence, metric drivers, review gaps, and next actions.
- `homepilot_source_ledger.py`: builds customer-safe source/provenance ledgers for evidence coverage, source runs, confidence, freshness, and review gaps.
- `homepilot_sql_apply_plan.py`: builds a reviewable Supabase SQL apply bundle, post-apply smoke SQL, operator commands, checksums, and rollback notes without storing credentials.
- `homepilot_live_proof_evidence_vault.py`: builds a non-mutating live-proof archive index for schema, RLS, customer access, partner access, public-data, signoff, first-wave, and production evidence without storing secrets or raw contact data.
- `homepilot_ops_status.py`: builds operational status pages and runbooks from readiness, due-diligence, preflight, release, and launch evidence.
- `homepilot_export.py`: builds customer CSV/XLSX export bundles from payloads or snapshots.
- `homepilot_responses.py`: merges response/no-response spreadsheet rows into payload interactions and campaign target statuses.
- `homepilot_privacy.py`: builds export-audit records and per-property delete plans for privacy/lifecycle reviews.
- `homepilot_retention.py`: audits contacted records for retention schedules, due reviews, opt-out lifecycle handling, and delete-plan triggers.
- `homepilot_roi_forecast.py`: builds tenant-scoped ROI/business-case forecasts with explicit scenario and capacity assumptions.
- `homepilot_rls_probe.py`: probes live Supabase RLS with real user JWTs across tenants and modules.
- `homepilot_live_fixture.py`: builds two-tenant live RLS verification fixtures and probe configs.
- `homepilot_fixture_cleanup.py`: builds reviewable SQL cleanup plans for temporary live RLS fixtures.
- `homepilot_healthcheck.py`: runs local and optional live operational checks for files, SQL contracts, client assets, environment, and Supabase reachability.
- `homepilot_integrations.py`: builds CRM/webhook integration packs with CRM import CSV, JSONL webhook events, field mapping, idempotency/retry contract, runbook, and secret-scan checks.
- `homepilot_integration_sync.py`: dry-runs or executes CRM/webhook sync batches with env-only credentials, idempotency, retry accounting, dead-letter output, and secret-safe reports.
- `homepilot_monitoring.py`: builds the customer-safe monitoring plan, alert matrix, owners, cadence, production blockers, and remediation runbook for live operations.
- `homepilot_launch.py`: bootstraps Supabase test users, imports the fixture, runs the RLS probe, and writes launch plus cleanup evidence.
- `homepilot_live_launch_request.py`: turns missing live-readiness inputs into a customer/operator checklist, env template, and request email without writing secret values.
- `homepilot_live_proof_plan.py`: turns buyer-review, live-readiness, launch-request, and production-proof evidence into a guarded live-proof execution plan, evidence map, and command script with no secrets or live writes.
- `homepilot_live_credential_handoff.py`: turns missing live Supabase, RLS fixture, and customer-access inputs into a secret-safe customer/IT handoff contract with owners, env var names, approved channels, validation artifacts, and checklist CSVs without storing secret values.
- `homepilot_launch_control_room.py`: turns market-readiness, live-readiness, production-proof, first-wave launch-gate, partner Auth/access, public-data reconciliation, and customer signoff evidence into a non-mutating live launch cockpit with stage gates, owner actions, env var names, and secret-scan guardrails.
- `homepilot_market_ready_audit.py`: maps the full market-ready platform objective to buyer-review evidence, live-launch blockers, production blockers, owners, next actions, and no-secrets/no-live-write guardrails.
- `homepilot_first_campaign_input_validation.py`: validates filled first-campaign customer CSVs for partner scope, territories, property source/contact basis, suppression, message approval, capacity, raw contact leakage, and live-proof gating.
- `homepilot_first_campaign_import_plan.py`: turns validated first-campaign CSVs into a non-mutating tenant/module/partner/campaign/source-run staging manifest, Markdown import plan, and Excel-ready staging rows without writing to Supabase or exposing raw contacts/secrets.
- `homepilot_first_wave_launch_gate.py`: combines first-campaign input validation, staging plan, source/message/suppression approval, public-data approval, live proof, and customer go/no-go into a non-mutating final first-wave launch decision.
- `homepilot_first_wave_database_handoff.py`: converts an authorized first-wave launch gate and staging plan into customer-IT database review artifacts, while blocked gates produce comment-only SQL with no executable DML.
- `homepilot_partner_auth_mapping.py`: bridges approved partner rosters to real Supabase Auth user IDs with a non-mutating mapping template, issue CSV, redacted review rows, and comment-only membership SQL until launch authorization and mapping completeness are proven.
- `homepilot_market_readiness.py`: builds a boardroom-friendly HTML view, DAW boardroom demo walkthrough/checklist, DAW first-campaign control room/action board, live launch control room/action board, market-ready gap audit/requirements CSV, customer acceptance plan/checklist, customer rollout/RACI plan, first-campaign intake, customer input templates, first-campaign input validation report/issues CSV, first-campaign import plan/staging rows, first-wave launch gate/checklist, first-wave database handoff/review SQL, partner Auth mapping/review SQL, partner-access reconciliation, synthetic completed DAW customer-input examples with happy-path validation plus staging plan and launch gate, procurement/security review pack, support/SLA and incident-response plan, buyer-review pilot proposal, customer training/adoption guide, training session plan, role cheatsheet, customer view catalog/matrix, value-realization plan, KPI CSV, executive decision log, outcome measurement contract/schema/template/checklist, outcome import dry-run validation/issues/review rows, module-expansion plan, module value matrix, expansion decision tree, public-data source register/matrix, blocked-data register, attribution requirements, public-data production intake and reconciliation, customer signoff reconciliation matrix/issues plus safe signoff intake/template CSV, portable data-room HTML/ZIP with relative evidence links, local-path redaction, and checksums, scorecard, data-room index, stakeholder views, and launch action CSV from the evidence pack.
- `homepilot_customer_view_catalog.py`: renders the buyer-review "who sees what" catalog across DAW producer, network-manager, partner-renovator, module-only, IT/security, customer-success, and benchmark-safe lenses without replacing Supabase/RLS runtime authorization.
- `homepilot_data_platform_blueprint.py`: renders the buyer/IT blueprint for the shared HomePilot database spine across tenants, modules, partners, campaigns, public-data lanes, exports, access lenses, and live-proof gates.
- `MARKET_RESEARCH.md`: competitive research, best practices, and HomePilot positioning against property data, visual intelligence, CRM, and lead marketplace systems.
- `homepilot_readiness.py`: builds a local enterprise evidence pack across launch dry-run, customer package, data quality, compliance, retention, cleanup, and benchmark privacy gates.
- `homepilot_release_audit.py`: produces the final buyer-review and production go/no-go decision from readiness, due-diligence, live readiness, live schema, live launch, and customer access evidence.
- `homepilot_qa.py`: local preflight runner for platform, dashboard, and SQL contracts.
- `supabase_schema.sql`: normalized tenant/module/property/campaign schema with RLS, plus separate public-data enrichment/provenance tables.
- `dashboard_views.sql`: dashboard, export, public enrichment, campaign metric, module metric, and second-brain views.

Operational docs:

- `ARCHITECTURE.md`
- `IMPORTING.md`
- `SYNC.md`
- `DASHBOARD.md`
- `PRODUCTION_READINESS.md`
- `PRODUCTION_LAUNCH.md`

## Local QA

Run before sharing a customer demo, importing a new pilot batch, or applying schema changes:

```bash
python3 platform/homepilot_qa.py
```
