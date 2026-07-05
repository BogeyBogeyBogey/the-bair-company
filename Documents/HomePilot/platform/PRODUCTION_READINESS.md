# Production Readiness

HomePilot is intended to become a market-ready property intelligence platform
for renovation opportunities. This checklist defines what must be true before a
large customer gets access.

## Operational Health Check

Before any live run, copy `.env.example` to `.env` and fill the HomePilot
Supabase URL, service-role key, and anon key. Keep real secrets out of git.
The healthcheck validates the template and reports missing runtime values.

Run the non-destructive healthcheck before demos, handoffs, and live launches:

```bash
python3 platform/homepilot_healthcheck.py --out /tmp/homepilot_healthcheck.json
```

For live rollout, require Supabase configuration and REST reachability:

```bash
python3 platform/homepilot_healthcheck.py \
  --live \
  --require-live \
  --out /tmp/homepilot_healthcheck_live.json
```

## Current Local Gates

Run:

```bash
python3 platform/homepilot_qa.py
```

This checks:

- Python platform files compile.
- Contract tests pass.
- Dashboard JavaScript parses.
- Dashboard SQL views retain tenant/module security markers.

## Data Access Gates

Before onboarding a paying customer:

- Run `homepilot_onboarding.py` for every paying tenant before importing campaign data.
- Every user belongs to exactly one or more explicit `homepilot_memberships`.
- Build `homepilot_account_access.py` packs before live access so invitees, roles, permissions, membership SQL, and revocation SQL are reviewed.
- Run `homepilot_customer_access_verification.py` against the reviewed account access plan before production access so planned customer invitees are verified with live tenant/module RLS.
- Build `homepilot_partner_access_reconciliation.py` for producer networks before partner portal access so partner Auth mappings, planned membership rows, and customer-access probe identities are aligned.
- Every visible record has a `tenant_id`.
- Every module-specific record has a `module_key`.
- Customer-facing metric surfaces use `homepilot_metric_access.py`; unknown metric keys are hidden by default.
- Generate `homepilot_data_dictionary.py` for enterprise handoffs so every visible metric, export sheet, table, and dashboard view has a reviewed definition.
- Generate `homepilot_processing_register.py` for enterprise privacy review so processing purposes, data categories, controls, risks, and retention workflows are explicit.
- `homepilot_tenant_modules` contains only modules the customer paid for.
- `homepilot_metrics_for_customer` is used by SQL dashboard/export views so live reads do not expose internal metrics.
- `homepilot_has_tenant_access` and `homepilot_has_module_access` are used by all customer-facing views.
- Static `dashboard-data.js` exports are generated for one tenant only.
- Customer packages scope the source payload from onboarding tenant/module entitlements before dashboard/export generation.
- Manual snapshot/export generation uses `--module` when the customer has limited module access.
- Run `homepilot_access_audit.py` before sharing a snapshot or export bundle.
- Access audits must fail if snapshots, scoped payloads, or exports contain hidden/internal metrics.
- Run `homepilot_data_quality.py` before live import or customer handoff; fails block launch, warnings require review.
- Build a `homepilot_recovery.py recovery-pack` for every live import so source hashes, rollback SQL, and operator recovery steps are archived.
- Run `homepilot_compliance.py` before outreach activation or customer handoff; fails block campaign use, warnings require review.
- Build customer handoff packages with `homepilot_customer_package.py` so scoped payload, dashboard, exports, manifest, audit report, export log, and audit trail stay together.
- Build `homepilot_portal.py` bundles from customer packages before online deployment so public assets, exports, live Auth/RLS runtime config, security headers, redirects, route map, tenant scope, and secret scan are reviewed together.
- Build `homepilot_hosting.py` packs before hosting a customer portal so asset hashes, cache policy, provider configs, private-access guardrails, rollback manifest, and hosted verification blockers are reviewed together.
- Build `homepilot_integrations.py` packs before sales handoff so CRM import CSV, webhook payloads, provider field mappings, idempotency/retry rules, and secret scan are reviewed together.
- Run `homepilot_integration_sync.py` in dry-run before live CRM activation, then live only with customer-specific webhook URL/API key from environment variables and archived sync reports.
- Build `homepilot_monitoring.py` packs before buyer review and live launch so alert ownership, cadence, source gates, production blockers, and remediation are explicit.
- Build `homepilot_enrichment.py` packs before territory scale-up so parcel, geocode, imagery, energy, permit, pricing, and contact-provenance coverage/backlog are reviewed.
- Run `homepilot_enrichment_refresh.py` in dry-run before live vendor refresh, then live only with customer/vendor endpoint and API key from environment variables plus archived refresh reports.
- Store approved public-data imports in `homepilot_source_runs`, `homepilot_geographies`, `homepilot_public_features`, and `homepilot_property_enrichments` so source licence, allowed use, attribution, transform version, confidence, and provenance stay separate from campaign/contact basis.
- Build `homepilot_public_data_reconciliation.py` before any production public-data import so source register rows, dataset approvals, first-wave public-data need, and live proof are aligned.
- Build `homepilot_demo_room.py` before enterprise demos so the all-module showroom, portal, CRM handoff, enrichment plan, exports, and audit evidence are generated from one canonical payload.
- Include `homepilot_customer_brief.py` in customer handoff packages so leadership, sales, and operations get the same tenant/module-scoped business case in JSON and Markdown.
- Include `homepilot_campaign_learning.py` in customer handoff packages so response and no-response memory becomes a concrete experiment backlog for the next campaign.
- Include `homepilot_territory_plan.py` in customer handoff packages so customers know which city/segment/module batch to run next and why.
- Build `homepilot_visual_intelligence.py` packs before large territory demos/imports so map clustering, graph budgets, and boardroom visual strategy are proven.
- Use `homepilot_autoresearch.py` only for non-mutating second-brain graph layout experiments; treat winning layout configs as reviewable visual proposals, not production proof or customer demand evidence.
- Include `homepilot_roi_forecast.py` in customer handoff packages so the buyer sees explicit scenario assumptions, expected outcomes, and capacity needs.
- Include `homepilot_opportunity_dossier.py` in customer handoff packages so every top property has customer-safe reasons, evidence, review gaps, and a next action.
- Include `homepilot_source_ledger.py` in customer handoff packages so coverage, source runs, confidence, timestamps, provenance gaps, and lead-claim guardrails are reviewable.
- Include `homepilot_boardroom_report.py` in readiness evidence so executive KPIs, partner/module steering matrix, work queues, recommendations, caveats, and producer-network partner summary CSV are verified before buyer demos.
- Build `homepilot_partner_cutdown.py` packs for producer networks so each renovator receives only assigned records and leakage evidence before partner access is discussed.
- Run or review `homepilot_audit_trail.py` reports for customer packages and live launch evidence so package/export/access events are traceable.
- No public/demo repository contains generated customer snapshots.

