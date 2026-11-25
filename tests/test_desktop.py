"""Lanceur de bureau en mode --headless (la fenêtre pywebview se teste à la main, voir TESTS_MANUELS.md)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_launcher_headless(lc_home):
    port = _free_port()
    env = {**os.environ, "LIVECLIPPER_HOME": str(lc_home)}
    p = subprocess.Popen([sys.executable, str(ROOT / "desktop" / "launcher.py"), "--headless", "--port", str(port)],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        assert r.json()["app"] == "LiveClipper"
        assert (lc_home / "logs" / "liveclipper.log").exists()
        assert (lc_home / "liveclipper.db").exists()
    finally:
        p.terminate()
        p.wait(10)
