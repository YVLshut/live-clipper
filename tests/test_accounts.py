"""Comptes : OAuth Instagram/TikTok simulé (respx), jetons keyring, rafraîchissement, garde-fou captcha."""
from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from liveclipper.publish import guard, instagram_api as ig, tiktok_api as tt


@pytest.fixture
def client(lc_home, monkeypatch):
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)
    from liveclipper.main import create_app
    with TestClient(create_app(start_workers=False)) as c:
        yield c


def _new(client, platform="instagram", mode="api", name="Mon compte"):
    r = client.post("/api/accounts", json={"platform": platform, "name": name, "mode": mode})
    assert r.status_code == 200, r.text
    return r.json()


def test_connect_requires_app_credentials(client):
    a = _new(client)
    r = client.post(f"/api/accounts/{a['id']}/connect")
    assert r.status_code == 400 and "Paramètres" in r.json()["detail"]


@respx.mock
def test_instagram_oauth_flow(client):
    client.put("/api/settings", json={"meta_app_id": "111", "meta_app_secret": "sec"})
    a = _new(client)
    r = client.post(f"/api/accounts/{a['id']}/connect").json()
    q = parse_qs(urlparse(r["auth_url"]).query)
    assert q["client_id"] == ["111"] and "instagram_content_publish" in q["scope"][0]
    assert q["redirect_uri"] == ["http://localhost:47615/oauth/instagram/callback"]
    respx.get(f"{ig.GRAPH}/oauth/access_token", params={"code": "CODE"}).mock(
        return_value=httpx.Response(200, json={"access_token": "short"}))
    respx.get(f"{ig.GRAPH}/oauth/access_token", params={"grant_type": "fb_exchange_token"}).mock(
        return_value=httpx.Response(200, json={"access_token": "long", "expires_in": 5184000}))
    respx.get(f"{ig.GRAPH}/me/accounts").mock(return_value=httpx.Response(200, json={"data": [
        {"name": "Ma Page", "instagram_business_account": {"id": "1784", "username": "moncompte",
                                                            "profile_picture_url": "https://x/p.jpg"}}]}))
    page = client.get("/oauth/instagram/callback", params={"code": "CODE", "state": q["state"][0]})
    assert page.status_code == 200 and "Compte connecté" in page.text
    acc = client.get("/api/accounts").json()[0]
    assert acc["status"] == "connected" and acc["username"] == "moncompte" and acc["external_id"] == "1784"
    from liveclipper.publish import accounts
    assert accounts.load_tokens(a["id"])["access_token"] == "long"
    # state réutilisé -> refus
    page = client.get("/oauth/instagram/callback", params={"code": "CODE", "state": q["state"][0]})
    assert page.status_code == 400 and "expirée" in page.text


