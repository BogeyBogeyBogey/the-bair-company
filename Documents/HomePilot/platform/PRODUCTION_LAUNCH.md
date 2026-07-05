# HomePilot Production Launch Checklist

Use this checklist after buyer review is green and before any paying customer
gets live access.

## 1. Configure Environment

Copy `.env.example` to `.env` and replace all placeholder values:

```bash
HOMEPILOT_SUPABASE_URL=https://PROJECT.supabase.co
HOMEPILOT_SUPABASE_SERVICE_KEY=service-role-key
HOMEPILOT_SUPABASE_ANON_KEY=anon-key
HOMEPILOT_SUPABASE_DB_URL=postgresql://postgres:password@db.PROJECT.supabase.co:5432/postgres
HOMEPILOT_RLS_WINDOW_PASSWORD=temporary-strong-password-1
HOMEPILOT_RLS_FACADE_PASSWORD=temporary-strong-password-2
HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD=temporary-strong-password-3
```

Do not commit `.env`, service-role keys, anon keys, fixture passwords, customer
JWTs, or generated probe configs that contain real credentials.

## 2. Verify Local And Live Health

```bash
python3 platform/homepilot_healthcheck.py \
  --live \
  --require-live \
  --out /tmp/homepilot_healthcheck_live.json
```

The healthcheck must pass before live launch. Missing environment values,
placeholder keys, or Supabase REST failures block launch.

## 3. Build Redacted Live Readiness Evidence

Before running a live cutover, generate the redacted credential/evidence
checklist. It reports which Supabase, fixture, and customer-access credentials
are present without writing any secret values:

```bash
python3 platform/homepilot_live_readiness.py \
  --out-dir /tmp/homepilot_live_readiness \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json
```

Production requires `live_readiness.json` status `ready` before the live cutover
command is executed.

## 3b. Build The Live Launch Request Pack

If live readiness is `action_required`, convert the missing inputs into a
customer/operator request pack before asking anyone for credentials:

```bash
python3 platform/homepilot_live_launch_request.py \
  --out-dir /tmp/homepilot_live_launch_request \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json \
  --release-label production-candidate
```

Share `LIVE_LAUNCH_REQUEST.md`, `LIVE_LAUNCH_CHECKLIST.csv`, and
`LIVE_LAUNCH_REQUEST_EMAIL.txt` for ownership and next actions. Use
`live_launch.env.template` only as a local/secret-manager template, never with
real values committed or sent by email.

## 3c. Build The Live Proof Execution Plan

After buyer review and live-launch input assignment, build the guarded live
proof plan. This is the operator route that connects buyer-review evidence to
the actual production proof sequence without storing secrets or writing live
data by itself:

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

Review `LIVE_PROOF_EXECUTION_PLAN.md`, `LIVE_PROOF_EVIDENCE_MAP.csv`, and
`LIVE_PROOF_COMMANDS.sh` before live work starts. The command script is guarded
by `HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof`; run it only after customer/IT
signoff and secure environment loading. A generated plan is not production
proof. Production still requires live schema verification, live RLS launch, and
customer access verification with `production_verified=true`.

## 4. Build And Review Deployment Evidence

```bash
python3 platform/homepilot_deployment.py \
  --out-dir /tmp/homepilot_deployment_pack \
  --release-label production-candidate
```

Review `/tmp/homepilot_deployment_pack/SQL_APPLY_PLAN.md` and
`/tmp/homepilot_deployment_pack/apply.sql` with the operator/customer IT owner.
The pack also writes `post_apply_verification.sql` for a quick smoke check.

Apply SQL in this order, or use the generated `apply.sql` bundle:

```text
platform/supabase_schema.sql
platform/dashboard_views.sql
```

Then seed the module catalog:

```bash
python3 platform/homepilot_store.py seed-modules
```

## 5. Verify The Live Schema Contract

After applying SQL, verify that the live database actually exposes the expected
tables, columns, partner-aware functions, security-invoker views, and RLS
policies:

```bash
python3 platform/homepilot_live_schema_verification.py \
  --out-dir /tmp/homepilot_schema_verification_live \
  --live
```

Production requires:

- `schema_verification.json` status `pass`.
- `production_verified: true`.
- `contract_status: pass`.
- `live_status: pass`.

## 6. Run Live RLS Launch Gate

Use real Supabase Auth test users and strong temporary passwords from
environment variables, so they do not appear in shell history:

```bash
python3 platform/homepilot_launch.py rls-fixture \
  --out-dir /tmp/homepilot_launch_live
```

Production requires:

- `launch_report.json` status `pass`.
- `production_verified: true`.
- `rls_probe_report.json` status `pass` with real customer JWTs.
- `cleanup_plan.json` and `cleanup_plan.sql` ready for review.

