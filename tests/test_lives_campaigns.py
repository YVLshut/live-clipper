"""Onglet Lives (live en direct par tranches) et onglet Publier (campagnes N clips par compte)."""
from __future__ import annotations

import random
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from liveclipper import db
from liveclipper.models import Account, Campaign, Clip, Job, Publication, Source
from liveclipper.publish import scheduler

PARIS = timezone(timedelta(hours=1))


# ------------------------------------------------------------------ migration de la base existante
def test_old_database_gets_new_columns(lc_home):
    lc_home.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(lc_home / "liveclipper.db")
    con.execute("CREATE TABLE publication (id INTEGER PRIMARY KEY, clip_id VARCHAR NOT NULL, account_id INTEGER NOT NULL,"
                " status VARCHAR NOT NULL, scheduled_at DATETIME NOT NULL, attempts INTEGER NOT NULL, auto BOOLEAN NOT NULL,"
                " created_at DATETIME NOT NULL)")
    con.execute("INSERT INTO publication VALUES (1, 'c', 1, 'published', '2026-11-01 10:00:00', 1, 0, '2026-11-01 10:00:00')")
    con.commit()
    con.close()
    db.reset_engine()
    with db.session() as s:
        p = s.get(Publication, 1)
        assert p.campaign_id is None and p.status == "published"


# ------------------------------------------------------------------ live en direct
@pytest.fixture
def live_env(lc_home, sample_video, monkeypatch):
    from liveclipper import services
    from liveclipper.jobs import live as live_mod
    lm = services.live_manager
    # un vrai live renvoie à chaque ouverture le flux « en cours » : on simule 3 morceaux successifs
    parts = []
    for i, (a, b) in enumerate([(0, 10), (10, 20), (20, 27)]):
        f = lc_home.parent / f"flux_{i}.ts"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(a), "-to", str(b), "-i", str(sample_video),
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-f", "mpegts", str(f)], check=True)
        parts.append(f)
    calls = {"n": 0}

    def fake_stream(url):
        calls["n"] += 1
        if calls["n"] > len(parts):   # le live est terminé
            raise subprocess.CalledProcessError(1, ["yt-dlp"], "", "ERROR: not currently live")
        return str(parts[calls["n"] - 1])

    monkeypatch.setattr(lm, "stream_url", fake_stream)
    monkeypatch.setattr(lm, "segment_seconds", lambda: 10.0)
    monkeypatch.setattr(lm, "retry_wait", 0.1)
    monkeypatch.setattr(live_mod, "MIN_SEGMENT", 3.0)
    return lm


def test_live_job_is_detected_and_recorded_in_segments(live_env, monkeypatch):
    from liveclipper.jobs import clip_job
    from liveclipper.pipeline import download
    from liveclipper.services import job_queue
    monkeypatch.setattr(download, "probe", lambda url: {
        "id": "v999", "extractor_key": "Twitch", "uploader": "StreamerLive", "uploader_id": "streamerlive",
        "title": "Live du soir", "is_live": True, "webpage_url": url})
    job = job_queue.submit("clip", url="https://www.twitch.tv/streamerlive", options={"max_clips": 2})
    j = job_queue.run_sync(job.id)
    assert j.kind == "live" and j.status == "running" and j.step == "record"
    live_env.join(job.id, 60)
    with db.session() as s:
        j = s.get(Job, job.id)
        segs = s.exec(__import__("sqlmodel").select(Job).where(Job.kind == "clip", Job.id != job.id)).all()
    assert j.status == "done", (j.status, j.error, j.message)
    assert j.extra["segments"] == len(segs) >= 2
    assert 18 < j.extra["recorded"] < 40
    first = sorted(segs, key=lambda x: x.id)[0]
    assert len(segs) == 3
    assert first.options["live_source"]["author"] == "StreamerLive"
    assert first.options["segment"] == 0 and first.url.endswith(".ts")
    assert "Live terminé" in j.message


