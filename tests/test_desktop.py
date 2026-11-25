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


def _launcher():
    sys.path.insert(0, str(ROOT / "desktop"))
    import launcher
    return launcher


def test_engine_subprocess_start_and_graceful_stop(lc_home, monkeypatch):
    """La fenêtre lance le moteur dans un processus séparé, puis l'arrête proprement avec le jeton."""
    launcher = _launcher()
    port = _free_port()
    proc = launcher.start_engine_process(port, "jeton-secret")
    try:
        assert launcher.wait_healthy(port, proc, timeout=60)
        assert proc.pid != os.getpid()
        r = httpx.post(f"http://127.0.0.1:{port}/api/shutdown", headers={"X-Shutdown-Token": "mauvais"})
        assert r.status_code == 403 and proc.poll() is None
        launcher.stop_engine_process(proc, port, "jeton-secret")
        assert proc.poll() == 0          # arrêt propre, pas tué
    finally:
        if proc.poll() is None:
            proc.kill()


def test_engine_stops_when_window_process_dies(lc_home):
    """Si la fenêtre plante, le moteur orphelin s'arrête tout seul."""
    port = _free_port()
    env = {**os.environ, "LIVECLIPPER_HOME": str(lc_home)}
    # faux processus « fenêtre » qui lance le moteur puis meurt
    parent = subprocess.Popen([sys.executable, "-c", f"""
import subprocess, sys, time, os
p = subprocess.Popen([sys.executable, {str(ROOT / 'desktop' / 'launcher.py')!r}, '--server', '--port', '{port}',
                      '--parent-pid', str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(p.pid, flush=True)
time.sleep(6)
"""], env=env, stdout=subprocess.PIPE, text=True)
    child_pid = int(parent.stdout.readline())
    ok = False
    for _ in range(80):
        try:
            ok = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200
            if ok:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    assert ok
    parent.wait(20)                       # la « fenêtre » se termine
    for _ in range(60):
        try:
            os.kill(child_pid, 0)
            time.sleep(0.5)
        except ProcessLookupError:
            break
    else:
        os.kill(child_pid, 9)
        raise AssertionError("le moteur ne s'est pas arrêté après la fermeture de la fenêtre")
