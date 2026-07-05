# Importing Pilot Data

HomePilot imports are staged so tenants, modules, campaign data, responses, dashboards, and exports stay repeatable.

1. Onboard the customer tenant and enabled modules.
2. Convert pilot-specific data into a canonical HomePilot JSON payload.
3. Validate/import that payload into Supabase.
4. Merge campaign responses over time.
5. Generate dashboard snapshots or export bundles.

## Operational Health Check

Before importing or packaging customer data, run:

```bash
python3 platform/homepilot_healthcheck.py --out /tmp/homepilot_healthcheck.json
```

The local healthcheck verifies required files, dashboard SQL contracts, RLS
schema markers, client assets, and environment shape without mutating Supabase.

## Enterprise Readiness Evidence

For a local preflight bundle before customer or security review:

```bash
python3 platform/homepilot_readiness.py build \
  --out-dir /tmp/homepilot_readiness_pack \
  --run-qa
```

The evidence pack contains a readiness report, launch dry-run evidence,
customer package smoke, cleanup SQL, data quality, compliance, and privacy-safe
benchmark smoke. It does not replace the live Supabase RLS launch gate.

## Buyer Due-Diligence Pack

After building a readiness report, package buyer-facing evidence without raw
customer data:

```bash
python3 platform/homepilot_due_diligence.py \
  --out-dir /tmp/homepilot_due_diligence_pack \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --module windowpilot
```

The pack includes an executive summary, access matrices, source-file hashes, the
readiness report, and a redaction scan. It remains `local_ready` by design;
production is proven separately by the live launch report and RLS probe.

## Schema Deployment Manifest

Before applying Supabase SQL, build a release manifest:

```bash
python3 platform/homepilot_deployment.py \
  --out-dir /tmp/homepilot_deployment_pack \
  --release-label production-candidate
```

The manifest records SQL apply order, file hashes, required contract markers,
and post-apply checks. Archive it with readiness, preflight, and launch
evidence.

## Production Preflight

Build one operator preflight before review, live launch, or rollout:

```bash
python3 platform/homepilot_preflight.py \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --stage buyer_review \
  --out /tmp/homepilot_preflight_buyer.json
```

Use `--stage live_launch --live` to require Supabase environment and REST
reachability before running the live RLS fixture.

## Release Go/No-Go Audit

After readiness and due diligence, create the final release decision:

```bash
python3 platform/homepilot_release_audit.py \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --out /tmp/homepilot_release_audit.json
```

Without live readiness, live schema verification, live launch, and customer
access verification reports, buyer review can be `go` while production remains
`no_go`. Production can become `go` only when all live proof artifacts pass.


## Tenant Onboarding

Create one tenant with only the modules the customer paid for:

```bash
python3 platform/homepilot_onboarding.py build   --name "Window Customer"   --slug window-customer   --module windowpilot   --member 11111111-1111-4111-8111-111111111111:owner   --out /tmp/homepilot_window_customer_onboarding.json

python3 platform/homepilot_onboarding.py --dry-run import-json   --json /tmp/homepilot_window_customer_onboarding.json
```

`--slug` is converted into a deterministic UUID. Use the same slug as `--tenant-id` in pilot imports when you do not have a real Supabase tenant UUID yet. Passing a real UUID keeps it unchanged.

## Convert FacadePilot CSV

```bash
python3 platform/homepilot_platform.py convert-facade-csv   --csv ../FacadePilot/facadepilot_leads_24107_scored.csv   --tenant-id window-customer   --campaign-id facade-leuven-q3   --out /tmp/homepilot_facade_records.json
```

The adapter emits:

- `campaigns`
- `properties`
- `assessments`
- `campaign_targets`
- `interactions`
- `response_insights`

Campaign and tenant IDs are database-ready UUIDs even when the input uses human slugs.

## Generic Module CSV

WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future pilots can use one adapter when their CSV contains canonical metric columns:

```bash
python3 platform/homepilot_sync.py pilot-csv \
  --module windowpilot \
  --csv /tmp/windowpilot_leads.csv \
  --tenant-id window-customer \
  --campaign-id window-q3 \
  --campaign-name "Window Q3" \
  --out /tmp/homepilot_window_records.json
```

Common columns:

