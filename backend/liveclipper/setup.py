"""Premier lancement : téléchargement des modèles Whisper et (option) des bibliothèques CUDA, avec progression."""
from __future__ import annotations

import fnmatch
import functools
import json
import logging
import re
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path

import httpx

from . import paths
from .errors import Cancelled, humanize
from .events import bus
from .pipeline.utils import NO_WINDOW

log = logging.getLogger("liveclipper.setup")

MODEL_SIZES = {"tiny": "75 Mo", "base": "145 Mo", "small": "480 Mo", "medium": "1,5 Go",
               "large-v3": "3 Go", "large-v3-turbo": "1,6 Go"}
ALLOW = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
CUDA_PACKAGES = [("nvidia-cublas-cu12", None), ("nvidia-cudnn-cu12", "9.")]
HF = "https://huggingface.co"


# Dépôts Hugging Face des modèles (sans importer faster_whisper, très lourd à charger).
MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",  # redirigé par Hugging Face
}


def repo_for(model: str) -> str:
    if model not in MODEL_REPOS:
        raise ValueError(f"Modèle inconnu : {model}")
    return MODEL_REPOS[model]


def model_installed(model: str) -> bool:
    return (paths.models_dir() / model / "model.bin").exists()


@functools.lru_cache(maxsize=1)
def nvidia_gpu() -> dict:
    """Carte NVIDIA présente (pilote installé) ?"""
    exe = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if paths.IS_WINDOWS else None)
    if not exe or not Path(exe).exists():
        return {"present": False, "name": None}
    try:
        r = subprocess.run([exe, "--query-gpu=name", "--format=csv,noheader"], capture_output=True,
                           text=True, timeout=10, **NO_WINDOW)
        name = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else None
        return {"present": bool(name), "name": name}
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return {"present": False, "name": None}


def cuda_libs_installed() -> bool:
    d = paths.cuda_dir()
    return any(d.glob("cublas64_*.dll")) and any(d.glob("cudnn*.dll"))


class SetupTask:
    """Une seule tâche de téléchargement à la fois, suivie par l'interface (événements setup.progress)."""

    def __init__(self) -> None:
        self.state = {"task": None, "label": None, "progress": 0.0, "done_bytes": 0, "total_bytes": 0,
                      "status": "idle", "error": None}
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._last = 0.0

    def busy(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _emit(self, force: bool = False) -> None:
        if force or time.monotonic() - self._last > 0.3:
            self._last = time.monotonic()
            bus.publish("setup.progress", dict(self.state))

    def _set(self, force: bool = False, **kw) -> None:
        self.state.update(kw)
        if self.state["total_bytes"]:
            self.state["progress"] = round(self.state["done_bytes"] / self.state["total_bytes"], 4)
        self._emit(force)

    def start(self, task: str, label: str, fn) -> None:
        if self.busy():
            raise RuntimeError("Un téléchargement est déjà en cours.")
        self._cancel.clear()
        self.state.update(task=task, label=label, progress=0.0, done_bytes=0, total_bytes=0,
                          status="running", error=None)
        self._emit(True)

        def runner():
            try:
                fn()
                self._set(True, status="done", progress=1.0)
                bus.notify(f"{label} : terminé ✔", "success")
            except Cancelled:
                self._set(True, status="cancelled", error="Téléchargement annulé.")
            except Exception as e:
                log.exception("Téléchargement %s", task)
                msg = humanize(e)
                if isinstance(e, httpx.HTTPError):
                    msg = f"Téléchargement impossible (connexion Internet ?) : {e}"
                self._set(True, status="failed", error=msg)
                bus.notify(f"{label} : échec — {msg}", "error")

        self._thread = threading.Thread(target=runner, name=f"setup-{task}", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------ téléchargement HTTP avec progression
    def _download(self, client: httpx.Client, url: str, dest: Path) -> None:
        tmp = dest.with_suffix(dest.suffix + ".part")
        with client.stream("GET", url, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1024 * 256):
                    if self._cancel.is_set():
                        f.close()
                        tmp.unlink(missing_ok=True)
                        raise Cancelled()
                    f.write(chunk)
                    self.state["done_bytes"] += len(chunk)
                    self._set()
        tmp.replace(dest)

    # ------------------------------------------------------------ Whisper
    def whisper_files(self, client: httpx.Client, repo: str) -> list[tuple[str, int]]:
        r = client.get(f"{HF}/api/models/{repo}/tree/main")
        r.raise_for_status()
        out = []
        for item in r.json():
            name = item.get("path", "")
            if item.get("type") == "file" and any(fnmatch.fnmatch(name, p) for p in ALLOW):
                size = (item.get("lfs") or {}).get("size") or item.get("size") or 0
                out.append((name, int(size)))
        if not any(n == "model.bin" for n, _ in out):
            raise RuntimeError(f"Fichiers du modèle introuvables sur Hugging Face ({repo}).")
        return out

    def download_whisper(self, model: str) -> None:
        repo = repo_for(model)
        final = paths.models_dir() / model
        work = paths.models_dir() / f".{model}.download"
        work.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=httpx.Timeout(60, connect=20), follow_redirects=True) as c:
            files = self.whisper_files(c, repo)
            self._set(True, total_bytes=sum(s for _, s in files))
            for name, size in files:
                dest = work / name
                if dest.exists() and dest.stat().st_size == size:
                    self.state["done_bytes"] += size
                    continue
                self._set(True, label=f"Modèle Whisper {model} — {name}")
                self._download(c, f"{HF}/{repo}/resolve/main/{name}", dest)
        if final.exists():
            shutil.rmtree(final)
        work.rename(final)
        log.info("Modèle Whisper %s installé dans %s", model, final)

    # ------------------------------------------------------------ CUDA (Windows)
    @staticmethod
    def wheel_url(client: httpx.Client, package: str, prefix: str | None) -> tuple[str, int]:
        r = client.get(f"https://pypi.org/pypi/{package}/json")
        r.raise_for_status()
        data = r.json()

        def key(v: str):
            return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", v))

        for version in sorted(data["releases"], key=key, reverse=True):
            if prefix and not version.startswith(prefix):
                continue
            for f in data["releases"][version]:
                if f["filename"].endswith("win_amd64.whl"):
                    return f["url"], int(f.get("size") or 0)
        raise RuntimeError(f"Aucune version Windows trouvée pour {package}.")

    def download_cuda(self) -> None:
        dest = paths.cuda_dir()
        tmpdir = dest / ".download"
        tmpdir.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=True) as c:
            wheels = [(p, *self.wheel_url(c, p, pre)) for p, pre in CUDA_PACKAGES]
            self._set(True, total_bytes=sum(s for _, _, s in wheels))
            for pkg, url, _size in wheels:
                self._set(True, label=f"Bibliothèques GPU — {pkg}")
                whl = tmpdir / f"{pkg}.whl"
                self._download(c, url, whl)
                with zipfile.ZipFile(whl) as z:
                    for m in z.namelist():
                        if m.lower().endswith(".dll") and "/bin/" in m:
                            with z.open(m) as src, open(dest / Path(m).name, "wb") as out:
                                shutil.copyfileobj(src, out)
                whl.unlink(missing_ok=True)
        shutil.rmtree(tmpdir, ignore_errors=True)
        (dest / "installed.json").write_text(json.dumps({"packages": [w[0] for w in wheels]}), encoding="utf-8")
        paths.setup_dll_dirs()
        from .pipeline.transcribe import cuda_available
        cuda_available(refresh=True)


setup_task = SetupTask()
