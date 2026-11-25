"""Journalisation dans %APPDATA%\\LiveClipper\\logs."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths

_done = False


def setup_logging(level: int = logging.INFO) -> None:
    global _done
    if _done:
        return
    _done = True
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    fh = RotatingFileHandler(paths.logs_dir() / "liveclipper.log", maxBytes=5_000_000,
                             backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:  # absent dans un exe sans console
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    for noisy in ("httpx", "httpcore", "httpx2", "httpcore2", "faster_whisper", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def _hook(exc_type, exc, tb):
        logging.getLogger("liveclipper").critical("Exception non gérée", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