@respx.mock
def test_instagram_multiple_accounts_choice(client):
    client.put("/api/settings", json={"meta_app_id": "111", "meta_app_secret": "sec"})
    a = _new(client)
    url = client.post(f"/api/accounts/{a['id']}/connect").json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    respx.get(f"{ig.GRAPH}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 5184000}))
    respx.get(f"{ig.GRAPH}/me/accounts").mock(return_value=httpx.Response(200, json={"data": [
        {"name": "P1", "instagram_business_account": {"id": "1", "username": "un"}},
        {"name": "P2", "instagram_business_account": {"id": "2", "username": "deux"}}]}))
    # secours : l'utilisateur colle l'URL de retour
    r = client.post(f"/api/accounts/{a['id']}/oauth-code",
                    json={"url": f"https://exemple.fr/cb?code=C&state={state}"})
    acc = r.json()
    assert acc["status"] == "reconnect" and len(acc["pending_choices"]) == 2
    acc = client.post(f"/api/accounts/{a['id']}/choose", json={"external_id": "2"}).json()
    assert acc["status"] == "connected" and acc["username"] == "deux" and acc["pending_choices"] is None


@respx.mock
def test_tiktok_oauth_pkce_and_refresh(client):
    client.put("/api/settings", json={"tiktok_client_key": "ck", "tiktok_client_secret": "cs"})
    a = _new(client, "tiktok")
    q = parse_qs(urlparse(client.post(f"/api/accounts/{a['id']}/connect").json()["auth_url"]).query)
    assert q["client_key"] == ["ck"] and len(q["code_challenge"][0]) == 64
    token_route = respx.post(f"{tt.API}/oauth/token/").mock(return_value=httpx.Response(200, json={
        "access_token": "act", "expires_in": 86400, "refresh_token": "rft", "refresh_expires_in": 31536000,
        "open_id": "oid", "scope": "video.publish"}))
    respx.get(f"{tt.API}/user/info/").mock(return_value=httpx.Response(200, json={
        "data": {"user": {"username": "tiktokeur", "avatar_url": "https://x/a.jpg"}}, "error": {"code": "ok"}}))
    page = client.get("/oauth/tiktok/callback", params={"code": "C", "state": q["state"][0]})
    assert page.status_code == 200
    body = parse_qs(token_route.calls[0].request.content.decode())
    assert body["code_verifier"][0] and body["grant_type"] == ["authorization_code"]
    acc = client.get("/api/accounts").json()[0]
    assert acc["status"] == "connected" and acc["username"] == "tiktokeur"

    from liveclipper.publish import accounts
    tok = accounts.load_tokens(a["id"])
    tok["expires_at"] = time.time() + 30   # expire bientôt
    accounts.save_tokens(a["id"], tok)
    token_route.mock(return_value=httpx.Response(200, json={
        "access_token": "act2", "expires_in": 86400, "refresh_token": "rft2", "open_id": "oid"}))
    assert accounts.valid_token(accounts.get_account(a["id"])) == "act2"
    assert accounts.load_tokens(a["id"])["refresh_token"] == "rft2"

    # refresh refusé -> compte à reconnecter
    tok = accounts.load_tokens(a["id"])
    tok["expires_at"] = 0
    accounts.save_tokens(a["id"], tok)
    token_route.mock(return_value=httpx.Response(400, json={"error": "invalid_grant", "error_description": "x"}))
    accounts.refresh_all()
    assert client.get("/api/accounts").json()[0]["status"] == "reconnect"


def test_rules_validation(client):
    a = _new(client)
    r = client.patch(f"/api/accounts/{a['id']}", json={"time_windows": [["20:00", "18:00"]]})
    assert r.status_code == 400 and "Plage horaire" in r.json()["detail"]
    r = client.patch(f"/api/accounts/{a['id']}", json={"auto_publish": True, "min_score": 8, "max_per_day": 2,
                                                      "time_windows": [["09:00", "12:00"]],
                                                      "delay_min_minutes": 30, "delay_max_minutes": 60})
    acc = r.json()
    assert acc["auto_publish"] and acc["min_score"] == 8 and acc["time_windows"] == [["09:00", "12:00"]]
    assert acc["require_approval"] is True   # par défaut, approbation manuelle requise


def test_delete_account(client, lc_home):
    a = _new(client, mode="browser")
    from liveclipper import paths
    (paths.profiles_dir() / str(a["id"])).mkdir()
    assert client.delete(f"/api/accounts/{a['id']}").json()["ok"]
    assert client.get("/api/accounts").json() == []
    assert not (paths.profiles_dir() / str(a["id"])).exists()


def test_guard_detect_in():
    assert guard.detect_in("https://www.instagram.com/challenge/abc/", "")
    assert guard.detect_in("https://www.tiktok.com/upload", "Faites glisser le curseur pour compléter le puzzle")
    assert guard.detect_in("https://x", "Please verify it's you to continue")
    assert guard.detect_in("https://www.tiktok.com/tiktokstudio/upload", "Publier ta vidéo") is None


def test_guard_on_real_page():
    """Page locale avec un faux captcha, dans un vrai Chromium headless."""
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        try:
            b = p.chromium.launch()
        except Exception:
            b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Chromium indisponible : {e}")
    try:
        page = b.new_page()
        page.set_content("<h1>Upload</h1><div>Prêt à publier</div>")
        assert guard.detect(page) is None
        page.set_content('<div class="captcha-container"><iframe title="CAPTCHA"></iframe>'
                         "<p>Faites glisser la pièce</p></div>")
        assert "captcha" in guard.detect(page)
    finally:
        b.close()
        p.stop()
