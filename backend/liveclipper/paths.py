"""Emplacements des données et des binaires.

Les données utilisateur vivent toujours dans %APPDATA%\\LiveClipper (Windows),
jamais à côté de l'exécutable (Program Files est en lecture seule).
Sous Linux/macOS (développement) : $XDG_DATA_HOME/LiveClipper ou ~/.local/share/LiveClipper.
La variable LIVECLIPPER_HOME permet de surcharger l'emplacement (tests).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "LiveClipper"
IS_WINDOWS = sys.platform.startswith("win")
FROZEN = bool(getattr(sys, "frozen", False))


def home() -> Path:
    env = os.environ.get("LIVECLIPPER_HOME")
    if env:
        p = Path(env)
    elif IS_WINDOWS:
        p = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sub(name: str) -> Path:
    p = home() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return home() / "liveclipper.db"


def logs_dir() -> Path:
    return _sub("logs")


def work_dir() -> Path:
    """Fichiers intermédiaires (vidéo source, audio, transcription)."""
    return _sub("work")


def default_clips_dir() -> Path:
    return _sub("clips")


def profiles_dir() -> Path:
    """Profils Chromium persistants (un par compte en mode navigateur)."""
    return _sub("profiles")


def models_dir() -> Path:
    """Modèles Whisper téléchargés au premier lancement."""
    return _sub("models")


def cuda_dir() -> Path:
    """DLL CUDA (cuBLAS / cuDNN) téléchargées à la demande."""
    return _sub("cuda")


def screenshots_dir() -> Path:
    return _sub("screenshots")


def avatars_dir() -> Path:
    return _sub("avatars")


def bundle_dir() -> Path:
    """Racine des ressources embarquées (PyInstaller) ou racine du dépôt en dev."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def frontend_dist() -> Path:
    return bundle_dir() / "frontend" / "dist"


def bin_path(name: str) -> str:
    """Chemin d'un binaire externe (ffmpeg, ffprobe, yt-dlp).

    Ordre : dossier bin/ embarqué -> dossier de l'interpréteur (venv) -> PATH.
    Renvoie le nom nu si rien n'est trouvé (l'erreur sera remontée à l'exécution).
    """
    exe = name + (".exe" if IS_WINDOWS else "")
    candidates = [home() / "bin" / exe, bundle_dir() / "bin" / exe, Path(sys.executable).parent / exe]
    if not FROZEN:
        candidates.append(bundle_dir() / "packaging" / "bin" / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which(name) or name


def setup_dll_dirs() -> None:
    """Rend les DLL CUDA téléchargées visibles pour ctranslate2 (Windows)."""
    d = cuda_dir()
    if not any(d.glob("*.dll")) and not any(d.glob("*.so*")):
        return
    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    if IS_WINDOWS and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(d))
        except OSError:
            pass


def install_user_tools() -> None:
    """Copie yt-dlp embarqué dans %APPDATA%\\LiveClipper\\bin pour pouvoir le mettre à jour
    (`yt-dlp -U`) sans droits administrateur : Program Files est en lecture seule."""
    exe = "yt-dlp" + (".exe" if IS_WINDOWS else "")
    src = bundle_dir() / "bin" / exe
    dst = home() / "bin" / exe
    if src.is_file() and (not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
