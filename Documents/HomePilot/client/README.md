# HomePilot Client Prototype

Static customer-facing intelligence dashboard for the shared HomePilot data
model. It is intentionally dependency-free for now, so it can be opened locally
or deployed as static files while the backend continues to mature.

Open:

```text
client/index.html
```

Current views:

- Executive view with decision ledger, data trust, shortlist, readiness checks, and campaign memory.
- Trust view with source ledger coverage, source runs, evidence types, guardrails, and review gaps.
- Overview with KPIs, module quality, and priority queue.
- Database view with search, grade/status filters, and CSV export.
- Property profile with module assessments and interactions.
- Opportunity map with territory-style markers.
- Campaign intelligence with funnel, objections, and recommendations.
- Second brain graph linking signals, properties, reactions, and actions.

Production data path:

- Keep `sample-data.js` as the public demo fallback.
- Generate tenant-specific `dashboard-data.js` from a canonical HomePilot payload with `platform/homepilot_snapshot.py`.
- Build a deployable customer portal from a scoped customer package with `platform/homepilot_portal.py` before online review or static hosting.
- `live-config.js` is disabled by default; configure it only after live RLS/customer access proof.
- `live-data.js` can load tenant-scoped Supabase dashboard views with a public anon key plus a customer JWT; it never needs privileged database keys.
