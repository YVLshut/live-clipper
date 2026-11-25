"""Paramètres de l'application (table `setting`), avec les valeurs par défaut de clipper.py."""
from __future__ import annotations

import copy
from typing import Any

from sqlmodel import select

from . import db, paths
from .models import Setting

# Repris de clipper.py (DEFAULTS), complétés pour l'application.
DEFAULTS: dict[str, Any] = {
    "whisper_model": "large-v3",
    "device": "auto",              # auto | cuda | cpu
    "compute_type": "auto",        # auto -> float16 (GPU) / int8 (CPU)
    "language": "fr",
    "min_len": 15,
    "max_len": 60,
    "max_clips": 10,
    "live_segment_minutes": 30,
    "layout": "blur",
    "font": "Arial Black",
    "words_per_line": 3,
    "encoder": "libx264",          # libx264 | h264_nvenc
    "default_hashtags": ["#live", "#clip", "#fyp"],
    "output_dir": "",              # vide -> %APPDATA%\LiveClipper\clips
    "ai_model": "claude-haiku-5-5",
    "ai_window_sec": 1500,
    "browser_channel": "msedge" if paths.IS_WINDOWS else "chromium",
    "meta_app_id": "",
    "tiktok_client_key": "",
    "oauth_port": 47615,
    "setup_done": False,
}

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
AI_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
ENCODERS = ["libx264", "h264_nvenc"]
LAYOUTS = ["blur", "crop"]


def get_all() -> dict[str, Any]:
    out = copy.deepcopy(DEFAULTS)
    with db.session() as s:
        for row in s.exec(select(Setting)).all():
            out[row.key] = row.value
    return out


def get(key: str) -> Any:
    with db.session() as s:
        row = s.get(Setting, key)
        return row.value if row is not None else copy.deepcopy(DEFAULTS.get(key))


def update(values: dict[str, Any]) -> dict[str, Any]:
    with db.session() as s:
        for k, v in values.items():
            row = s.get(Setting, k)
            if row is None:
                s.add(Setting(key=k, value=v))
            else:
                row.value = v
                s.add(row)
        s.commit()
    return get_all()


def clips_dir(cfg: dict | None = None) -> "paths.Path":
    cfg = cfg or get_all()
    if cfg.get("output_dir"):
        p = paths.Path(cfg["output_dir"])
        p.mkdir(parents=True, exist_ok=True)
        return p
    return paths.default_clips_dir()
