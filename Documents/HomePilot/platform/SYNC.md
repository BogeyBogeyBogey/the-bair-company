# Pilot Sync

`homepilot_sync.py` is the command that turns pilot output into central
HomePilot data.

## FacadePilot

```bash
python3 platform/homepilot_sync.py facadepilot \
  --csv ../FacadePilot/facadepilot_leads_24107_scored.csv \
  --tenant-id 00000000-0000-0000-0000-000000000001 \
  --campaign-id 00000000-0000-0000-0000-000000000002
```

This writes a HomePilot JSON payload to:

```text
HomePilot/exports/facadepilot/
```

## Dry-Run Import

```bash
python3 platform/homepilot_sync.py facadepilot \
  --csv ../FacadePilot/facadepilot_leads_24107_scored.csv \
  --tenant-id 00000000-0000-0000-0000-000000000001 \
  --campaign-id 00000000-0000-0000-0000-000000000002 \
  --import \
  --dry-run
```

## Live Import

After applying `supabase_schema.sql` and configuring `HomePilot/.env`:

```bash
python3 platform/homepilot_sync.py facadepilot \
  --csv ../FacadePilot/facadepilot_leads_24107_scored.csv \
  --tenant-id REAL_TENANT_UUID \
  --campaign-id REAL_CAMPAIGN_UUID \
  --import
```

The runner keeps legacy FacadePilot support while sharing the store layer. New pilot exports should prefer `pilot-csv` with canonical metric columns; only highly custom legacy exports need a bespoke adapter.

## Generic Pilot CSV

For modules that export canonical metric columns, use the shared `pilot-csv` command:

```bash
python3 platform/homepilot_sync.py pilot-csv \
  --module windowpilot \
  --csv /tmp/windowpilot_leads.csv \
  --tenant-id window-customer \
  --campaign-id window-q3 \
  --campaign-name "Window Q3" \
  --out /tmp/homepilot_window_records.json
```

Supported module keys are defined in `homepilot_platform.py`:

- `facadepilot`
- `windowpilot`
- `roofpilot`
- `gardenpilot`
- `poolpilot`
- `porchpilot`
- `drivewaypilot`

FacadePilot can still use its legacy adapter when working with older FacadePilot
CSV column names. Newer FacadePilot exports may also use `pilot-csv` when they
already expose canonical metric names.
