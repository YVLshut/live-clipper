"""Publication : API Instagram / TikTok simulées, règles de planification, worker, file et historique."""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from liveclipper import db
from liveclipper.errors import PublishError, VerificationRequired
from liveclipper.models import Account, Clip, Publication, Source
from liveclipper.publish import instagram_api as ig, scheduler, tiktok_api as tt

PARIS = timezone(timedelta(hours=1))


@pytest.fixture
def video(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00" * 2048)
    return f


# ------------------------------------------------------------------ API officielles
@respx.mock
def test_instagram_publish_reel(video):
    create = respx.post(f"{ig.GRAPH}/1784/media").mock(
        return_value=httpx.Response(200, json={"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v/C1"}))
    up = respx.post("https://rupload.facebook.com/ig-api-upload/v/C1").mock(
        return_value=httpx.Response(200, json={"success": True}))
    respx.get(f"{ig.GRAPH}/C1").mock(side_effect=[
        httpx.Response(200, json={"status_code": "IN_PROGRESS"}),
        httpx.Response(200, json={"status_code": "FINISHED"})])
    pub = respx.post(f"{ig.GRAPH}/1784/media_publish").mock(return_value=httpx.Response(200, json={"id": "M9"}))
    respx.get(f"{ig.GRAPH}/M9").mock(return_value=httpx.Response(200, json={"permalink": "https://instagram.com/reel/abc"}))
    url = ig.publish_reel("1784", "tok", video, "Légende 🎥", poll_every=0)
    assert url == "https://instagram.com/reel/abc"
    body = dict(x.split("=", 1) for x in create.calls[0].request.content.decode().split("&"))
    assert body["media_type"] == "REELS" and body["upload_type"] == "resumable"
    assert up.calls[0].request.headers["file_size"] == "2048"
    assert up.calls[0].request.headers["Authorization"] == "OAuth tok"
    assert "creation_id=C1" in pub.calls[0].request.content.decode()


@respx.mock
def test_instagram_errors(video):
    respx.post(f"{ig.GRAPH}/1784/media").mock(return_value=httpx.Response(400, json={
        "error": {"code": 190, "message": "Error validating access token"}}))
    with pytest.raises(PublishError) as e:
        ig.publish_reel("1784", "tok", video, "x", poll_every=0)
    assert e.value.reconnect and "reconnecte" in e.value.message


@respx.mock
def test_tiktok_publish_video(video):
    respx.post(f"{tt.API}/post/publish/creator_info/query/").mock(return_value=httpx.Response(200, json={
        "data": {"privacy_level_options": ["SELF_ONLY"], "creator_username": "moi"}, "error": {"code": "ok"}}))
    init = respx.post(f"{tt.API}/post/publish/video/init/").mock(return_value=httpx.Response(200, json={
        "data": {"publish_id": "P1", "upload_url": "https://upload.tiktok.test/u1"}, "error": {"code": "ok"}}))
    put = respx.put("https://upload.tiktok.test/u1").mock(return_value=httpx.Response(201))
    respx.post(f"{tt.API}/post/publish/status/fetch/").mock(side_effect=[
        httpx.Response(200, json={"data": {"status": "PROCESSING_UPLOAD"}, "error": {"code": "ok"}}),
        httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [777]},
                                  "error": {"code": "ok"}})])
    url = tt.publish_video("tok", video, "Ma légende", "PUBLIC_TO_EVERYONE", poll_every=0)
    assert url == "https://www.tiktok.com/@moi/video/777"
    body = json.loads(init.calls[0].request.content)
    assert body["post_info"]["privacy_level"] == "SELF_ONLY"   # seule option permise (app non auditée)
    assert body["source_info"] == {"source": "FILE_UPLOAD", "video_size": 2048, "chunk_size": 2048,
                                   "total_chunk_count": 1}
    assert put.calls[0].request.headers["Content-Range"] == "bytes 0-2047/2048"


def test_tiktok_chunk_plan():
    assert tt.chunk_plan(1000) == (1000, 1)
    size = 150 * 1024 * 1024
    cs, n = tt.chunk_plan(size)
    assert cs == 10 * 1024 * 1024 and n == 15


