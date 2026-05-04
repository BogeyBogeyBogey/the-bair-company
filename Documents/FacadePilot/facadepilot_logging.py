#!/usr/bin/env python3
"""
FacadePilot Logging — centrale logger met file rotation
=========================================================
Eén logger voor alle modules. Schrijft naar:
  - stdout (console-vriendelijk format)
  - facadepilot.log (RotatingFileHandler, 10 MB max, 3 backups)

Gebruik:
    from facadepilot_logging import get_logger
    log = get_logger(__name__)
    log.info("Pipeline gestart")
    log.warning("Geen Street View beschikbaar")
    log.error("API call mislukt", exc_info=True)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

HERE = Path(__file__).parent.resolve()
LOG_FILE = HERE / "facadepilot.log"

_LOGGERS = {}
_INITIALIZED = False


def _init_root():
    """Eenmalige setup van root logger met file + stdout handlers."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    root = logging.getLogger("facadepilot")
    root.setLevel(logging.DEBUG)
    # Ouders niet laten dupliceren
    root.propagate = False

    # Console handler (info+)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    root.addHandler(console)

    # File handler met rotatie (10 MB, 3 backups = max 40 MB op disk)
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s [%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        root.addHandler(file_handler)
    except Exception as e:
        # Bv. read-only filesystem — laat console werken
        sys.stderr.write(f"[facadepilot_logging] kon log-file niet openen: {e}\n")


def get_logger(name: str = "facadepilot") -> logging.Logger:
    """Haal een named logger op (child van 'facadepilot' root).

    Voorbeeld:
        log = get_logger(__name__)   # bv. 'facadepilot_render'
    """
    _init_root()
    # Strip 'facadepilot_' prefix om de naam korter te maken in logs
    short = name.replace("facadepilot_", "fp.")
    if short not in _LOGGERS:
        logger = logging.getLogger("facadepilot." + short)
        _LOGGERS[short] = logger
    return _LOGGERS[short]


def silence_noisy_libraries():
    """Zet logging-noise van requests/urllib3 op WARNING."""
    for noisy in ["urllib3", "requests", "httpx", "openai", "PIL"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


# Auto-silence externe libs bij import
silence_noisy_libraries()


# ─── CLI test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log = get_logger(__name__)
    log.debug("debug — alleen in file")
    log.info("info — console + file")
    log.warning("warning")
    log.error("error")
    print(f"\n→ check log: {LOG_FILE}")