## Supabase Gates

Build a deployment manifest before applying SQL:

```bash
python3 platform/homepilot_deployment.py \
  --out-dir /tmp/homepilot_deployment_pack \
  --release-label production-candidate
```

The deployment pack includes `SQL_APPLY_PLAN.md`, `apply.sql`, and
`post_apply_verification.sql`. To generate that review bundle by itself:

```bash
python3 platform/homepilot_sql_apply_plan.py \
  --out-dir /tmp/homepilot_sql_apply_plan \
  --release-label production-candidate
```

Before enabling real customer access, build and archive customer access
verification evidence. Credentials are read from the environment variables named
in the generated probe contract; tokens/passwords are not written to the report:

```bash
python3 platform/homepilot_customer_access_verification.py \
  --account-access-plan /tmp/homepilot_readiness/account_access_smoke/account_access_plan.json \
  --out-dir /tmp/homepilot_customer_access_verification
```

When live readiness reports missing inputs, build the launch request pack before
asking the operator/customer IT team for credentials. It writes the request
summary, checklist, env template, and email draft with env var names only:

```bash
python3 platform/homepilot_live_launch_request.py \
  --out-dir /tmp/homepilot_live_launch_request \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --account-access-plan /tmp/homepilot_readiness/account_access_smoke/account_access_plan.json \
  --release-label production-candidate
```

Archive `LIVE_LAUNCH_REQUEST.md`, `LIVE_LAUNCH_CHECKLIST.csv`,
`live_launch.env.template`, and `LIVE_LAUNCH_REQUEST_EMAIL.txt` with the
buyer/security evidence. Do not send service keys, database URLs, fixture
passwords, JWTs, or customer passwords by email.

After those owners are assigned, build the guarded live-proof execution plan:

