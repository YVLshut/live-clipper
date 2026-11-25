"""API + file de jobs + WebSocket, avec un vrai job de clipping sur la vidéo d'exemple."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from conftest import has_flite, whisper_tiny_available


@pytest.fixture
def client(lc_home):
    from liveclipper.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def wait_job(client, job_id, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = [x for x in client.get("/api/jobs").json() if x["id"] == job_id][0]
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("job trop long")


def test_health_and_settings(client):
    assert client.get("/api/health").json()["app"] == "LiveClipper"
    s = client.get("/api/settings").json()
    assert s["encoder"] == "libx264" and s["secrets"]["anthropic_api_key"] is False
    r = client.put("/api/settings", json={"anthropic_api_key": "sk-ant-xyz", "max_clips": 4,
                                          "default_hashtags": "live #clip", "encoder": "h264_nvenc"})
    s = r.json()
    assert s["secrets"]["anthropic_api_key"] and s["max_clips"] == 4
    assert s["default_hashtags"] == ["#live", "#clip"] and s["encoder"] == "h264_nvenc"
    from liveclipper import secrets
    assert secrets.get(secrets.ANTHROPIC_KEY) == "sk-ant-xyz"
    r = client.put("/api/settings", json={"min_len": 50, "max_len": 20})
    assert r.status_code == 400 and "inférieure" in r.json()["detail"]
    assert client.put("/api/settings", json={"whisper_model": "xxl"}).json()["detail"] == "Modèle Whisper inconnu."


def test_create_jobs_validation(client):
    r = client.post("/api/jobs", json={"urls": "pas de lien ici"})
    assert r.status_code == 400 and "Aucun lien" in r.json()["detail"]
    r = client.post("/api/jobs", json={"urls": "https://twitch.tv/videos/1", "options": {"section": "2:00-1:00"}})
    assert r.status_code == 400 and "fin doit être après" in r.json()["detail"]


def test_parse_urls():
    from liveclipper.api.routes_clips import parse_urls
    assert parse_urls("https://www.twitch.tv/videos/1 https://youtu.be/abc,\nhttps://kick.com/x/videos/2") == [
        "https://www.twitch.tv/videos/1", "https://youtu.be/abc", "https://kick.com/x/videos/2"]


def test_full_job_with_websocket(client, sample_video, monkeypatch):
    if not whisper_tiny_available() or not has_flite():
        pytest.skip("Whisper tiny ou flite indisponible")
    from liveclipper.pipeline import highlights
    monkeypatch.setattr(highlights, "ask_claude", lambda text, cfg, key: [
        {"start": "00:00:02", "end": "00:00:10", "score": 9, "title": "Top", "hook": "Regarde ça",
         "caption": "Incroyable", "hashtags": ["#wow"]}])
    client.put("/api/settings", json={"whisper_model": "tiny", "device": "cpu", "language": "en",
                                      "anthropic_api_key": "sk-test"})
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.post("/api/jobs", json={"urls": str(sample_video),
                                           "options": {"max_clips": 2, "min_len": 5, "max_len": 12}})
        job = r.json()["jobs"][0]
        steps = set()
        while True:
            msg = ws.receive_json()
            if msg["type"] == "job.updated" and msg["data"]["id"] == job["id"]:
                steps.add(msg["data"]["step"])
                if msg["data"]["status"] in ("done", "failed"):
                    break
    assert msg["data"]["status"] == "done", msg["data"]
    assert {"download", "transcribe", "detect", "render"} <= steps
    clips = client.get("/api/clips").json()
    assert len(clips) == 1
    c = clips[0]
    assert c["score"] == 9 and c["source"]["platform"] == "Fichier local"
    assert "🎥 Source : Fichier local" in c["final_caption"] and "#wow" in c["final_caption"]
    v = client.get(c["video_url"])
    assert v.status_code == 200 and v.headers["content-type"] == "video/mp4"
    t = client.get(c["thumb_url"])
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg" and t.content[:2] == b"\xff\xd8"

    # Modifier l'accroche relance le montage de ce clip seulement
    r = client.patch(f"/api/clips/{c['id']}", json={"hook": "Nouvelle accroche", "caption": "Légende 2"})
    assert r.json()["rendering"] is True
    for _ in range(200):
        c2 = client.get(f"/api/clips/{c['id']}").json()
        if not c2["rendering"]:
            break
        time.sleep(0.3)
    assert c2["version"] == 2 and c2["caption"] == "Légende 2"
    from pathlib import Path
    assert "NOUVELLE ACCROCHE" in (Path(c2["file"]).parent / "subs.ass").read_text(encoding="utf-8")
    jobs = client.get("/api/jobs").json()
    assert jobs[0]["kind"] == "rerender" and jobs[0]["status"] == "done"

    assert client.post(f"/api/clips/{c['id']}/approve").json()["status"] == "approved"
    assert client.delete(f"/api/clips/{c['id']}").json()["ok"]
    assert client.get("/api/clips").json() == []
    assert not Path(c2["file"]).exists()


def test_cancel_queued_and_failed_job(client):
    r = client.post("/api/jobs", json={"urls": "/nonexistent/file.mp4 https://example.invalid/video"})
    jobs = r.json()["jobs"]
    assert len(jobs) == 1  # le chemin inexistant est ignoré
    j = wait_job(client, jobs[0]["id"], 60)
    assert j["status"] == "failed" and j["error"]
