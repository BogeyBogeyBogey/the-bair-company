#!/usr/bin/env python3
"""Launch FacadePilot for the native macOS wrapper."""

import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser


def maximize_app_window():
    if sys.platform != "darwin" or os.environ.get("FACADEPILOT_MAXIMIZE_WINDOW", "1") == "0":
        return

    app_name = os.environ.get("FACADEPILOT_APP_NAME", "FacadePilot")
    script = f'''
set appName to "{app_name}"
set timeoutAt to (current date) + 12
repeat while (current date) is less than timeoutAt
    tell application "System Events"
        if exists process appName then
            tell process appName
                set frontmost to true
                if (count of windows) > 0 then
                    try
                        perform action "AXRaise" of window 1
                    end try
                    try
                        perform action "AXZoomWindow" of window 1
                        return
                    end try
                    try
                        click (first button of window 1 whose subrole is "AXZoomButton")
                        return
                    end try
                end if
            end tell
        end if
    end tell
    delay 0.2
end repeat
'''

    def run():
        try:
            subprocess.run(["osascript", "-e", script], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: launcher.py /path/to/FacadePilot")

    project_dir = Path(sys.argv[1]).expanduser().resolve()
    pipeline = project_dir / "facadepilot_pipeline.py"
    if not pipeline.exists():
        raise SystemExit(f"facadepilot_pipeline.py not found in {project_dir}")

    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))
    os.environ["FACADEPILOT_NO_BROWSER"] = "1"
    webbrowser.open = lambda *args, **kwargs: True
    maximize_app_window()

    import facadepilot_pipeline

    try:
        app_port = os.environ.get("FACADEPILOT_APP_PORT", "9300")
        facadepilot_pipeline.main(["--port", app_port, "--no-browser"])
    except TypeError:
        facadepilot_pipeline.main()


if __name__ == "__main__":
    main()