def test_live_segment_is_credited_to_the_live(live_env, monkeypatch, lc_home):
    """Une tranche clippée est créditée au vrai live (auteur + lien), pas au fichier local."""
    from conftest import has_flite, whisper_tiny_available
    if not (has_flite() and whisper_tiny_available()):
        pytest.skip("Whisper tiny / flite indisponible")
    from liveclipper import config
    from liveclipper.pipeline import highlights
    from liveclipper.services import job_queue
    config.update({"whisper_model": "tiny", "device": "cpu", "language": "en"})
    monkeypatch.setattr(highlights, "ask_claude", lambda *a: [
        {"start": "00:00:01", "end": "00:00:08", "score": 8, "title": "T", "hook": "H", "caption": "C",
         "hashtags": []}])
    from liveclipper import secrets
    secrets.set(secrets.ANTHROPIC_KEY, "sk-test")
    seg = lc_home / "live_tranche001.ts"
    import shutil
    shutil.copy(live_env.stream_url("x"), seg)
    src = {"id": "twitch_v999", "url": "https://www.twitch.tv/videos/999", "author": "StreamerLive",
           "author_url": "https://www.twitch.tv/streamerlive", "title": "Live du soir", "platform": "Twitch",
           "date": "2026-11-25", "was_live": True}
    job = job_queue.submit("clip", url=str(seg), options={"live_source": src, "segment": 0, "min_len": 3,
                                                         "max_len": 8})
    j = job_queue.run_sync(job.id)
    assert j.status == "done", j.error
    with db.session() as s:
        clip = s.exec(__import__("sqlmodel").select(Clip)).first()
        source = s.get(Source, clip.source_id)
    assert source.author == "StreamerLive" and source.url == "https://www.twitch.tv/videos/999"
    assert source.title == "Live du soir (partie 1)"
    assert not seg.exists()   # tranche brute supprimée après clipping


# ------------------------------------------------------------------ campagnes
def _clip(cid, score, status="pending"):
    with db.session() as s:
        if not s.get(Source, "src"):
            s.add(Source(id="src", url="https://twitch.tv/videos/1", author="A", platform="Twitch"))
        s.add(Clip(id=cid, source_id="src", file=f"/tmp/{cid}.mp4", start=0, end=20, duration=20, score=score,
                   status=status))
        s.commit()


def _acc(name, **kw):
    a = Account(platform="tiktok", name=name, status="connected", min_score=0, max_per_day=10,
                time_windows=[["00:00", "23:59"]], delay_min_minutes=10, delay_max_minutes=10, **kw)
    with db.session() as s:
        s.add(a)
        s.commit()
        s.refresh(a)
    return a


def _publish_all(at: datetime):
    with db.session() as s:
        for p in s.exec(__import__("sqlmodel").select(Publication).where(Publication.status == "scheduled")).all():
            p.status, p.published_at = "published", at
            s.add(p)
        s.commit()


def test_campaign_one_clip_per_hour_distinct_when_possible(lc_home):
    for i, sc in enumerate([9, 8, 7]):
        _clip(f"c{i}", sc)
    _clip("rej", 10, "rejected")
    a, b = _acc("A"), _acc("B")
    with db.session() as s:
        camp = Campaign(count=2, account_ids=[a.id, b.id])
        s.add(camp)
        s.commit()
        s.refresh(camp)
    t0 = datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc)
    pubs = scheduler.plan_campaigns(t0, random.Random(0))
    got = {p.account_id: p.clip_id for p in pubs}
    assert got == {a.id: "c0", b.id: "c1"}          # 1 seul post à la fois, clips différents
    assert all(p.scheduled_at == t0 for p in pubs)   # premier post tout de suite
    assert scheduler.plan_campaigns(t0, random.Random(0)) == []   # rien tant que le post n'est pas parti
    _publish_all(t0)
    pubs = scheduler.plan_campaigns(t0 + timedelta(minutes=1), random.Random(0))
    got = {p.account_id: p for p in pubs}
    assert got[a.id].clip_id == "c2"                 # clip encore inutilisé ailleurs
    assert got[b.id].clip_id == "c0"                 # stock épuisé : réutilisation
    for p in pubs:                                    # 1 heure (+ 0-5 min) après le post précédent
        assert timedelta(hours=1) <= p.scheduled_at - t0 <= timedelta(hours=1, minutes=5)
    assert "rej" not in [p.clip_id for p in pubs]
    _publish_all(t0 + timedelta(hours=1))
    scheduler.plan_campaigns(t0 + timedelta(hours=1, minutes=1))
    with db.session() as s:
        assert s.get(Campaign, camp.id).status == "done"


