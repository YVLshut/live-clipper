"""Liste « Mes lives » : œil (activer / couper le clipping) et surveillance des chaînes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from liveclipper import db
from liveclipper.jobs import streams
from liveclipper.models import Job, Stream


def test_channel_urls():
    assert streams.is_channel_url("https://www.twitch.tv/zerator")
    assert streams.is_channel_url("https://kick.com/pseudo")
    assert streams.is_channel_url("https://www.youtube.com/@squeezie/live")
    assert not streams.is_channel_url("https://www.twitch.tv/videos/123456")
    assert not streams.is_channel_url("https://www.youtube.com/watch?v=abc")
    assert streams.normalize_url("https://www.twitch.tv/zerator/?ref=x") == "https://www.twitch.tv/zerator"


@pytest.fixture
def client(lc_home):
    from liveclipper.main import create_app
    with TestClient(create_app(start_workers=False)) as c:
        yield c


def test_add_list_toggle_delete(client):
    r = client.post("/api/jobs", json={"urls": "https://www.twitch.tv/zerator\nhttps://www.twitch.tv/videos/42"})
    assert r.json()["streams"] == 2 and len(r.json()["jobs"]) == 2
    # le même lien ne crée ni doublon ni second traitement tant que le premier est en cours
    r = client.post("/api/jobs", json={"urls": "https://www.twitch.tv/zerator/"})
    assert r.json()["jobs"] == []
    lst = client.get("/api/streams").json()
    assert len(lst) == 2
    chan = [x for x in lst if x["url"].endswith("zerator")][0]
    assert chan["enabled"] and chan["channel"] and chan["state"] == "processing"

    # œil barré : le traitement en attente est annulé, plus aucun clip
    r = client.patch(f"/api/streams/{chan['id']}", json={"enabled": False}).json()
    assert r["enabled"] is False and r["state"] == "paused"
    with db.session() as s:
        jobs = s.exec(select(Job).where(Job.stream_id == chan["id"])).all()
    assert jobs and all(j.status == "cancelled" for j in jobs)

    # œil ouvert : le clipping repart
    r = client.patch(f"/api/streams/{chan['id']}", json={"enabled": True}).json()
    assert r["enabled"] and r["state"] == "processing"
    assert client.delete(f"/api/streams/{chan['id']}").json()["ok"]
    assert len(client.get("/api/streams").json()) == 1


def test_clip_job_of_disabled_stream_is_cancelled(lc_home):
    from liveclipper.services import job_queue
    with db.session() as s:
        st = Stream(url="https://www.twitch.tv/videos/1", enabled=False)
        s.add(st)
        s.commit()
        s.refresh(st)
    job = job_queue.submit("clip", url=st.url, stream_id=st.id)
    assert job_queue.run_sync(job.id).status == "cancelled"


def test_watcher_starts_recording_when_channel_goes_live(lc_home):
    from liveclipper.services import job_queue
    w = streams.StreamWatcher(job_queue)
    live = {"on": False}
    probes = []
    w.is_live = lambda url: probes.append(url) or live["on"]
    with db.session() as s:
        s.add(Stream(url="https://www.twitch.tv/zerator"))
        s.add(Stream(url="https://www.twitch.tv/off", enabled=False))   # œil barré : jamais vérifiée
        s.add(Stream(url="https://www.twitch.tv/videos/9"))               # vidéo : pas de surveillance
        s.commit()
    t = datetime(2026, 11, 25, 20, 0, tzinfo=timezone.utc)
    assert w.tick(t) == [] and probes == ["https://www.twitch.tv/zerator"]
    live["on"] = True
    assert w.tick(t + timedelta(minutes=2)) == []          # vérifiée il y a moins de 5 min
    started = w.tick(t + timedelta(minutes=6))
    assert len(started) == 1 and started[0].url == "https://www.twitch.tv/zerator"
    assert w.tick(t + timedelta(minutes=20)) == []          # déjà en traitement


def test_live_segment_not_clipped_when_eye_closed(lc_home, tmp_path):
    from liveclipper.jobs.queue import JobContext
    from liveclipper.services import job_queue, live_manager
    with db.session() as s:
        st = Stream(url="https://www.twitch.tv/zerator", enabled=False)
        s.add(st)
        s.commit()
        s.refresh(st)
    job = job_queue.submit("clip", url=st.url, stream_id=st.id)
    seg = tmp_path / "t.ts"
    seg.write_bytes(b"x")
    live_manager._submit_segment(JobContext(job_queue, job.id), seg, 0, {"id": "x"}, {}, 600.0)
    assert not seg.exists()
    with db.session() as s:
        assert s.exec(select(Job).where(Job.id != job.id)).all() == []
