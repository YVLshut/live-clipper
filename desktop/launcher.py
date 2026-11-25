"""Point d'entrée de l'application de bureau Live Clipper.

Le moteur (FastAPI + uvicorn + transcription) tourne dans un PROCESSUS SÉPARÉ de la fenêtre :
la fenêtre pywebview reste réactive même quand le moteur charge un modèle Whisper ou transcrit
(sinon ces calculs natifs bloquent le verrou de Python et Windows affiche « Ne répond pas »).

    python desktop/launcher.py              # application normale (fenêtre + moteur en sous-processus)
    python desktop/launcher.py --headless   # moteur seul, sans fenêtre (tests, développement)
    python desktop/launcher.py --server ... # (interne) processus moteur lancé par la fenêtre
"""
from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

# Exe sans console (PyInstaller console=False) : stdout/stderr valent None et feraient planter
# les bibliothèques qui écrivent dessus (barres tqdm, avertissements…).
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

log = logging.getLogger("liveclipper.desktop")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def existing_instance(port: int) -> bool:
    import httpx
    try:
        return httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2).json().get("app") == "LiveClipper"
    except Exception:
        return False


class JsApi:
    """Fonctions natives appelables depuis l'interface (window.pywebview.api)."""

    def __init__(self) -> None:
        self.window = None

    def pick_folder(self, initial: str | None = None):
        import webview
        res = self.window.create_file_dialog(webview.FOLDER_DIALOG, directory=initial or "")
        return res[0] if res else None


def make_server(port: int, shutdown_token: str | None = None):
    import uvicorn
    from liveclipper.main import create_app

    app = create_app()
    # h11 / asyncio : implémentations Python pur (pas de httptools ni uvloop natifs)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None,
                            access_log=False, ws="websockets", http="h11", loop="asyncio")
    server = uvicorn.Server(config)
    app.state.uvicorn_server = server
    app.state.shutdown_token = shutdown_token
    return server


def watch_parent(parent_pid: int, server) -> None:
    """Arrête le moteur si la fenêtre (processus parent) disparaît, même après un plantage."""
    def _wait():
        if sys.platform.startswith("win"):
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE
            if not h:
                return
            k32.WaitForSingleObject(h, 0xFFFFFFFF)
            k32.CloseHandle(h)
        else:
            while os.getppid() == parent_pid:
                time.sleep(1)
        log.info("Fenêtre fermée : arrêt du moteur.")
        server.should_exit = True
        time.sleep(15)
        os._exit(0)  # filet de sécurité si l'arrêt propre bloque

    threading.Thread(target=_wait, name="parent-watch", daemon=True).start()


def engine_command(port: int) -> list[str]:
    args = ["--server", "--port", str(port), "--parent-pid", str(os.getpid())]
    if getattr(sys, "frozen", False):
        return [sys.executable] + args
    return [sys.executable, str(Path(__file__).resolve())] + args