## 7. Verify Planned Customer Access

Use the reviewed account access plan from readiness or the customer-specific
account access pack. Set the token/password environment variables named in the
generated probe contract; do not store real credentials in JSON or git.

```bash
python3 platform/homepilot_customer_access_verification.py \
  --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json \
  --out-dir /tmp/homepilot_customer_access_verification_live
```

Production requires:

- `customer_access_verification.json` status `pass`.
- `production_verified: true`.
- `customer_access_rls_probe_report.json` status `pass` for planned invitees.
- The report guardrail `secrets_written: false`.

For producer networks such as DAW plus partner renovators, reconcile customer
access with the partner Auth mapping before enabling partner portal access:

```bash
python3 platform/homepilot_partner_access_reconciliation.py \
  --out-dir /tmp/homepilot_partner_access_reconciliation \
  --partner-auth-mapping /tmp/homepilot_partner_auth_mapping/partner_auth_mapping.json \
  --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json \
  --customer-access-verification /tmp/homepilot_customer_access_verification_live/customer_access_verification.json \
  --release-label production-candidate
```

Production partner access requires `partner_access_reconciliation.json` status
`partner_access_reconciled`; blocked statuses are launch evidence, not approval.

## 8. Build Final Release Evidence

You can run the full cutover evidence chain in one controlled sequence. This
does not apply SQL automatically; it verifies the schema after SQL is applied,
checks live readiness before mutating steps, seeds modules, runs the live RLS
fixture, verifies planned customer access, and writes a final release audit:

```bash
python3 platform/homepilot_production_cutover.py \
  --out-dir /tmp/homepilot_cutover_live \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json \
  --release-label production-candidate \
  --live
```

Production requires `cutover_report.json` status `production_verified`.
When live inputs are missing, the cutover writes `live_readiness.json`,
`LIVE_READINESS.md`, and `live_cutover.env.template` before skipping
seed/import/probe steps. Run `homepilot_live_launch_request.py` against that
report to create the owner checklist and safe email draft for the missing
Supabase, fixture, and customer-access inputs.

If you run the final evidence steps manually instead, use:

```bash
python3 platform/homepilot_release_pack.py \
  --out-dir /tmp/homepilot_release_pack \
  --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json \
  --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json \
  --live-readiness-report /tmp/homepilot_live_readiness/live_readiness.json \
  --schema-verification-report /tmp/homepilot_schema_verification_live/schema_verification.json \
  --launch-report /tmp/homepilot_launch_live/launch_report.json \
  --customer-access-report /tmp/homepilot_customer_access_verification_live/customer_access_verification.json \
  --release-label production-candidate \
  --stage production_rollout \
  --live
```

