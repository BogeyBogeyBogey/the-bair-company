# HomePilot Autoresearch

This is a narrow, non-mutating research loop for HomePilot visual intelligence.
It is inspired by experiment-driven autoresearch, but it does not modify live
systems, customer data, Supabase, outreach state, or production access.

## V1 Experiment Family

- Family: `second_brain_graph_layout`
- Target: improve readability of the HomePilot second-brain graph.
- Fixture: synthetic visual-scale HomePilot data from `homepilot_visual_intelligence.py`.
- Output: review artifacts in an operator-selected output directory, normally `/private/tmp/homepilot_autoresearch`.

## V2 Experiment Family

- Family: `lead_prioritization`
- Target: improve the ranked opportunity/action queue for a tenant-scoped dashboard snapshot.
- Fixture: a tenant-scoped dashboard snapshot, for example the DAW demo package.
- Output: review artifacts in an operator-selected output directory, normally `/private/tmp/homepilot_lead_autoresearch`.

This family tests scoring recipes across opportunity score, estimated value,
facade surface, confidence, public-context coverage, evidence coverage,
campaign-status proxy, partner capacity, and partner response history. The
response signal is an outcome proxy for model comparison only; it is not a
homeowner intent claim.

## V3 Experiment Family

- Family: `partner_assignment`
- Target: improve producer-network first-wave batches across assigned partners.
- Fixture: a tenant-scoped producer-network snapshot, normally with `leadPrioritization` attached.
- Output: review artifacts in an operator-selected output directory, normally `/private/tmp/homepilot_partner_assignment_autoresearch`.

This family tests quota modes, capacity weighting, response weighting, partner
share caps, and first-wave size. V1 uses existing assigned partner records only;
it never reassigns raw records across partners and never grants partner access.

## V4 Experiment Family

- Family: `campaign_segmentation`
- Target: identify reviewable campaign segments by territory, status, message angle, public context, property type, value band, facade band, and partner tier.
- Fixture: a tenant-scoped dashboard snapshot, optionally with lead and partner-assignment research attached.
- Output: review artifacts in an operator-selected output directory, normally `/private/tmp/homepilot_campaign_segmentation_autoresearch`.

This family keeps response denominators explicit: `response_rate_pct` uses
contacted records, while `target_response_rate_pct` remains separate. Segment
outputs omit raw addresses and contact values.

## V5 Experiment Family

- Family: `message_strategy`
- Target: choose safe draft-message angles for reviewed campaign segments.
- Fixture: a tenant-scoped dashboard snapshot, normally with `campaignSegmentation` attached.
- Output: review artifacts in an operator-selected output directory, normally `/private/tmp/homepilot_message_strategy_autoresearch`.

This family tests draft angles such as facade refresh, energy savings,
subsidy-review-without-claims, premium finish, maintenance, and local partner
review. Drafts require customer/legal approval before use and must not claim
homeowner intent, promised savings, subsidy eligibility, or technical outcomes.

## Intelligence Lab Orchestration

- Pack: `homepilot_intelligence_lab`
- Target: run the review-safe autoresearch stack for enterprise buyer demos and customer packages.
- Families: `lead_prioritization`, `partner_assignment` for producer networks, `campaign_segmentation`, and `message_strategy`.
- Output: `INTELLIGENCE_LAB.md`, `intelligence_lab.json`, and family subfolders under the selected output directory.

The lab mutates only the in-memory snapshot passed to the pack builder. It
writes review artifacts, not live data, and DAW/demo evidence remains synthetic
unless regenerated from customer-approved production sources.

## Allowed Changes

Autoresearch may test deterministic layout configuration values only:

- lane x positions
- node spacing and repulsion padding
- relaxation tick count
- edge distance and edge force
- visible property-label budget
- graph fit margins and scale bounds

The winning config is a proposal. It is not automatically applied to customer
packages or production.

## Score

The harness ranks variants by `final_score`, derived from:

- node overlap count and overlap amount
- edge crossing proxy
- label overlap count
- viewport fit score
- graph spread score
- runtime in milliseconds

Use source tables and dashboard snapshots for factual metrics. The graph score
is visual readability evidence only.

## Guardrails

- Synthetic demo evidence only.
- No live database writes.
- No Supabase credentials or service-role keys.
- No homeowner contact data.
- No cross-tenant learning.
- No claim that graph quality proves customer demand or homeowner intent.
- Lead-prioritization queues omit raw addresses in research outputs and must be
  reconciled against the tenant-scoped source snapshot before operational use.

## Example

```bash
python3 platform/homepilot_autoresearch.py \
  --out-dir /private/tmp/homepilot_autoresearch \
  --release-label local \
  --run 12
```

Review:

- `results.tsv`
- `best_graph_layout.json`
- `AUTORESEARCH_REPORT.md`

Lead-prioritization example:

```bash
python3 platform/homepilot_lead_autoresearch.py \
  --snapshot /private/tmp/homepilot_demo_2000/customer_package/data/dashboard_snapshot.json \
  --out-dir /private/tmp/homepilot_lead_autoresearch_daw_demo \
  --release-label daw-lead-priority \
  --run 48 \
  --limit 50
```

Optional target-score run:

```bash
python3 platform/homepilot_lead_autoresearch.py \
  --snapshot /private/tmp/homepilot_demo_2000/customer_package/data/dashboard_snapshot.json \
  --out-dir /private/tmp/homepilot_lead_autoresearch_daw_demo_target \
  --target-score 70 \
  --max-runs 200
```

Partner-assignment example:

```bash
python3 platform/homepilot_partner_assignment_autoresearch.py \
  --snapshot /private/tmp/homepilot_demo_2000/customer_package/data/dashboard_snapshot.json \
  --out-dir /private/tmp/homepilot_partner_assignment_daw_demo \
  --release-label daw-partner-assignment \
  --run 48 \
  --limit 50
```

Campaign-segmentation target-score example:

```bash
python3 platform/homepilot_campaign_segmentation_autoresearch.py \
  --snapshot /private/tmp/homepilot_demo_2000/customer_package/data/dashboard_snapshot.json \
  --out-dir /private/tmp/homepilot_campaign_segmentation_daw_demo_target \
  --target-score 80 \
  --max-runs 72
```

Message-strategy target-score example:

```bash
python3 platform/homepilot_message_strategy_autoresearch.py \
  --snapshot /private/tmp/homepilot_demo_2000/customer_package/data/dashboard_snapshot.json \
  --out-dir /private/tmp/homepilot_message_strategy_daw_demo_target \
  --target-score 93 \
  --max-runs 72
```

Full Intelligence Lab example:

```bash
python3 platform/homepilot_intelligence_lab.py \
  --snapshot /private/tmp/homepilot_demo_2000/customer_package/data/dashboard_snapshot.json \
  --out-dir /private/tmp/homepilot_intelligence_lab_daw_demo \
  --release-label daw-intelligence-lab \
  --run 12 \
  --lead-limit 50
```
