"""Pipeline réel sur une courte vidéo générée par ffmpeg (CPU, Whisper tiny)."""
from __future__ import annotations

import json
import subprocess

import pytest

from conftest import has_flite, whisper_tiny_available
from liveclipper import config
from liveclipper.pipeline import caption, download, highlights, peaks, render, transcribe
from liveclipper.pipeline.utils import duration, tool

pytestmark = pytest.mark.slow


def probe_stream(path):
    r = subprocess.run([tool("ffprobe"), "-v", "error", "-show_entries",
                        "stream=codec_type,width,height", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"]


@pytest.fixture
def cfg():
    c = config.get_all()
    c.update(whisper_model="tiny", device="cpu", compute_type="int8", language="en",
             min_len=5, max_len=15)
    return c


def test_download_local_and_peaks(sample_video, lc_home):
    events = []
    d, src = download.download(str(sample_video), lc_home / "work", progress=lambda f, m: events.append(f))
    assert (d / "video.mp4").exists() and (d / "audio.wav").exists()
    assert src["platform"] == "Fichier local" and src["author"] == "Fichier local"
    assert events and events[-1] == 1.0
    pk = peaks.loudness_peaks(d)
    assert pk, "aucun pic détecté"
    top = max(pk, key=lambda p: p["z"])
    # le "boom" commence après la 1re phrase + 4 s de silence
    assert top["z"] > 0.5


def test_full_pipeline_cpu(sample_video, lc_home, cfg):
    if not whisper_tiny_available() or not has_flite():
        pytest.skip("modèle Whisper tiny ou synthèse vocale flite indisponible")
    d, src = download.download(str(sample_video), lc_home / "work")
    segs = transcribe.transcribe(d, cfg)
    text = " ".join(s["text"] for s in segs).lower()
    assert "stream" in text and segs[0]["words"], text
    total = duration(d / "video.mp4")
    pk = peaks.loudness_peaks(d)

    calls = []

    def fake_ask(prompt, c, key):
        calls.append(prompt)
        assert "TRANSCRIPTION" in prompt and "[00:00:0" in prompt
        return [{"start": "00:00:01", "end": "00:00:09", "score": 8.5, "title": "Intro",
                 "hook": "Il ne s'attendait pas à ça", "caption": "Le début du live",
                 "hashtags": ["#gaming", "#twitch"]},
                {"start": "00:00:20", "end": "00:00:24", "score": 6, "title": "Réaction",
                 "hook": "", "caption": "", "hashtags": []}]

    hl, warns = highlights.find_highlights(segs, pk, src, 3, total, cfg, "sk-test", ask=fake_ask)
    assert calls and not warns
    assert len(hl) == 2 and hl[0]["score"] == 8.5
    assert 5 <= hl[0]["end"] - hl[0]["start"] <= 15

    for layout in ("blur", "crop"):
        out = render.render_clip(d / "video.mp4", segs, hl[0]["start"], hl[0]["end"], hl[0]["hook"],
                                 layout, lc_home / "clips" / layout, cfg)
        streams = probe_stream(out)
        v = [s for s in streams if s["codec_type"] == "video"][0]
        assert (v["width"], v["height"]) == (1080, 1920)
        assert any(s["codec_type"] == "audio" for s in streams)
        assert abs(duration(out) - (hl[0]["end"] - hl[0]["start"])) < 0.6
        ass = (out.parent / "subs.ass").read_text(encoding="utf-8")
        assert "IL NE S'ATTENDAIT PAS" in ass and "Dialogue: 0" in ass

    cap = caption.build_caption(hl[0], src, ["#live", "#gaming"])
    assert "🎥 Source : Fichier local\n" in cap and "file://" not in cap
    assert caption.credit_line({"author": "Zerator", "url": "https://twitch.tv/videos/1"}) == \
        "🎥 Source : Zerator — https://twitch.tv/videos/1"
    assert cap.endswith("#gaming #twitch #live")


def test_fallback_without_key(sample_video, lc_home, cfg):
    d, src = download.download(str(sample_video), lc_home / "work")
    segs = [{"start": 0.0, "end": 30.0, "text": "x", "words": []}]
    hl, warns = highlights.find_highlights(segs, peaks.loudness_peaks(d), src, 2,
                                           duration(d / "video.mp4"), cfg, None)
    assert hl and "Aucune clé API" in warns[0]


def test_ai_error_falls_back(sample_video, lc_home, cfg):
    d, src = download.download(str(sample_video), lc_home / "work")
    segs = [{"start": float(i), "end": i + 1.0, "text": f"phrase {i}", "words": []} for i in range(30)]

    def bad(*_a):
        raise highlights.AIError("Clé API Anthropic invalide : vérifie-la dans les Paramètres.")

    hl, warns = highlights.find_highlights(segs, peaks.loudness_peaks(d), src, 2,
                                           duration(d / "video.mp4"), cfg, "sk-bad", ask=bad)
    assert hl and any("invalide" in w for w in warns)


def test_source_from_info_twitch():
    src = download.source_from_info({"id": "v123", "extractor_key": "TwitchVod", "uploader": "Zerator",
                                     "uploader_id": "zerator", "title": "Live", "upload_date": "20261101",
                                     "webpage_url": "https://www.twitch.tv/videos/123"}, "x")
    assert src["platform"] == "Twitch" and src["date"] == "2026-11-01"
    assert src["author_url"] == "https://www.twitch.tv/zerator" and src["id"] == "twitch_v123"