@respx.mock
def test_tiktok_failed_reason(video):
    respx.post(f"{tt.API}/post/publish/creator_info/query/").mock(return_value=httpx.Response(200, json={
        "data": {"privacy_level_options": ["SELF_ONLY"]}, "error": {"code": "ok"}}))
    respx.post(f"{tt.API}/post/publish/video/init/").mock(return_value=httpx.Response(200, json={
        "data": {"publish_id": "P1", "upload_url": "https://upload.tiktok.test/u1"}, "error": {"code": "ok"}}))
    respx.put("https://upload.tiktok.test/u1").mock(return_value=httpx.Response(201))
    respx.post(f"{tt.API}/post/publish/status/fetch/").mock(return_value=httpx.Response(200, json={
        "data": {"status": "FAILED", "fail_reason": "duration_check_failed"}, "error": {"code": "ok"}}))
    with pytest.raises(PublishError, match="durée de vidéo refusée"):
        tt.publish_video("tok", video, "x", None, poll_every=0)


# ------------------------------------------------------------------ règles de planification
def test_next_slot_windows_and_quota():
    rng = random.Random(1)
    start = datetime(2026, 11, 25, 8, 0, tzinfo=PARIS)
    win = [["10:00", "12:00"], ["18:00", "22:00"]]
    s1 = scheduler.next_slot(start, win, [], 2, 30, 30, rng)
    assert s1 == datetime(2026, 11, 25, 10, 0, tzinfo=PARIS)
    s2 = scheduler.next_slot(start, win, [s1], 2, 30, 30, rng)
    assert s2 == datetime(2026, 11, 25, 10, 30, tzinfo=PARIS)        # délai respecté
    s3 = scheduler.next_slot(start, win, [s1, s2], 2, 30, 30, rng)
    assert s3 == datetime(2026, 11, 26, 10, 0, tzinfo=PARIS)         # quota du jour atteint
    late = datetime(2026, 11, 25, 12, 30, tzinfo=PARIS)
    assert scheduler.next_slot(late, win, [], 3, 0, 0, rng) == datetime(2026, 11, 25, 18, 0, tzinfo=PARIS)
    inside = datetime(2026, 11, 25, 19, 15, tzinfo=PARIS)
    assert scheduler.next_slot(inside, win, [], 3, 0, 0, rng) == inside


def test_next_slot_random_delay_range():
    start = datetime(2026, 11, 25, 9, 0, tzinfo=PARIS)
    prev = datetime(2026, 11, 25, 9, 0, tzinfo=PARIS)
    for seed in range(20):
        s = scheduler.next_slot(start, [["00:00", "23:59"]], [prev], 10, 45, 120, random.Random(seed))
        assert timedelta(minutes=45) <= s - prev <= timedelta(minutes=120)


def _seed(score=8.5, status="approved", clip_id="src_000010", video_path="/tmp/x.mp4"):
    with db.session() as s:
        if not s.get(Source, "src"):
            s.add(Source(id="src", url="https://twitch.tv/videos/1", author="Streamer", platform="Twitch"))
        s.add(Clip(id=clip_id, source_id="src", file=str(video_path), start=10, end=40, duration=30, score=score,
                   title="T", hook="H", caption="Légende", hashtags=["#a"], status=status))
        s.commit()


def _account(**kw):
    a = Account(platform="tiktok", name="Compte", status="connected", **kw)
    with db.session() as s:
        s.add(a)
        s.commit()
        s.refresh(a)
    return a


def test_plan_auto_rules(lc_home):
    _seed(9, "approved", "c1")
    _seed(8, "pending", "c2")
    _seed(5, "approved", "c3")
    _seed(9.5, "approved", "c4")
    off = _account()
    assert scheduler.plan_auto(off) == []                       # publication auto désactivée par défaut
    a = _account(auto_publish=True, min_score=7, max_per_day=1, time_windows=[["00:00", "23:59"]],
                 delay_min_minutes=10, delay_max_minutes=20)
    now = datetime(2026, 11, 25, 9, 0, tzinfo=PARIS)
    pubs = scheduler.plan_auto(a, now, random.Random(0))
    # c2 non approuvé, c3 score trop bas ; 1 par jour -> c4 aujourd'hui, c1 demain
    assert [p.clip_id for p in pubs] == ["c4", "c1"]
    assert pubs[1].scheduled_at.astimezone(PARIS).date() == now.date() + timedelta(days=1)
    assert all(p.auto for p in pubs)
    assert scheduler.plan_auto(a, now, random.Random(0)) == []  # pas de doublon
    b = _account(auto_publish=True, require_approval=False, min_score=7, max_per_day=5,
                 time_windows=[["00:00", "23:59"]], delay_min_minutes=0, delay_max_minutes=0)
    assert {p.clip_id for p in scheduler.plan_auto(b, now)} == {"c1", "c2", "c4"}


