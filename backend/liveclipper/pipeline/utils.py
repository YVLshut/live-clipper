"""Utilitaires repris de clipper.py (run, to_sec, hms, safe, duration)."""
from __future__ import annotations

import logging
import re
import subprocess
import sys
import time
from typing import Callable, Optional

from .. import paths
from ..errors import Cancelled

log = logging.getLogger("liveclipper.pipeline")

Progress = Callable[[float, Optional[str]], None]   # (fraction 0..1, message)
CancelCheck = Callable[[], bool]

# Pas de fenêtre console qui clignote sous Windows quand l'app lance ffmpeg / yt-dlp.
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}


def noop_progress(_f: float, _m: Optional[str] = None) -> None:
    pass


def never_cancel() -> bool:
    return False


def tool(name: str) -> str:
    return paths.bin_path(name)


def run(cmd, cancel: CancelCheck = never_cancel, on_line: Callable[[str], None] | None = None,
        **kw) -> subprocess.CompletedProcess:
    """Lance une commande ; lève CalledProcessError (avec stderr) ou Cancelled."""
    cmd = [str(c) for c in cmd]
    log.info("$ %s", " ".join(cmd)[:400])
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT if on_line else subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", **NO_WINDOW, **kw)
    out_lines: list[str] = []
    if on_line:
        assert proc.stdout is not None
        for line in proc.stdout:
            out_lines.append(line)
            if len(out_lines) > 400:
                del out_lines[:200]
            on_line(line.rstrip())
            if cancel():
                proc.kill()
                proc.wait()
                raise Cancelled()
        proc.wait()
        err = "".join(out_lines)
        out = err
    else:
        while True:
            try:
                out, err = proc.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if cancel():
                    proc.kill()
                    proc.communicate()
                    raise Cancelled()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def to_sec(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = 0.0
    for p in str(v).strip().split(":"):
        s = s * 60 + float(p)
    return s


def hms(s) -> str:
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def safe(s) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(s))[:60]


def duration(path) -> float:
    r = subprocess.run([tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, **NO_WINDOW)
    try:
        return float(r.stdout.strip() or 0)
    except ValueError:
        return 0.0


def check(cancel: CancelCheck) -> None:
    if cancel():
        raise Cancelled()


class Throttle:
    """Limite la fréquence des callbacks de progression."""

    def __init__(self, fn: Progress, every: float = 0.4):
        self.fn, self.every, self.last = fn, every, 0.0

    def __call__(self, f: float, m: Optional[str] = None, force: bool = False) -> None:
        t = time.monotonic()
        if force or t - self.last >= self.every:
            self.last = t
            self.fn(f, m)
