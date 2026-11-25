"""2. Transcription faster-whisper (reprise de clipper.transcribe), GPU si possible sinon CPU int8."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from .. import paths
from .utils import CancelCheck, Progress, Throttle, check, hms, never_cancel, noop_progress

log = logging.getLogger("liveclipper.whisper")
_cache: dict[tuple, object] = {}
_cache_lock = threading.Lock()


_cuda_cache: tuple[bool, str] | None = None
_cuda_lock = threading.Lock()


def cuda_available(refresh: bool = False) -> tuple[bool, str]:
    """Détection CUDA, mise en cache : importer ctranslate2 + CUDA est lent (plusieurs secondes au
    premier lancement), on ne le fait qu'une fois par processus."""
    global _cuda_cache
    with _cuda_lock:
        if _cuda_cache is not None and not refresh:
            return _cuda_cache
        try:
            paths.setup_dll_dirs()
            import ctranslate2
            n = ctranslate2.get_cuda_device_count()
            _cuda_cache = (n > 0, f"{n} GPU CUDA détecté(s)" if n else "aucun GPU CUDA détecté")
        except Exception as e:  # pragma: no cover - dépend de la machine
            _cuda_cache = (False, f"CUDA indisponible : {e}")
        return _cuda_cache


def prewarm() -> None:
    """Au démarrage du moteur, en arrière-plan : détection GPU (et chargement des DLL natives)."""
    threading.Thread(target=cuda_available, name="cuda-prewarm", daemon=True).start()


def pick_device(cfg: dict) -> tuple[str, str, str]:
    """Renvoie (device, compute_type, explication)."""
    dev, ct = cfg.get("device", "auto"), cfg.get("compute_type", "auto")
    if dev == "auto":
        ok, why = cuda_available()
        dev = "cuda" if ok else "cpu"
    else:
        why = "choisi dans les Paramètres"
    if ct in (None, "", "auto"):
        ct = "float16" if dev == "cuda" else "int8"
    return dev, ct, why


def model_path(name: str) -> str:
    """Modèle local (téléchargé par l'assistant) si présent, sinon le nom (téléchargement auto)."""
    local = paths.models_dir() / name
    if (local / "model.bin").exists():
        return str(local)
    return name


def load_model(cfg: dict):
    from faster_whisper import WhisperModel
    dev, ct, why = pick_device(cfg)
    key = (cfg["whisper_model"], dev, ct)
    with _cache_lock:
        if key in _cache:
            return _cache[key], dev, ct, why
        try:
            m = WhisperModel(model_path(cfg["whisper_model"]), device=dev, compute_type=ct,
                             download_root=str(paths.models_dir()))
        except Exception as e:
            if dev != "cuda":
                raise
            log.warning("GPU inutilisable (%s) : repli sur le CPU (int8)", e)
            why = f"repli CPU : {e}"
            dev, ct = "cpu", "int8"
            key = (cfg["whisper_model"], dev, ct)
            m = WhisperModel(model_path(cfg["whisper_model"]), device=dev, compute_type=ct,
                             download_root=str(paths.models_dir()))
        _cache.clear()          # un seul modèle en mémoire
        _cache[key] = m
        return m, dev, ct, why


def transcribe(d: Path, cfg: dict, progress: Progress = noop_progress,
               cancel: CancelCheck = never_cancel) -> list[dict]:
    out = d / "transcript.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    p = progress if isinstance(progress, Throttle) else Throttle(progress)
    p(0.0, "Chargement du modèle Whisper…", force=True)
    model, dev, ct, why = load_model(cfg)
    log.info("Whisper %s sur %s/%s (%s)", cfg["whisper_model"], dev, ct, why)
    p(0.01, f"Transcription sur {'GPU' if dev == 'cuda' else 'CPU'}…", force=True)
    lang = cfg.get("language") or None
    if lang == "auto":
        lang = None
    segs, info = model.transcribe(str(d / "audio.wav"), language=lang, word_timestamps=True, vad_filter=True)
    total = float(getattr(info, "duration", 0) or 0)
    data = []
    for s in segs:
        check(cancel)
        data.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                     "words": [{"s": w.start, "e": w.end, "w": w.word.strip()} for w in (s.words or [])]})
        if total:
            p(min(0.99, s.end / total), f"Transcription {hms(s.end)} / {hms(total)}")
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    p(1.0, "Transcription terminée", force=True)
    return data
