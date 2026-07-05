# HomePilot

HomePilot is the shared property intelligence platform for renovation opportunity
engines such as FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot,
PorchPilot, and DrivewayPilot.

The product rule is simple:

```text
tenant -> modules -> campaigns -> properties -> assessments -> interactions
```

`properties` are shared across pilots. A single house can have a facade
assessment, window assessment, roof assessment, response history, notes, exports,
and campaign learnings without duplicating the address across multiple products.

## Data Platform Location

The shared data platform belongs in `HomePilot/platform`, not inside `facadepilot`. FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future pilots are modules that feed the same tenant-safe database.

## Folder Layout

```text
HomePilot/
  platform/         Shared data model, metrics catalog, Supabase schema, privacy/export tooling.
  pilots/           Pilot modules and adapters.
```

The current FacadePilot app still lives next to this folder at `../FacadePilot`.
It should be treated as the first production pilot module and can later move to
`pilots/facadepilot` once imports, scripts, and local paths are updated
deliberately.

## Access Model

- A customer belongs to one tenant.
- A tenant can enable one or more modules.
- A WindowPilot customer sees only its own tenant, campaigns, properties,
  interactions, and WindowPilot metrics.
- Other tenants' raw data, addresses, responses, notes, and campaign learnings
  are never visible.
- Platform intelligence can use aggregate benchmarks only after anonymization,
  minimum cohort thresholds, and raw-identifier validation.
- Production access must be proven with the live RLS probe before customer rollout.
- Outreach readiness must be proven with compliance audits for provenance, contact basis, opt-outs, retention review, and careful lead-claim language.
- Use the readiness pack for local enterprise evidence, including data quality, then the live launch runner to seed repeatable WindowPilot/FacadePilot isolation tests, archive proof, and generate fixture cleanup SQL.
- Use the data dictionary for enterprise handoffs so customers can understand the metrics, exports, tables, views, and second-brain surfaces they are buying.
- Use `platform/MARKET_RESEARCH.md` as the product positioning brief: copy enterprise best practices from property-data, visual-intelligence, contractor-CRM, and compliance-heavy lead platforms while keeping HomePilot focused on renovation opportunity intelligence.

## Product Surfaces

1. Database view: fast table, filters, saved segments, CSV/XLSX export.
2. Property profile: one house with images, evidence, scores, modules, notes,
   and contact history.
3. Opportunity map: clusters, heatmaps, territory quality, and campaign status.
4. Campaign intelligence: response rates, objections, winning messages, next
   best actions.
5. Second brain: graph-like view linking property signals, campaigns,
   interactions, responses, objections, and recommendations.

For buyer demos without real customer data, build a synthetic all-module demo
room with `platform/homepilot_demo_room.py`. It packages the actual dashboard,
exports, portal bundle, CRM handoff, enrichment plan, access audit, audit trail,
and data dictionary from canonical payloads.

For a large territory demo, generate a safe 2000-address synthetic showroom:

```bash
python3 platform/homepilot_demo_room.py \
  --out-dir /tmp/homepilot_demo_2000 \
  --tenant-name "HomePilot 2000 Demo" \
  --tenant-slug homepilot-2000-demo \
  --property-count 2000
```

For the DAW producer/partner demo, generate a FacadePilot-only network with ten
synthetic Belgian facade renovators:

```bash
python3 platform/homepilot_demo_room.py \
  --out-dir /tmp/homepilot_daw_demo \
  --tenant-name "DAW Belgium Crepi Network" \
  --tenant-slug daw-belgium-crepi-network \
  --scenario daw \
  --property-count 2000
```

## Market Position

HomePilot should not be sold as another lead list. It should be sold as:

> The property intelligence layer for renovation opportunities.

Each Pilot is a specialized opportunity engine on top of that shared layer.