```bash
python3 platform/homepilot_live_proof_plan.py \
  --out-dir /tmp/homepilot_live_proof_plan \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --live-launch-request /tmp/homepilot_live_launch_request/live_launch_request.json \
  --production-proof /tmp/homepilot_release_pack/production_proof.json \
  --artifact-index /tmp/homepilot_release_pack/artifact_index.json \
  --release-label production-candidate
```

Archive `LIVE_PROOF_EXECUTION_PLAN.md`, `LIVE_PROOF_EVIDENCE_MAP.csv`, and
`LIVE_PROOF_COMMANDS.sh` with the launch evidence. The command script requires
`HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof` plus secure environment values;
do not treat it as live proof until the resulting schema, launch/RLS, and
customer access reports all show `production_verified=true`.

Apply in order:

```text
platform/supabase_schema.sql
platform/dashboard_views.sql
```

Then verify with at least two tenants:

- Tenant A can read its own properties, assessments, campaigns, interactions, exports, and dashboard views.
- Tenant A cannot read Tenant B records.
- A WindowPilot-only tenant cannot read FacadePilot assessments or FacadePilot campaign rows.
- A multi-module tenant sees only enabled modules.
- Service-role imports work, but customer JWT access remains governed by RLS.
- Run `homepilot_rls_probe.py probe` with real Supabase Auth users and archive the JSON report before giving a customer production access.

## Enterprise Evidence Pack

Before running a live Supabase launch, build a local evidence pack:

```bash
python3 platform/homepilot_readiness.py build \
  --out-dir /tmp/homepilot_readiness_pack \
  --run-qa
```

The readiness report must be `pass`, including the data dictionary and schema
verification smoke gates, but it must still show `production_verified: false`.
Production is proven only after live schema verification, live launch/RLS probe,
and customer access verification all return `production_verified: true`.

After buyer review, the safest operator path is the cutover orchestrator:

```bash
python3 platform/homepilot_production_cutover.py \
  --out-dir /tmp/homepilot_cutover_live \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json \
  --release-label production-candidate \
  --live
```

This runner does not apply SQL automatically. It first writes the redacted live
readiness evidence; if required live inputs are missing, it stops before
seed/import/probe steps. Once ready, it verifies the live schema after SQL is
applied, seeds modules, runs the live RLS fixture, verifies planned customer
access, and writes `cutover_report.json`.

## Buyer Due-Diligence Pack

For enterprise buyer/security review, generate:

```bash
python3 platform/homepilot_due_diligence.py \
  --out-dir /tmp/homepilot_due_diligence_pack \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --module windowpilot
```

The due-diligence pack must not copy raw customer rows. It summarizes the
readiness gates, access matrices, source hashes, and redaction status.

## Buyer Data Room

After readiness and due diligence are available, build the release evidence
bundle for buyer review:

```bash
python3 platform/homepilot_release_pack.py \
  --out-dir /tmp/homepilot_release_pack \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --release-label production-candidate \
  --stage buyer_review
```

Share `/tmp/homepilot_release_pack/market_readiness/homepilot_boardroom_data_room.zip`
first for customer review. It contains `index.html`,
`DATA_ROOM_MANIFEST.json`, and copied evidence files with relative links and
SHA-256 checksums. The portable copy redacts local machine paths from text
artifacts, so the boardroom/IT reader is not dependent on or distracted by
local absolute paths. The local `market-readiness.html` remains useful for
operator review inside the generated evidence directory.

Use `LIVE_LAUNCH_CONTROL_ROOM.md` and `LIVE_LAUNCH_ACTION_BOARD.csv` from the
same `market_readiness/` directory as the live-launch cockpit. They summarize
buyer-review, live-input, live schema, RLS launch, customer-access, first-wave,
and production gates in one place. The control room is intentionally
non-mutating: it stores env var names and evidence references only, and
production remains `no_go` until live schema/RLS/customer-access reports show
`production_verified=true`.

Use `LIVE_PROOF_EXECUTION_PLAN.md`, `LIVE_PROOF_EVIDENCE_MAP.csv`, and
`LIVE_PROOF_COMMANDS.sh` as the single operator checklist once live inputs are
assigned. It is generated by `homepilot_live_proof_plan.py`, remains
non-mutating until the guarded commands are run deliberately, and keeps buyer
review, live launch, and production proof separated.

Use `production_cutover/CUTOVER_RUNBOOK.md` and
`production_cutover/cutover_report.json` from the release pack as the dry-run
operator rehearsal. They show the exact sequence for live readiness, schema
verification, module seeding, RLS fixture launch, customer access verification,
and final release audit without writing live data or claiming production proof.

