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


def test_campaign_distinct_clips_when_possible(lc_home):
    for i, sc in enumerate([9, 8, 7]):
        _clip(f"c{i}", sc)
    _clip("rej", 10, "rejected")
    a, b = _acc("A"), _acc("B")
    with db.session() as s:
        camp = Campaign(count=2, account_ids=[a.id, b.id])
        s.add(camp)
        s.commit()
        s.refresh(camp)
    now = datetime(2026, 11, 25, 9, 0, tzinfo=PARIS)
    pubs = scheduler.plan_campaigns(now, random.Random(0))
    got = {}
    for p in pubs:
        got.setdefault(p.account_id, []).append(p.clip_id)
    assert got[a.id] == ["c0", "c1"]                     # meilleurs clips, validation automatique
    assert got[b.id][0] == "c2"                          # d'abord un clip encore inutilisé
    assert len(got[b.id]) == 2 and got[b.id][1] in ("c0", "c1")   # puis réutilisation faute de stock
    assert "rej" not in sum(got.values(), [])           # jamais un clip rejeté
    assert all(p.campaign_id == camp.id for p in pubs)
    assert scheduler.plan_campaigns(now, random.Random(0)) == []   # pas de doublon
    # fin de campagne quand tout est publié
    with db.session() as s:
        for p in s.exec(__import__("sqlmodel").select(Publication)).all():
            p.status = "published"
            s.add(p)
        s.commit()
    scheduler.plan_campaigns(now)
    with db.session() as s:
        assert s.get(Campaign, camp.id).status == "done"


def test_campaign_respects_daily_quota(lc_home):
    for i in range(6):
        _clip(f"c{i}", 9 - i)
    a = _acc("A")
    with db.session() as s:
        s.exec(__import__("sqlmodel").select(Account)).first().max_per_day = 2
        acc = s.get(Account, a.id)
        acc.max_per_day = 2
        s.add(acc)
        s.add(Campaign(count=5, account_ids=[a.id]))
        s.commit()
    now = datetime(2026, 11, 25, 9, 0, tzinfo=PARIS)
    pubs = scheduler.plan_campaigns(now, random.Random(0), horizon_hours=48)
    days = [p.scheduled_at.astimezone(PARIS).date() for p in pubs]
    # horizon de 48 h depuis 9 h : 25/11 (2), 26/11 (2), 27/11 avant 9 h (1) ; jamais plus de 2 par jour
    assert len(pubs) == 5 and max(days.count(d) for d in set(days)) == 2
    assert all(p.scheduled_at.astimezone(PARIS) <= now + timedelta(hours=48) for p in pubs)


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
        assert row["target"] == 50 and row["scheduled"] == 1     # 1 seul clip en stock pour l'instant
        assert client.get("/api/campaigns/stock").json() == {"clips": 1, "unused": 0}
        assert client.post(f"/api/campaigns/{r['id']}/cancel").json()["ok"]
        assert client.get("/api/campaigns").json()[0]["status"] == "cancelled"
        assert client.get("/api/publications").json()[0]["status"] == "cancelled"