# ------------------------------------------------------------------ worker + API
@pytest.fixture
def client(lc_home, monkeypatch):
    from liveclipper.main import create_app
    with TestClient(create_app(start_workers=False)) as c:
        yield c


def _pubs(client):
    return client.get("/api/publications").json()


def test_publish_flow_api_success_and_failure(client, video):
    from liveclipper.services import publish_worker
    _seed(video_path=video)
    a = _account(username="moi")
    r = client.post("/api/publications", json={"clip_id": "src_000010", "account_ids": [a.id]})
    assert r.json()["created"] == 1
    r = client.post("/api/publications", json={"clip_id": "src_000010", "account_ids": [a.id]})
    assert r.status_code == 400 and "déjà programmé" in r.json()["detail"]
    pid = _pubs(client)[0]["id"]

    seen = {}

    def ok(acc, path, caption, progress):
        seen["caption"] = caption
        return "https://www.tiktok.com/@moi/video/1"

    publish_worker.api_publishers["tiktok"] = ok
    publish_worker.publish(pid)
    p = _pubs(client)[0]
    assert p["status"] == "published" and p["post_url"].endswith("/video/1")
    assert "🎥 Source : Streamer — https://twitch.tv/videos/1" in seen["caption"]

    # échec avec reconnexion nécessaire
    _seed(clip_id="c2", video_path=video)
    client.post("/api/publications", json={"clip_id": "c2", "account_ids": [a.id]})
    pid2 = [x for x in _pubs(client) if x["clip_id"] == "c2"][0]["id"]

    def boom(*_a):
        raise PublishError("La connexion TikTok a expiré : reconnecte le compte.", reconnect=True)

    publish_worker.api_publishers["tiktok"] = boom
    publish_worker.publish(pid2)
    p = [x for x in _pubs(client) if x["id"] == pid2][0]
    assert p["status"] == "failed" and "expiré" in p["error"]
    assert client.get("/api/accounts").json()[0]["status"] == "reconnect"
    # Réessayer -> remis en file
    publish_worker.api_publishers["tiktok"] = ok
    assert client.post(f"/api/publications/{pid2}/retry").json()["ok"]
    assert [x for x in _pubs(client) if x["id"] == pid2][0]["status"] == "scheduled"
    publish_worker.publish(pid2)
    assert [x for x in _pubs(client) if x["id"] == pid2][0]["status"] == "published"


def test_browser_verification_pauses(client, video, lc_home):
    from liveclipper.services import publish_worker
    _seed(video_path=video)
    a = _account(mode="browser")
    client.post("/api/publications", json={"clip_id": "src_000010", "account_ids": [a.id]})
    pid = _pubs(client)[0]["id"]
    shot = lc_home / "shot.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls = []

    def captcha(browsers, aid, platform, path, caption, username):
        calls.append(aid)
        if len(calls) == 1:
            raise VerificationRequired("Vérification de sécurité requise", str(shot))
        return "https://www.tiktok.com/@moi"

    publish_worker.browser_publish = captcha
    publish_worker.publish(pid)
    p = _pubs(client)[0]
    assert p["status"] == "paused" and p["screenshot_url"]
    assert client.get(p["screenshot_url"]).status_code == 200
    from liveclipper.events import bus
    assert any(m["type"] == "notification" and "pause" in m["data"]["message"] for m in bus.history)
    # l'utilisateur a traité la vérification -> Reprendre
    client.post(f"/api/publications/{pid}/retry")
    publish_worker.publish(pid)
    assert _pubs(client)[0]["status"] == "published"


def test_cannot_schedule_unapproved(client, video):
    _seed(status="pending", video_path=video)
    a = _account()
    r = client.post("/api/publications", json={"clip_id": "src_000010", "account_ids": [a.id]})
    assert r.status_code == 400 and "Approuve" in r.json()["detail"]


def test_scheduler_tick_enqueues_due(client, video):
    from liveclipper.services import scheduler as sched
    _seed(video_path=video)
    a = _account()
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    client.post("/api/publications", json={"clip_id": "src_000010", "account_ids": [a.id], "scheduled_at": future})
    got = []
    sched.enqueue, old = got.append, sched.enqueue
    sched._last_refresh = time.time()  # pas de rafraîchissement de jetons dans ce test
    try:
        sched.tick()
        assert got == []
        pid = _pubs(client)[0]["id"]
        with db.session() as s:
            p = s.get(Publication, pid)
            p.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            s.add(p)
            s.commit()
        sched.tick()
        assert got == [pid]
    finally:
        sched.enqueue = old
