# HomePilot FacadePilot Entrypoint

This folder is the HomePilot-facing launcher for the existing FacadePilot app.

## Legal-first pipeline policy

FacadePilot now treats renovation scoring as property intelligence, not
homeowner-intent profiling:

```text
legal/open/customer data
→ property opportunity score
→ partner shortlist
→ own/partner/licensed photo verification
→ AI render/flyer
→ real campaign response learning
```

Google Street View is not a production image source. If a legacy review tool is
used for orientation, it must be explicitly enabled with
`FACADEPILOT_ALLOW_GOOGLE_STREETVIEW=1` and may not produce stored campaign
assets or customer-facing before-images.

For DAW demos, use the generated package at:

```text
/private/tmp/homepilot_demo_2000/START_DAW_DEMO.html
```

That package contains 2,000 synthetic addresses and 2,000 generated synthetic
facade visuals. They are intentionally labelled as demo-only and are not based
on real buildings or Google imagery.

The real FacadePilot code currently lives at:

```text
../../../../Documents/FacadePilot
```

Run from this folder with:

```bash
python3 app.py
```

or:

```bash
npm run dev
```

Both commands start the same FacadePilot dashboard and expose the flyer editor at:

```text
http://localhost:8769/flyer-editor
```

Set `FACADEPILOT_APP_DIR` only if the legacy app is moved to another location.