def test_campaign_stops_retrying_after_repeated_failures(lc_home):
    for i in range(6):
        _clip(f"c{i}", 9 - i)
    a = _acc("A")
    with db.session() as s:
        camp = Campaign(count=10, account_ids=[a.id])
        s.add(camp)
        s.commit()
        s.refresh(camp)
    t = datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc)
    for i in range(3):
        pubs = scheduler.plan_campaigns(t, random.Random(0))
        assert len(pubs) == 1
        with db.session() as s:
            p = s.get(Publication, pubs[0].id)
            p.status, p.error = "failed", "Erreur TikTok"
            s.add(p)
            s.commit()
        t = pubs[0].scheduled_at + timedelta(minutes=1)
        if i < 2:   # après un échec, on attend quand même l'intervalle d'une heure
            nxt = scheduler.plan_campaigns(t, random.Random(0))
            assert nxt and nxt[0].scheduled_at >= pubs[0].scheduled_at + timedelta(hours=1)
            with db.session() as s:
                s.delete(s.get(Publication, nxt[0].id))
                s.commit()
    assert scheduler.plan_campaigns(t + timedelta(hours=5)) == []   # 3 échecs d'affilée : en pause


def test_overdue_posts_are_respaced(lc_home):
    for i in range(3):
        _clip(f"c{i}", 8)
    a = _acc("A", )
    past = datetime.now(timezone.utc) - timedelta(hours=3)
    with db.session() as s:
        for i in range(3):
            s.add(Publication(clip_id=f"c{i}", account_id=a.id, scheduled_at=past + timedelta(minutes=i)))
        s.commit()
        due = s.exec(__import__("sqlmodel").select(Publication).order_by(Publication.scheduled_at)).all()
    acc = scheduler.next_slot  # noqa: F841
    with db.session() as s:
        account = s.get(Account, a.id)
    go = scheduler.respace_overdue(account, due, random.Random(0))
    assert [p.id for p in go] == [due[0].id]
    with db.session() as s:
        later = sorted(s.get(Publication, p.id).scheduled_at for p in due[1:])
    nowu = datetime.now(timezone.utc)
    assert all(t > nowu for t in later)
    assert later[1] - later[0] >= timedelta(minutes=9)   # délai du compte (10 min) entre deux posts


def test_campaign_api(lc_home):
    from liveclipper.main import create_app
    _clip("c0", 9)
    a = _acc("A")
    off = Account(platform="instagram", name="B", status="reconnect")
    with db.session() as s:
        s.add(off)
        s.commit()
        s.refresh(off)
    with TestClient(create_app(start_workers=False)) as client:
        assert client.post("/api/campaigns", json={"count": 0, "account_ids": [a.id]}).status_code == 400
        r = client.post("/api/campaigns", json={"count": 50, "account_ids": [a.id, off.id]}).json()
        assert r["count"] == 50 and "non connectés" in r["warning"]
        lst = client.get("/api/campaigns").json()
        row = [x for x in lst[0]["accounts"] if x["account_id"] == a.id][0]
        assert row["target"] == 50 and row["scheduled"] == 1 and row["next_at"]   # 1 post à la fois
        assert client.get("/api/campaigns/stock").json() == {"clips": 1, "unused": 0}
        assert client.post(f"/api/campaigns/{r['id']}/cancel").json()["ok"]
        assert client.get("/api/campaigns").json()[0]["status"] == "cancelled"
        assert client.get("/api/publications").json()[0]["status"] == "cancelled"