Use `MARKET_READY_GAP_AUDIT.md` and `MARKET_READY_REQUIREMENTS.csv` as the
plain-language market-ready requirements tracker. They separate what is already
buyer-review ready from what still blocks live launch, production rollout, and
first-wave outreach. The audit is derived evidence only: it writes no live data,
stores no secret values, and does not replace live Supabase/RLS/customer-access
proof.

For the first DAW-style buyer meeting, use
`DAW_BOARDROOM_DEMO_WALKTHROUGH.md` as the talk track and
`DAW_DEMO_CHECKLIST.csv` as the operator checklist. These files sequence the
portable data room, executive dashboard, boardroom report, second-brain graph,
partner cutdowns, completed-input example, public-data governance, and live
launch request without turning synthetic demo results into production claims.
Use `DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md` and
`DAW_FIRST_CAMPAIGN_ACTION_BOARD.csv` immediately after the demo to keep partner
waves, owners, customer inputs, public-data approvals, live proof, and
first-wave go/no-go evidence in one operating cockpit.

After DAW or another enterprise customer fills the six first-campaign CSV
templates, validate them before importing data, sending outreach, or giving
partners access:

```bash
python3 platform/homepilot_first_campaign_input_validation.py \
  --out-dir /tmp/homepilot_first_campaign_validation \
  --template-pack /tmp/homepilot_release_pack/market_readiness/customer_input_templates.json \
  --input-dir /path/to/customer-filled-templates \
  --release-label production-candidate \
  --expected-partners 10
```

Archive `FIRST_CAMPAIGN_INPUT_VALIDATION.md` and
`FIRST_CAMPAIGN_INPUT_ISSUES.csv` with the buyer/customer handoff. A validation
pass means the customer CSVs are structurally and operationally reviewable; it
does not replace legal approval, contact-basis proof, suppression proof, live
schema/RLS proof, customer-access verification, or the explicit first-wave
go/no-go decision.

After validation, build a non-mutating import/staging plan before any live
database write. This turns the filled CSVs into reviewable tenant/module,
partner-scope, campaign, source-run, suppression, and message staging rows
without touching Supabase:

```bash
python3 platform/homepilot_first_campaign_import_plan.py \
  --out-dir /tmp/homepilot_first_campaign_import_plan \
  --template-pack /tmp/homepilot_release_pack/market_readiness/customer_input_templates.json \
  --input-dir /path/to/customer-filled-templates \
  --release-label production-candidate \
  --expected-partners 10
```

Archive `FIRST_CAMPAIGN_IMPORT_PLAN.md` and
`FIRST_CAMPAIGN_STAGING_ROWS.csv` with the handoff. The generated plan is an
operator/IT/legal review surface only: it does not authorize outreach, partner
portal access, live imports, or campaign activation until live schema/RLS,
customer-access proof, customer go/no-go, and source/suppression review are
archived.

Then build the final first-wave launch gate. This combines the validation,
staging plan, approval lanes, live proof, and explicit customer go/no-go into
one reviewable decision before outreach:

```bash
python3 platform/homepilot_first_wave_launch_gate.py \
  --out-dir /tmp/homepilot_first_wave_launch_gate \
  --input-validation /tmp/homepilot_first_campaign_import_plan/first_campaign_input_validation.json \
  --import-plan /tmp/homepilot_first_campaign_import_plan/first_campaign_import_plan.json \
  --live-readiness /tmp/homepilot_live_readiness/live_readiness.json \
  --release-label production-candidate
```

Archive `FIRST_WAVE_LAUNCH_GATE.md` and
`FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv`. A blocked decision is expected until
live schema/RLS/customer-access proof and explicit customer go/no-go are
present; it is useful launch evidence, not a failed generation.

After the launch gate, build the first-wave database handoff. It turns the
staging plan into customer-IT review files and only emits executable review SQL
when `launch_authorized=true`; otherwise `FIRST_WAVE_DATABASE_REVIEW.sql` is
comment-only and contains no DML:

```bash
python3 platform/homepilot_first_wave_database_handoff.py \
  --out-dir /tmp/homepilot_first_wave_database_handoff \
  --input-validation /tmp/homepilot_first_campaign_import_plan/first_campaign_input_validation.json \
  --import-plan /tmp/homepilot_first_campaign_import_plan/first_campaign_import_plan.json \
  --launch-gate /tmp/homepilot_first_wave_launch_gate/first_wave_launch_gate.json \
  --release-label production-candidate
```

