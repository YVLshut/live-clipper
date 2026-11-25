"""Mode navigateur : ouverture de la fenêtre de connexion, replis Edge -> Chrome -> Chromium, erreurs visibles."""
from __future__ import annotations

import pytest

from liveclipper import db
from liveclipper.errors import PublishError
from liveclipper.models import Account
from liveclipper.publish import browser


class FakeCtx:
    pages = []


class FakeChromium:
    def __init__(self, ok_channels):
        self.ok, self.tried = set(ok_channels), []

    def launch_persistent_context(self, channel=None, **kw):
        self.tried.append(channel or "chromium")
        if (channel or "chromium") in self.ok:
            return FakeCtx()
        raise Exception(f"Chromium distribution '{channel}' is not found" if channel else "Executable doesn't exist at /x")


class FakePW:
    def __init__(self, ok):
        self.chromium = FakeChromium(ok)


def test_fallback_edge_then_chrome(lc_home, monkeypatch):
    from liveclipper import config
    config.update({"browser_channel": "msedge"})   # réglage par défaut sous Windows
    b = browser.Browsers()
    b._pw = FakePW({"chrome"})
    assert isinstance(b.open(1), FakeCtx)
    assert b._pw.chromium.tried[:2] == ["msedge", "chrome"]


def test_all_browsers_missing_gives_clear_error(lc_home, monkeypatch):
    b = browser.Browsers()
    b._pw = FakePW(set())
    monkeypatch.setattr(browser, "install_chromium", lambda: (_ for _ in ()).throw(PublishError("réseau coupé")))
    with pytest.raises(PublishError) as e:
        b.open(1)
    assert "Impossible d'ouvrir un navigateur" in e.value.message and "msedge" in e.value.message


def test_chromium_downloaded_when_needed(lc_home, monkeypatch):
    b = browser.Browsers()
    b._pw = FakePW(set())
    def install():
        b._pw.chromium.ok.add("chromium")
    monkeypatch.setattr(browser, "install_chromium", install)
    assert isinstance(b.open(1), FakeCtx)


def test_login_error_is_shown_in_the_interface(lc_home, monkeypatch):
    from liveclipper.events import bus
    from liveclipper.publish.worker import PublishWorker
    with db.session() as s:
        a = Account(platform="tiktok", name="TT", mode="browser")
        s.add(a)
        s.commit()
        s.refresh(a)
    w = PublishWorker()

    def boom():
        raise PublishError("Le pilote du navigateur (Playwright) n'a pas pu démarrer : node introuvable")

    monkeypatch.setattr(w.browsers, "_playwright", boom)
    w._login(a.id)
    with db.session() as s:
        acc = s.get(Account, a.id)
    assert acc.status == "disconnected" and "ne s'est pas ouvert" in acc.status_message
    assert "Fenêtre de connexion ouverte" not in acc.status_message   # pas de faux bouton « J'ai terminé »
    assert any(m["type"] == "notification" and "Playwright" in m["data"]["message"] for m in bus.history)


def test_adding_browser_account_opens_login_window(lc_home):
    from fastapi.testclient import TestClient
    from liveclipper.main import create_app
    from liveclipper.services import publish_worker
    while not publish_worker.tasks.empty():
        publish_worker.tasks.get_nowait()
    with TestClient(create_app(start_workers=False)) as c:
        a = c.post("/api/accounts", json={"platform": "tiktok", "name": "TT", "mode": "browser"}).json()
    assert publish_worker.tasks.get_nowait() == ("login", a["id"])
