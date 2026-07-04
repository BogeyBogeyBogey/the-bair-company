# HomePilot FacadePilot Entrypoint

This folder is the HomePilot-facing launcher for the existing FacadePilot app.

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