Archive `FIRST_WAVE_DATABASE_HANDOFF.md`,
`FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv`,
`FIRST_WAVE_DATABASE_REVIEW_ROWS.csv`, and
`FIRST_WAVE_DATABASE_REVIEW.sql` with the handoff. Partner memberships remain
deferred until real Supabase Auth user IDs exist; property target rows remain
deferred until the approved property file is parsed and suppression is applied.

Then build the partner Auth mapping pack. It gives customer IT a fillable
mapping template for each approved partner, validates Supabase Auth UUIDs,
flags duplicates or raw contact references, and keeps membership SQL
comment-only until the launch gate is authorized and every mapping is complete:

```bash
python3 platform/homepilot_partner_auth_mapping.py \
  --out-dir /tmp/homepilot_partner_auth_mapping \
  --import-plan /tmp/homepilot_first_campaign_import_plan/first_campaign_import_plan.json \
  --launch-gate /tmp/homepilot_first_wave_launch_gate/first_wave_launch_gate.json \
  --release-label production-candidate \
  --expected-partner-count 10
```

Archive `PARTNER_AUTH_MAPPING.md`, `PARTNER_AUTH_MAPPING_TEMPLATE.csv`,
`PARTNER_AUTH_MAPPING_ISSUES.csv`, and `PARTNER_MEMBERSHIP_REVIEW.sql`.
Do not paste raw emails, phone numbers, passwords, JWTs, or service keys into
the mapping CSV; use the agreed secret channel and store only the real
Supabase Auth `user_id` UUID plus a secret reference.

Then reconcile the reviewed partner Auth mapping with the account-access plan
and customer-access verification report. This catches the practical failure
case where a partner is mapped in one place but not covered by planned
membership rows or live access probes:

```bash
python3 platform/homepilot_partner_access_reconciliation.py \
  --out-dir /tmp/homepilot_partner_access_reconciliation \
  --partner-auth-mapping /tmp/homepilot_partner_auth_mapping/partner_auth_mapping.json \
  --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json \
  --customer-access-verification /tmp/homepilot_customer_access_verification/customer_access_verification.json \
  --release-label production-candidate
```

Archive `PARTNER_ACCESS_RECONCILIATION.md`,
`PARTNER_ACCESS_RECONCILIATION_MATRIX.csv`, and
`PARTNER_ACCESS_RECONCILIATION_ISSUES.csv` with the launch evidence.
Production partner access is still blocked unless reconciliation status is
`partner_access_reconciled` and the underlying customer-access report has
`production_verified: true`.

Use `LIVE_LAUNCH_CONTROL_ROOM.md` and `LIVE_LAUNCH_ACTION_BOARD.csv` from the
market-readiness pack as the final shared launch-room view before live commands.
They combine live-input tasks, production-proof blockers, first-wave blockers,
owners, evidence references, and env var names without storing secret values. A
`blocked_until_live_inputs`, `blocked_until_live_proof`, or
`blocked_until_partner_auth_mapping` status is expected until secrets are
configured through the approved channel, partner Auth/membership/customer-access
evidence aligns, and live reports prove `production_verified=true`.

The generated market-readiness data room also includes
`MARKET_READY_GAP_AUDIT.md`, `MARKET_READY_REQUIREMENTS.csv`,
`FIRST_WAVE_DATABASE_HANDOFF.md`, `FIRST_WAVE_DATABASE_REVIEW_ROWS.csv`,
`FIRST_WAVE_DATABASE_REVIEW.sql`, `PARTNER_AUTH_MAPPING.md`,
`PARTNER_MEMBERSHIP_REVIEW.sql`, `PARTNER_ACCESS_RECONCILIATION.md`,
`PARTNER_ACCESS_RECONCILIATION_MATRIX.csv`, and
`PARTNER_ACCESS_RECONCILIATION_ISSUES.csv` as derived requirements and database-review
evidence. It also includes `CUSTOMER_SIGNOFF_RECONCILIATION.md`,
`CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv`, and
`CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv` as the decision-review layer that
separates buyer-ready artefacts from signed customer approval, first-wave
go/no-go, commercial terms, support acknowledgement, partner-access signoff,
public-data import approval, and live proof. It also includes
`CUSTOMER_SIGNOFF_INTAKE.md` and
`CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv` so customer success or DAW can record
safe approval references without storing raw signatures, personal contact data,
or secrets in the portable data room. The template can satisfy controlled
customer decision keys, but it cannot override live schema/RLS/customer-access
proof, partner-access reconciliation, or public-data reconciliation. It also includes
`EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md`
and `example_completed_customer_inputs/*.csv` as synthetic DAW-style happy-path
examples for demos and onboarding. Those examples show how correct inputs pass
validation with `customer_inputs_ready` and produce a 10-partner staging plan
plus launch gate while first-wave launch remains blocked until live proof and
customer go/no-go; they are not customer approval or production data.