def start_engine_process(port: int, token: str):
    import subprocess
    env = {**os.environ, "LIVECLIPPER_SHUTDOWN_TOKEN": token}
    flags = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
    return subprocess.Popen(engine_command(port), env=env, creationflags=flags,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_healthy(port: int, proc=None, timeout: float = 90) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc is not None and proc.poll() is not None:
            return False
        if existing_instance(port):
            return True
        time.sleep(0.25)
    return False


def stop_engine_process(proc, port: int, token: str) -> None:
    import httpx
    if proc is None or proc.poll() is not None:
        return
    try:
        httpx.post(f"http://127.0.0.1:{port}/api/shutdown", headers={"X-Shutdown-Token": token}, timeout=3)
    except Exception:
        pass
    try:
        proc.wait(10)
    except Exception:
        proc.kill()


LOADING_HTML = """<!doctype html><html><body style="margin:0;background:#0b0d12;color:#b9bfcd;
font-family:'Segoe UI',sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">
<div style="text-align:center"><div style="width:42px;height:42px;margin:0 auto 18px;border-radius:50%;
border:4px solid #272e3d;border-top-color:#a78bfa;animation:s 1s linear infinite"></div>
Démarrage de Live Clipper…</div><style>@keyframes s{to{transform:rotate(360deg)}}</style></body></html>"""


def error_box(message: str) -> None:
    log.error(message)
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Live Clipper", 0x10)
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


POLICY_MESSAGE = (
    "Windows a bloqué un composant de Live Clipper (stratégie de contrôle d'application, "
    "probablement le « Contrôle intelligent des applications »).\n\n"
    "Les bibliothèques de Live Clipper ne sont pas signées numériquement : ce réglage de Windows les "
    "refuse.\n\nPour l'autoriser : Sécurité Windows > Contrôle des applications et du navigateur > "
    "Paramètres du contrôle intelligent des applications > Désactivé.\n\nDétail : {detail}"
)


def blocked_by_policy(e: BaseException) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("contrôle d", "controle d", "application control", "4551",
                                  "bloqué ce fichier", "blocked this file"))


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", help="moteur seul, sans fenêtre")
    ap.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--parent-pid", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)

    try:
        from liveclipper import config, paths
        from liveclipper.logging_setup import setup_logging
        if args.server or args.headless:
            from liveclipper.main import create_app  # noqa: F401  (charge toutes les DLL natives dès maintenant)
    except ImportError as e:
        if blocked_by_policy(e):
            error_box(POLICY_MESSAGE.format(detail=e))
            return 2
        raise
    setup_logging()
    paths.setup_dll_dirs()
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    port = args.port or int(config.get("oauth_port") or 47615)

    # ---------------------------------------------------------------- moteur seul
    if args.server or args.headless:
        if existing_instance(port):
            log.info("Un moteur Live Clipper tourne déjà sur le port %s.", port)
            return 0
        server = make_server(port, os.environ.get("LIVECLIPPER_SHUTDOWN_TOKEN"))
        if args.parent_pid:
            watch_parent(args.parent_pid, server)
        log.info("Moteur : http://127.0.0.1:%s/", port)
        server.run()
        return 0

    # ---------------------------------------------------------------- fenêtre
    import secrets as pysecrets
    token = pysecrets.token_urlsafe(24)
    proc = None
    if existing_instance(port):
        log.info("Live Clipper tourne déjà sur le port %s : ouverture d'une fenêtre supplémentaire.", port)
    else:
        if not port_free(port):
            log.warning("Port %s occupé par une autre application : port aléatoire (la connexion "
                        "OAuth nécessitera de coller l'adresse de retour).", port)
            port = free_port()
        proc = start_engine_process(port, token)
    url = f"http://127.0.0.1:{port}/"

    try:
        import webview
    except Exception as e:
        stop_engine_process(proc, port, token)
        error_box(f"Composant d'affichage introuvable (pywebview) : {e}")
        return 1
    api = JsApi()
    window = webview.create_window("Live Clipper", html=LOADING_HTML, width=1440, height=920,
                                   min_size=(1100, 700), background_color="#0b0d12", js_api=api,
                                   text_select=True)
    api.window = window

    def boot():
        if wait_healthy(port, proc):
            log.info("Interface : %s", url)
            window.load_url(url)
            return
        code = proc.poll() if proc else None
        msg = (f"Le moteur de Live Clipper n'a pas pu démarrer (code {code}).\n\n"
               f"Journaux : {paths.logs_dir()}")
        if code == 2:
            msg = POLICY_MESSAGE.format(detail="composant bloqué au démarrage du moteur")
        error_box(msg)
        window.destroy()

    try:
        webview.start(boot, private_mode=False, storage_path=str(paths.home() / "webview"))
    except Exception as e:
        error_box("Impossible d'ouvrir la fenêtre de Live Clipper. Installe le runtime Microsoft "
                  f"Edge WebView2 puis relance l'application.\n\nDétail : {e}")
        return 1
    finally:
        stop_engine_process(proc, port, token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