- `address` or `adres`
- `city`, `postcode`, `lat`, `lon`
- module score, for example `window_opportunity_score` or generic `score`
- `grade`
- any metric key from `homepilot_platform.py` for that module
- `status` and `next_action` for campaign targets
- evidence columns such as `streetview_url`, `render_url`, `photo_url`, `satellite_url`

## Validate Payload

```bash
python3 platform/homepilot_store.py summary-json   --json /tmp/homepilot_facade_records.json
```

## Data Quality Audit

Before a live import or customer handoff, audit usefulness beyond structural
validity:

```bash
python3 platform/homepilot_data_quality.py \
  --json /tmp/homepilot_facade_records.json \
  --out /tmp/homepilot_data_quality.json
```

The audit reports score coverage, geocode coverage, evidence coverage, campaign
target coverage, response rate, and duplicate counts. `fail` blocks launch;
`warn` means the dataset is importable but needs review before a customer sees
it.

## Compliance Audit

Before activating outreach or sharing campaign claims with a customer, audit
the outreach metadata and claim language:

```bash
python3 platform/homepilot_compliance.py \
  --json /tmp/homepilot_facade_records.json \
  --out /tmp/homepilot_compliance.json
```

This is an operational gate, not legal advice. `fail` blocks campaign use until
the dataset has source provenance, a reviewed contact basis, opt-out handling,
and no unproven ready-to-buy or ready-to-hire claims. `warn` means the records
are structurally usable but need review before customer handoff.

## Dry-Run Import

```bash
python3 platform/homepilot_store.py --dry-run import-json   --json /tmp/homepilot_facade_records.json
```

## Import Recovery Pack

Before a live import, archive a recovery pack for the exact payload:

```bash
python3 platform/homepilot_recovery.py recovery-pack \
  --payload /tmp/homepilot_records.json \
  --out-dir /tmp/homepilot_recovery_pack \
  --include-properties
```

The pack writes `backup_manifest.json`, `rollback_plan.json`,
`rollback_plan.sql`, `RECOVERY_RUNBOOK.md`, and `recovery_pack.json`. The SQL is
review-only until an operator confirms tenant id, module keys, affected records,
and whether property deletion is intended.

## Live Import

Create `HomePilot/.env` from `.env.example`, then run:

```bash
python3 platform/homepilot_store.py check
python3 platform/homepilot_onboarding.py import-json   --json /tmp/homepilot_window_customer_onboarding.json
python3 platform/homepilot_store.py import-json   --json /tmp/homepilot_facade_records.json
```

The import uses the service-role key. Customer access is handled by RLS for authenticated users.

After a live import, prove customer JWT isolation with the launch runner:

```bash
python3 platform/homepilot_launch.py rls-fixture \
  --dry-run \
  --out-dir /tmp/homepilot_launch_dry_run

python3 platform/homepilot_launch.py rls-fixture \
  --out-dir /tmp/homepilot_launch_live \
  --window-email window.rls@example.com \
  --window-password 'temporary-strong-password-1' \
  --facade-email facade.rls@example.com \
  --facade-password 'temporary-strong-password-2'
```

The live runner creates or reuses Supabase Auth test users, imports the two-tenant fixture, runs the RLS probe, and writes `/tmp/homepilot_launch_live/launch_report.json`. The probe fails when a user can read another tenant or a disabled module. Keep the JSON report as launch evidence.

The same folder contains `cleanup_plan.json` and `cleanup_plan.sql`. Apply cleanup only after the launch and probe reports are archived; the SQL deletes fixture tenants only when the tenant settings still contain the live fixture marker.

## Import Customer Responses

After a campaign runs, add reactions or no-response updates from a spreadsheet:

```bash
python3 platform/homepilot_responses.py   --payload /tmp/homepilot_facade_records.json   --csv /tmp/homepilot_responses.csv   --out /tmp/homepilot_facade_records_with_responses.json
```

Useful response CSV columns:

- `property_id` or `address`
- `module_key`
- `status`: `responded`, `appointment`, `no_response`, `rejected`, ...
- `interaction_type`: `call`, `meeting`, `note`, `status_change`, ...
- `response_status`: `interested`, `not_interested`, `later`, ...
- `detail`
- `objection_code`
- `occurred_at`
- `next_action`