Use `CUSTOMER_ACCEPTANCE_PLAN.md` and `ACCEPTANCE_CHECKLIST.csv` from the same
`market_readiness/` directory as the buyer-review signoff surface. Use
`CUSTOMER_ROLLOUT_PLAN.md` and `ROLLOUT_WORKSTREAMS.csv` as the practical
implementation layer: RACI roles, customer inputs, HomePilot actions, training,
and 30/60/90-day success checks. Use `PROCUREMENT_SECURITY_REVIEW.md`,
`SECURITY_QUESTIONNAIRE.csv`, and `PROCUREMENT_RISK_REGISTER.csv` as the compact
enterprise vendor-review layer for procurement, security, legal, and risk
owners. Use `SUPPORT_SLA_PLAN.md`, `SUPPORT_ESCALATION_MATRIX.csv`, and
`INCIDENT_RESPONSE_PLAYBOOK.md` as the operational support layer: priority tiers,
draft response targets, escalation triggers, and incident response steps. Use
`CUSTOMER_PILOT_PROPOSAL.md`, `PILOT_SCOPE_CHECKLIST.csv`, and
`COMMERCIAL_ASSUMPTIONS.csv` as the buyer-review proposal layer for the first
paid pilot; it is not a signed contractual offer. Use
`CUSTOMER_TRAINING_GUIDE.md`, `TRAINING_SESSION_PLAN.csv`, and
`ROLE_CHEATSHEET.csv` as the adoption layer for executives, DAW/network
managers, partner renovators, IT/security, customer success, and operators.
Use `CUSTOMER_VALUE_REALIZATION_PLAN.md`, `VALUE_REALIZATION_METRICS.csv`, and
`EXECUTIVE_DECISION_LOG.csv` as the value-realization layer: outcome tracks,
campaign KPIs, response-rate denominator guardrails, tenant-private value
metrics, and executive gates for buyer review, live launch, first campaign, and
scale decisions.
Use `CUSTOMER_MODULE_EXPANSION_PLAN.md`, `MODULE_VALUE_MATRIX.csv`, and
`EXPANSION_DECISION_TREE.csv` as the multi-module expansion layer: code-backed
module catalog, buyer questions, module metrics, expansion triggers, public-data
candidates, and tenant/module/partner access guardrails across FacadePilot,
WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, and DrivewayPilot.
Use `PUBLIC_DATA_SOURCE_REGISTER.md`, `PUBLIC_DATA_SOURCE_MATRIX.csv`,
`BLOCKED_DATA_REGISTER.csv`, `ATTRIBUTION_REQUIREMENTS.csv`,
`PUBLIC_DATA_PRODUCTION_INTAKE.md`, `PUBLIC_DATA_APPROVAL_CHECKLIST.csv`,
`PUBLIC_DATA_RECONCILIATION.md`,
`PUBLIC_DATA_RECONCILIATION_MATRIX.csv`, and
`PUBLIC_DATA_RECONCILIATION_ISSUES.csv` as the public-data/legal-reuse layer:
official/open source candidates, dataset-level licence gates, blocked
owner/EPC/contact-scraping lanes, attribution rules, source-run provenance
requirements, approval owners, and reconciliation blockers. Production imports
require dataset-level licence/allowed-use approval, field allowlist, retrieval
metadata, transform version, source provenance, public-data reconciliation, and
live proof before any enriched field appears in a customer dashboard or export.
Use `CUSTOMER_SIGNOFF_RECONCILIATION.md` and its CSVs as the final customer
decision tracker before launch review; buyer-review-ready documents are not
customer approval until this matrix shows the relevant decisions signed or
explicitly accepted. Together they separate what is
already acceptable for buyer review from what remains blocked for live launch,
production, first campaign, optimization, commercial agreement, or
customer-specific legal/procurement/SLA review.

