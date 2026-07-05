# Dashboard Data Contracts

HomePilot has two dashboard paths:

1. Supabase read models for the production app.
2. Static snapshots for demos, audits, exports, and customer review links.

Both paths use the same tenant/module/property model.

## Supabase Views

Apply in this order:

```bash
supabase_schema.sql
dashboard_views.sql
```

The dashboard views are:

- `homepilot_property_intelligence`: one row per property assessment, enriched with campaign target and latest interaction.
- `homepilot_property_export`: Excel-friendly flat export view.
- `homepilot_property_public_enrichment`: property-linked public enrichment with source, licence, allowed use, attribution, confidence, and provenance.
- `homepilot_campaign_metrics`: campaign funnel and response metrics; `response_rate_pct` uses contacted records as denominator, while `target_response_rate_pct` preserves the all-target context.
- `homepilot_module_metrics`: module-level performance per tenant; response rates use the same contacted-record denominator.
- `homepilot_second_brain_edges`: graph edges for signal/property/campaign/reaction visuals.

The views are created with `security_invoker = true`. RLS on the underlying
tables remains the access boundary, so a WindowPilot customer only sees their
own tenant data and enabled modules.

Generate the customer API/read-model contract for integrations and security
review:

```bash
python3 platform/homepilot_api_contract.py \
  --out-dir /tmp/homepilot_api_contract_pack \
  --module windowpilot
```

The contract documents the PostgREST endpoints, required anon-key plus customer
JWT headers, allowed filters, default selects, permissions, and RLS guarantees.

## Entitlement Scope

For customer handoffs, prefer `homepilot_customer_package.py`: it reads the
onboarding payload, scopes the canonical source data to that tenant and the
enabled modules, and then builds the dashboard/export artifacts. Manual
snapshot generation can still use repeated `--module` flags for module-limited
reviews.

## Static Dashboard Snapshot

Generate a customer dashboard snapshot from a canonical HomePilot JSON payload:

```bash
python3 platform/homepilot_snapshot.py \
  --json HomePilot/exports/facadepilot/example_homepilot.json \
  --tenant-name "Customer Name" \
  --tenant-slug customer-name \
  dashboard-js \
  --out HomePilot/client/dashboard-data.js
```

The generated file assigns:

```js
window.HOMEPILOT_DASHBOARD = {...};
```

The static dashboard loads that object first and falls back to `sample-data.js`
when no tenant snapshot exists. Keep generated tenant snapshots out of public
repositories unless the data is explicitly demo-safe.

## Export Shape

The static snapshot intentionally resembles a customer-facing read model:

- `tenant`: tenant identity and enabled modules.
- `campaigns`: campaign list visible to the tenant.
- `properties`: property records with status, next action, estimated value, tags, assessments, interactions, and objections.
- `recommendations`: campaign learnings and next-step suggestions.
- `trust.sourceLedger`: source/provenance coverage, evidence types, source runs, confidence, review gaps, and customer-safe guardrails.
- `brain`: graph nodes, edges, and stats connecting modules, signals, properties, campaign status, objections, and next actions.
- Assessment `metrics` are filtered through `homepilot_metric_access.py`; customer dashboards do not expose raw/internal/debug metrics.
- `summary`: counts for import QA.

This keeps the UI fast and lets the backend evolve without reshaping the
customer dashboard every time a pilot adds a metric.

## Data Dictionary

Generate the enterprise dictionary whenever a new pilot, metric, export column,
or dashboard view changes:

```bash
python3 platform/homepilot_data_dictionary.py \
  --out-dir /tmp/homepilot_data_dictionary_pack \
  --module windowpilot
```

The JSON and Markdown outputs explain the visible metric catalog, export sheets,
Supabase tables, dashboard views, product surfaces, roles, and privacy rules for
the selected modules. Use it next to the customer package and due-diligence pack
so large customers understand both the spreadsheet layer and the second-brain
visual layer.

## Enterprise Demo Room

Build a fully synthetic all-module showroom when a buyer needs to experience the
platform before live onboarding:

```bash
python3 platform/homepilot_demo_room.py \
  --out-dir /tmp/homepilot_enterprise_demo_room
```

The demo room writes onboarding JSON, canonical payload JSON, a tenant-scoped
customer package, static dashboard, CSV/XLSX exports, deployable portal bundle,
CRM/webhook handoff, data vendor enrichment plan, access audit, audit trail,
data dictionary, README, and optional zip archive.
