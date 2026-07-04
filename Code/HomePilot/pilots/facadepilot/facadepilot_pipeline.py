#!/usr/bin/env python3
"""Launch the real FacadePilot app from the HomePilot pilot folder.

The production FacadePilot code still lives in Documents/FacadePilot. This
wrapper makes HomePilot/pilots/facadepilot an app entrypoint without moving the
legacy output folders, imports, renders, flyers, or landing pages yet.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKTREE_ROOT = HERE.parents[3]
DEFAULT_FACADEPILOT_DIR = WORKTREE_ROOT / "Documents" / "FacadePilot"


def _facadepilot_dir() -> Path:
    configured = os.environ.get("FACADEPILOT_APP_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_FACADEPILOT_DIR.resolve()


def main() -> None:
    app_dir = _facadepilot_dir()
    script = app_dir / "facadepilot_pipeline.py"
    if not script.exists():
        raise SystemExit(
            "FacadePilot app niet gevonden.\n"
            f"Verwacht: {script}\n"
            "Zet eventueel FACADEPILOT_APP_DIR naar de echte FacadePilot-map."
        )

    sys.path.insert(0, str(app_dir))
    os.chdir(app_dir)

    spec = importlib.util.spec_from_file_location("_homepilot_facadepilot_app", script)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Kan FacadePilot niet laden vanaf {script}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.main()


if __name__ == "__main__":
    main()