## Production Preflight

Before enterprise review, live launch, or final rollout, build one operator
preflight report:

```bash
python3 platform/homepilot_preflight.py \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --stage buyer_review \
  --out /tmp/homepilot_preflight_buyer.json
```

For live launch, require the Supabase environment:

```bash
python3 platform/homepilot_preflight.py \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --stage live_launch \
  --live \
  --out /tmp/homepilot_preflight_live.json
```

For production rollout, include the live launch report. Production is proven by
the launch report plus passing RLS probe, while readiness and due diligence
remain the local buyer/security evidence.

## Operational Status

After building readiness and due-diligence evidence, create an operator status
page for customer success and launch coordination:

```bash
python3 platform/homepilot_ops_status.py \
  --out-dir /tmp/homepilot_ops_status \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --release-label buyer-review-candidate \
  --stage buyer_review
```

The status pack writes `ops_status.json`, `STATUS_PAGE.md`, and
`OPS_RUNBOOK.md`. It keeps buyer-review readiness separate from live launch and
production proof.

## Release Evidence Bundle

For a customer/security handoff, package the evidence into one review directory:

```bash
python3 platform/homepilot_release_pack.py \
  --out-dir /tmp/homepilot_release_pack \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --release-label buyer-review-candidate \
  --stage buyer_review
```

The bundle writes `production_proof.json`, `PRODUCTION_PROOF.md`,
`release_audit.json`, `preflight_report.json`, `artifact_index.json`,
`RELEASE_NOTES.md`, `HANDOFF_CHECKLIST.md`, the `market_readiness/`
HTML scorecard/data-room files, live launch control room/action board,
live-proof execution plan/evidence map/guarded command script,
acceptance, rollout, procurement/security, support/incident-response, pilot
proposal, customer input template, first-campaign input validation artifacts,
partner Auth mapping, partner-access reconciliation, and a schema deployment
manifest/runbook. It may be buyer-review ready while still marking production
`no_go` until live schema, RLS launch, and customer access reports prove
production isolation.

## Production Proof Manifest

When you need a standalone evidence manifest, run:

```bash
python3 platform/homepilot_production_proof.py \
  --out-dir /tmp/homepilot_production_proof \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --schema-verification-report /tmp/homepilot_schema_verification_live/schema_verification.json \
  --launch-report /tmp/homepilot_launch_live/launch_report.json \
  --customer-access-report /tmp/homepilot_customer_access_verification_live/customer_access_verification.json
```

The manifest records SHA-256 hashes, evidence age, missing live proof, release
blockers, and a redacted secret scan. It makes the handoff tamper-evident, but
production is still `go` only after the live readiness, schema, launch/RLS, and
customer access reports pass.

## Release Go/No-Go Audit

Before customer rollout, create the final decision report:

```bash
python3 platform/homepilot_release_audit.py \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --schema-verification-report /tmp/homepilot_schema_verification_live/schema_verification.json \
  --launch-report /tmp/homepilot_launch_live/launch_report.json \
  --customer-access-report /tmp/homepilot_customer_access_verification_live/customer_access_verification.json \
  --out /tmp/homepilot_release_audit.json \
  --require-production
```

Production is `go` only when readiness and due diligence are clean, live
readiness is `ready`, the live schema verification report proves the deployed
database contract, the live launch report proves `production_verified: true`
with a passing RLS probe, and the customer access verification report proves
planned invitee access with `production_verified: true`. For producer networks,
partner portal access also requires partner-access reconciliation to prove the
same partner Auth users are present in membership rows and customer-access
probe identities.


## Live RLS Probe

Run a local dry-run first:

```bash
python3 platform/homepilot_launch.py rls-fixture \
  --dry-run \
  --out-dir /tmp/homepilot_launch_dry_run
```

Then run the live gate with real Supabase environment variables:

```bash
export HOMEPILOT_SUPABASE_URL='https://PROJECT.supabase.co'
export HOMEPILOT_SUPABASE_SERVICE_KEY='service-role-key'
export HOMEPILOT_SUPABASE_ANON_KEY='anon-key'
export HOMEPILOT_SUPABASE_DB_URL='postgresql://postgres:password@db.PROJECT.supabase.co:5432/postgres'
export HOMEPILOT_RLS_WINDOW_PASSWORD='temporary-strong-password-1'
export HOMEPILOT_RLS_FACADE_PASSWORD='temporary-strong-password-2'
export HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD='temporary-strong-password-3'
```

