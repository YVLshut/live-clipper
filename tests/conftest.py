"""Fixtures communes : dossier de données isolé, vidéo d'exemple générée par ffmpeg."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TEXT1 = ("Hello everyone and welcome back to the stream. Today we are going to play a brand new game "
         "that a lot of you asked for. Let me tell you a quick story about what happened yesterday.")
TEXT2 = ("Oh my god, I cannot believe it, that was absolutely incredible! Did you see that? "
         "That is the best moment of the whole stream, thank you so much for watching.")


@pytest.fixture(autouse=True)
def lc_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LIVECLIPPER_HOME", str(home))
    monkeypatch.setenv("LIVECLIPPER_KEYRING", "file")
    from liveclipper import db, secrets
    db.reset_engine()
    secrets._use_file = None
    yield home
    db.reset_engine()


def has_flite() -> bool:
    ff = shutil.which("ffmpeg")
    if not ff:
        return False
    r = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True)
    return " flite " in r.stdout


def _make_sample(out: Path) -> Path:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg absent")
    if not has_flite():  # pas de synthèse vocale : tonalités seulement
        graph = ("sine=f=220:r=16000,volume=0.3,atrim=0:12[s1];anullsrc=r=16000:cl=mono,atrim=0:4[q];"
                 "sine=f=660:r=16000,volume=8,atrim=0:3[boom];sine=f=330:r=16000,volume=0.3,atrim=0:8[s2];"
                 "[s1][q][boom][s2]concat=n=4:v=0:a=1,aformat=channel_layouts=stereo[a]")
    else:
        graph = None
    graph = graph or (
        f"flite=text='{TEXT1}':voice=slt,aresample=16000[s1];"
        "anullsrc=r=16000:cl=mono,atrim=0:4[q];"
        "sine=f=660:r=16000,volume=8,atrim=0:3[boom];"
        f"flite=text='{TEXT2}':voice=kal,aresample=16000[s2];"
        "[s1][q][boom][s2]concat=n=4:v=0:a=1,aformat=channel_layouts=stereo[a]"
    )
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25",
                    "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-shortest",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(out)], check=True)
    return out


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    return _make_sample(tmp_path_factory.mktemp("sample") / "sample_live.mp4")


def whisper_tiny_available() -> bool:
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from faster_whisper.utils import download_model
        download_model("tiny")
        return True
    except Exception:
        return False