The release pack writes `production_proof.json`, `PRODUCTION_PROOF.md`, and the
`market_readiness/` scorecard/data-room files. Share
`market_readiness/homepilot_boardroom_data_room.zip` for customer review; it
contains a portable `index.html`, `DATA_ROOM_MANIFEST.json`, copied evidence
files, relative links, local-path redaction, and SHA-256 checksums. Review the local
`LIVE_LAUNCH_CONTROL_ROOM.md` and `LIVE_LAUNCH_ACTION_BOARD.csv` first in the
launch-room meeting: they combine live-readiness tasks, production proof,
first-wave launch gates, owners, env var names, and missing evidence without
storing secret values. They are non-mutating and do not authorize outreach or
customer access; a blocked status is expected until the live schema, RLS launch,
and customer access reports show `production_verified=true`. Then review
`LIVE_PROOF_EXECUTION_PLAN.md`, `LIVE_PROOF_EVIDENCE_MAP.csv`, and
`LIVE_PROOF_COMMANDS.sh` as the guarded live-proof route; the command script
requires `HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof`, secure environment
values, and customer/operator signoff before use. Then review
`production_cutover/CUTOVER_RUNBOOK.md` and
`production_cutover/cutover_report.json` as the dry-run rehearsal; it must show
`production_verified=false` until the live sequence has actually passed. Then
review
`MARKET_READY_GAP_AUDIT.md` and `MARKET_READY_REQUIREMENTS.csv` to separate
buyer-review proof from live-launch, production, and first-wave blockers. Then
review `FIRST_WAVE_DATABASE_HANDOFF.md`,
`FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv`,
`FIRST_WAVE_DATABASE_REVIEW_ROWS.csv`, and
`FIRST_WAVE_DATABASE_REVIEW.sql`; blocked launch gates must leave the SQL file
comment-only with no executable DML. Then review `PARTNER_AUTH_MAPPING.md`,
`PARTNER_AUTH_MAPPING_TEMPLATE.csv`, `PARTNER_AUTH_MAPPING_ISSUES.csv`, and
`PARTNER_MEMBERSHIP_REVIEW.sql`; partner membership SQL must stay comment-only
until real Supabase Auth user UUIDs are mapped, the launch gate is authorized,
and live RLS/customer-access proof is archived. Then review
`PARTNER_ACCESS_RECONCILIATION.md`,
`PARTNER_ACCESS_RECONCILIATION_MATRIX.csv`, and
`PARTNER_ACCESS_RECONCILIATION_ISSUES.csv`; partner access remains blocked
until Auth mapping, membership rows, and customer-access probe identities agree.
Then review the local
`market-readiness.html`, `CUSTOMER_ACCEPTANCE_PLAN.md`,
`ACCEPTANCE_CHECKLIST.csv`, `CUSTOMER_ROLLOUT_PLAN.md`,
`ROLLOUT_WORKSTREAMS.csv`, `PROCUREMENT_SECURITY_REVIEW.md`,
`SECURITY_QUESTIONNAIRE.csv`, `PROCUREMENT_RISK_REGISTER.csv`,
`SUPPORT_SLA_PLAN.md`, `SUPPORT_ESCALATION_MATRIX.csv`,
`INCIDENT_RESPONSE_PLAYBOOK.md`, `CUSTOMER_PILOT_PROPOSAL.md`,
`PILOT_SCOPE_CHECKLIST.csv`, `COMMERCIAL_ASSUMPTIONS.csv`,
`CUSTOMER_TRAINING_GUIDE.md`, `TRAINING_SESSION_PLAN.csv`,
`ROLE_CHEATSHEET.csv`, `CUSTOMER_VALUE_REALIZATION_PLAN.md`,
`VALUE_REALIZATION_METRICS.csv`, `EXECUTIVE_DECISION_LOG.csv`,
`CUSTOMER_MODULE_EXPANSION_PLAN.md`, `MODULE_VALUE_MATRIX.csv`,
`EXPANSION_DECISION_TREE.csv`, `PUBLIC_DATA_SOURCE_REGISTER.md`,
`PUBLIC_DATA_SOURCE_MATRIX.csv`, `BLOCKED_DATA_REGISTER.csv`,
`ATTRIBUTION_REQUIREMENTS.csv`, `LIVE_LAUNCH_CONTROL_ROOM.md`,
`LIVE_LAUNCH_ACTION_BOARD.csv`, `MARKET_READY_GAP_AUDIT.md`,
`MARKET_READY_REQUIREMENTS.csv`, `LIVE_PROOF_EXECUTION_PLAN.md`,
`LIVE_PROOF_EVIDENCE_MAP.csv`, `LIVE_PROOF_COMMANDS.sh`,
`FIRST_WAVE_DATABASE_HANDOFF.md`,
`FIRST_WAVE_DATABASE_REVIEW_ROWS.csv`, `FIRST_WAVE_DATABASE_REVIEW.sql`,
`PARTNER_ACCESS_RECONCILIATION.md`,
`PARTNER_ACCESS_RECONCILIATION_MATRIX.csv`,
`PARTNER_ACCESS_RECONCILIATION_ISSUES.csv`,
`PUBLIC_DATA_RECONCILIATION.md`,
`PUBLIC_DATA_RECONCILIATION_MATRIX.csv`,
`PUBLIC_DATA_RECONCILIATION_ISSUES.csv`,
`CUSTOMER_SIGNOFF_RECONCILIATION.md`,
`CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv`,
`CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv`,
`CUSTOMER_SIGNOFF_INTAKE.md`,
`CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv`, and production proof before customer access is
enabled: artifact hashes must be present, launch owners must be assigned, the
rollout owners/training path must be agreed, role visibility must be
understood, value metrics and response-rate denominators must be agreed, module
expansion must preserve tenant/module scope, public-data imports must have
dataset-level licence/allowed-use approval, field allowlists, source-run
metadata, provenance, attribution, and public-data reconciliation,
procurement/security review questions, support escalations, and commercial
assumptions must have owners, partner Auth mappings must align with membership
rows and customer-access probes, customer signoff must distinguish review-ready
documents from signed approval, filled signoff evidence must contain safe
approval references only, technical proof must not be overridden by customer
signoff CSVs, the secret scan must be `pass`, and production
must remain `no_go` unless live readiness, schema verification, launch/RLS,
customer access proof, partner-access reconciliation, public-data
reconciliation, and customer signoff reconciliation all pass where those scopes
are used.

Then run the final production gate:

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

## 8. Cleanup After Evidence Is Archived

Only after launch evidence is archived, review and apply `cleanup_plan.sql` to
remove fixture tenants and Supabase Auth users marked as HomePilot live fixtures.