Before calling the live mutating steps, generate the redacted live readiness
doctor report. It lists missing Supabase, fixture, and planned customer-access
credentials without writing secret values:

```bash
python3 platform/homepilot_live_readiness.py \
  --out-dir /tmp/homepilot_live_readiness \
  --readiness-report /tmp/homepilot_readiness_market_ready/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_market_ready/due_diligence_report.json \
  --account-access-plan /tmp/homepilot_readiness_market_ready/account_access_smoke/account_access_plan.json
```

If the doctor returns `action_required`, turn the missing inputs into an owner
checklist before the next launch meeting:

```bash
python3 platform/homepilot_live_launch_request.py \
  --out-dir /tmp/homepilot_live_launch_request \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --account-access-plan /tmp/homepilot_readiness_market_ready/account_access_smoke/account_access_plan.json \
  --release-label production-candidate
```

```bash
python3 platform/homepilot_launch.py rls-fixture \
  --out-dir /tmp/homepilot_launch_live
```

The launch report and RLS probe report must both be `pass`. A zero-row pass is not enough for production; the fixture seeds at least one property, assessment, campaign target, interaction, response insight, and export log for every active module under review.

Before any live customer import, archive a recovery pack for the payload. The launch runner also writes `cleanup_plan.json` and `cleanup_plan.sql`. Archive `launch_report.json` and `rls_probe_report.json` first; then review and apply cleanup SQL to remove only tenants marked with `settings.fixture = homepilot_live_fixture`.

## Customer Value Gates

The dashboard should answer these questions without extra explanation:

- Which properties should we contact first?
- Which city, segment, or territory should the next campaign batch target?
- Why are these properties interesting?
- Can sales explain each prioritized property without exposing internal/raw scoring data?
- What is the boardroom-level business case and action plan for this tenant/module scope?
- Which renovation module is the best entry point?
- What did each campaign learn?
- Which objections or non-responses are emerging?
- Which controlled experiment should the next campaign batch run?
- What can the sales team export today?
- What business case, expected revenue range, and sales capacity does the next batch imply?
- Is the dataset complete enough for maps, scoring, evidence review, and sales follow-up?
- Which insights are private to this customer, and which are safe as aggregate benchmarks?
- Are cross-customer learnings aggregate-only, thresholded, and free of tenant/address/property identifiers?
- Are contact and lead claims framed as renovation opportunities unless actual response evidence proves intent?

## Privacy Gates

Before scaling beyond demos:

- Add a retention policy for contacted properties and raw evidence media.
- Keep `contact_basis`, `source_provenance`, `contact_channel`, `opt_out_method`, and retention review metadata on contacted campaign targets.
- Separate raw evidence paths from customer-facing media URLs.
- Keep only aggregate benchmarks in `homepilot_platform_benchmarks`.
- Build benchmarks with `homepilot_benchmarks.py`; rows below the minimum cohort size are skipped.
- Enforce minimum cohort sizes for benchmarks; the platform default and database constraint are 10+ samples.
- Never include tenant IDs, property IDs, addresses, campaign IDs, or free-form response detail in benchmark rows.
- Never use ready-to-buy, ready-to-hire, requested-quote, or submitted-request language unless a response interaction proves it.
- Log exports in `homepilot_exports`; customer packages now write `data/export_log.json` for import or audit review.
- Run an export bundle smoke test for every customer handoff.
- Generate a per-property delete plan with `homepilot_privacy.py delete-plan` before executing production deletes.
- Run `homepilot_retention.py` on campaign payloads; failures block customer handoff until retention schedules or delete plans are reviewed.
- Generate or retain fixture cleanup plans after every live RLS launch test; never leave synthetic fixture tenants in production longer than needed.
- Review campaign-level `homepilot_response_insights` separately because they can summarize multiple properties.

## Pilot Expansion Gates

Each new pilot must add:

- A module definition in `homepilot_platform.py`.
- Metric definitions with visibility labels.
- A product access matrix entry for dashboard, export, benchmark, and internal metric visibility.
- An adapter that emits canonical `properties`, `assessments`, and optional `campaign_targets`.
- Tests that prove the module appears in snapshots only when enabled.
- One dashboard story: priority reason, next action, export column, and second-brain edge.
