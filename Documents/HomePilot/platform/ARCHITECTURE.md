# HomePilot Platform Architecture

The shared platform layer exists outside FacadePilot because FacadePilot is one
pilot module, not the owner of the customer database.

## Core Tables

```text
homepilot_tenants
homepilot_memberships
homepilot_modules
homepilot_tenant_modules
homepilot_properties
homepilot_property_media
homepilot_campaigns
homepilot_campaign_targets
homepilot_assessments
homepilot_interactions
homepilot_response_insights
homepilot_exports
homepilot_platform_benchmarks
```

`homepilot_properties` is the canonical house record. Module-specific facts live
in `homepilot_assessments`, keyed by `module_key`, so one property can safely
carry WindowPilot, FacadePilot, RoofPilot, and other pilot assessments at the
same time.

## Deployment Boundary

Schema deployment is tracked as evidence before production changes: `homepilot_deployment.py` hashes the SQL files, validates contract markers, records apply order, and lists post-apply checks. It does not mutate the database.

## Tenant And Module Boundary

Every customer-owned row carries `tenant_id`. Module-specific rows also carry
`module_key`. Database policies check both tenant membership and enabled module.
This gives one internal database while the customer experience remains a private
WindowPilot, FacadePilot, or multi-module workspace.

## Handoff Entitlement Boundary
## Metric Visibility Boundary

Module entitlements answer which modules a tenant may see. Metric visibility
answers which fields are safe on each surface. Customer dashboards, exports, and
packages expose `benchmarkable` plus `tenant_private` metrics. Aggregate
benchmark surfaces expose `benchmarkable` metrics only. Unknown, raw, debug,
model, prompt, token, and embedding metrics are treated as internal by default.


Production RLS remains the hard access boundary. Static handoffs add a local
boundary before presentation: `homepilot_entitlements.py` filters canonical
payloads to the onboarding tenant and enabled modules, removes module-disabled
records, and exposes properties only when an allowed assessment, target, or
interaction references them.

## Recovery Boundary

Recovery packs are local evidence artifacts, not automatic production actions. They hash the import payload, produce tenant-guarded rollback SQL in dependency order, and require operator review before any destructive SQL is executed.

## Benchmark Boundary

Private customer learnings stay tenant-scoped. Aggregate platform benchmarks
must be stored separately from raw customer rows and only after applying:

- no direct identifiers
- no address-level records
- minimum sample size, defaulting to 10+ samples
- regional generalization where needed
- no customer names or exact campaign content

## FacadePilot Adapter

The first adapter converts existing FacadePilot scored CSV rows into HomePilot
records:

```bash
python3 platform/homepilot_platform.py convert-facade-csv \
  --csv ../FacadePilot/facadepilot_leads_24107_scored.csv \
  --tenant-id TENANT_UUID \
  --campaign-id CAMPAIGN_UUID \
  --out /tmp/homepilot_facade_records.json
```

That conversion is intentionally non-destructive. It gives us a migration bridge
without breaking the current FacadePilot pipeline.