The merger updates `campaign_targets` and appends deterministic interaction records, then validates the payload before writing it.

## Build Customer Dashboard Snapshot

```bash
python3 platform/homepilot_snapshot.py   --json /tmp/homepilot_facade_records_with_responses.json   --tenant-name "Customer Name"   --tenant-slug customer-name   --module facadepilot   dashboard-js   --out client/dashboard-data.js
```

## Customer Export Bundle

```bash
python3 platform/homepilot_export.py   --json /tmp/homepilot_facade_records_with_responses.json   --tenant-name "Customer Name"   --tenant-slug customer-name   --module facadepilot   --out-dir /tmp/homepilot_customer_export
```

The bundle contains:

- `properties.csv`
- `assessments.csv`
- `interactions.csv`
- `recommendations.csv`
- `homepilot_export.xlsx` when `openpyxl` is available
- `manifest.json`

## Access Audit

Before sharing a dashboard snapshot or export bundle with a customer, run:

```bash
python3 platform/homepilot_access_audit.py \
  --onboarding /tmp/homepilot_customer_onboarding.json \
  --snapshot /tmp/homepilot_dashboard_snapshot.json \
  --export-dir /tmp/homepilot_customer_export
```

The report fails if a disabled module appears in the payload, snapshot, export
CSV files, or manifest.

## Customer Package

Build one customer-ready handoff folder with static dashboard, dashboard data, CSV/XLSX exports, access audit, export log, audit trail, manifest, and optional zip:

```bash
python3 platform/homepilot_customer_package.py \
  --onboarding /tmp/homepilot_customer_onboarding.json \
  --payload /tmp/homepilot_records_with_responses.json \
  --tenant-name "Customer Name" \
  --tenant-slug customer-name \
  --out-dir /tmp/homepilot_customer_package \
  --zip
```

The package derives allowed modules from onboarding and writes
`data/scoped_payload.json` before building the dashboard and exports. Use
`--module` only to intentionally override onboarding for a manual review. Use
`--audit-payload` to include the scoped payload in the same access audit as the
dashboard snapshot and export bundle.

The package also writes `data/export_log.json`, a row shaped for `homepilot_exports`, plus `data/audit_events.json` and `data/audit_trail_report.json` for package/export/access-audit traceability. To import the export log with the same payload:

```bash
python3 platform/homepilot_store.py --dry-run import-json \
  --json /tmp/homepilot_records_with_export_log.json
```

## Privacy Delete Plan
## Retention Lifecycle Audit

Before running long-lived campaigns or customer handoffs, audit retention
metadata:

```bash
python3 platform/homepilot_retention.py \
  --json /tmp/homepilot_records_with_responses.json \
  --out /tmp/homepilot_retention_report.json
```

The audit does not delete data. It identifies contacted records that need a
retention schedule, review, or a `homepilot_privacy.py delete-plan`.


Before deleting a contacted property, generate a reviewable JSON and SQL plan:

```bash
python3 platform/homepilot_privacy.py delete-plan \
  --payload /tmp/homepilot_records_with_responses.json \
  --property-id prop_example \
  --out /tmp/homepilot_delete_plan.json \
  --sql-out /tmp/homepilot_delete_plan.sql
```

The SQL deletes property-level interactions, campaign targets, assessments, media, and the property row in that order. Campaigns and response insights stay out of the automatic property plan because they can contain aggregate campaign learnings.

## Privacy-Safe Platform Benchmarks

Customer-specific learnings stay tenant-scoped. Cross-customer learnings may be
published only as aggregate benchmark rows after the minimum cohort threshold is
met:

```bash
python3 platform/homepilot_benchmarks.py \
  --json /tmp/customer_a_payload.json \
  --json /tmp/customer_b_payload.json \
  --min-sample-size 10 \
  build \
  --out /tmp/homepilot_benchmarks.json

python3 platform/homepilot_benchmarks.py \
  --json /tmp/customer_a_payload.json \
  --json /tmp/customer_b_payload.json \
  --min-sample-size 10 \
  import-json \
  --dry-run \
  --out /tmp/homepilot_benchmarks.json
```

The benchmark builder skips small cohorts and validates that benchmark rows do
not contain tenant IDs, property IDs, addresses, campaign IDs, or free-form
interaction detail.
