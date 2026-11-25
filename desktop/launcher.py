"""Point d'entrée de l'application de bureau Live Clipper.

Démarre le moteur (FastAPI + uvicorn) sur 127.0.0.1, puis affiche l'interface dans une fenêtre
native pywebview (WebView2 sous Windows) : aucun navigateur visible.

    python desktop/launcher.py              # application normale
    python desktop/launcher.py --headless   # moteur seul, sans fenêtre (tests, développement)
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


def start_server(port: int):
    import uvicorn
    from liveclipper.main import create_app

    # h11 / asyncio : implémentations Python pur (pas de httptools ni uvloop natifs)
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_config=None,
                            access_log=False, ws="websockets", http="h11", loop="asyncio")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    t.start()
    for _ in range(300):
        if server.started:
            break
        if not t.is_alive():
            raise RuntimeError("Le moteur de Live Clipper n'a pas pu démarrer (voir les logs).")
        time.sleep(0.05)
    return server, t


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
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)

    try:
        from liveclipper import config, paths
        from liveclipper.logging_setup import setup_logging
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
    server = None
    if existing_instance(port):
        log.info("Live Clipper tourne déjà sur le port %s : ouverture d'une fenêtre supplémentaire.", port)
    else:
        if not port_free(port):
            log.warning("Port %s occupé par une autre application : port aléatoire (la connexion "
                        "OAuth nécessitera de coller l'adresse de retour).", port)
            port = free_port()
        try:
            server, _t = start_server(port)
        except Exception as e:
            error_box(f"Impossible de démarrer Live Clipper : {e}\n\nJournaux : {paths.logs_dir()}")
            return 1
    url = f"http://127.0.0.1:{port}/"
    log.info("Interface : %s", url)

    if args.headless:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        try:
            import webview
        except Exception as e:
            error_box(f"Composant d'affichage introuvable (pywebview) : {e}")
            return 1
        api = JsApi()
        window = webview.create_window("Live Clipper", url, width=1440, height=920, min_size=(1100, 700),
                                       background_color="#0b0d12", js_api=api, text_select=True)
        api.window = window
        try:
            webview.start(private_mode=False, storage_path=str(paths.home() / "webview"))
        except Exception as e:
            error_box("Impossible d'ouvrir la fenêtre de Live Clipper. Installe le runtime Microsoft "
                      f"Edge WebView2 puis relance l'application.\n\nDétail : {e}")
            return 1
    if server is not None:
        server.should_exit = True
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
