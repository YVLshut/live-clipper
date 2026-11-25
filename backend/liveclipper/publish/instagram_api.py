"""Instagram Graph API : connexion OAuth (Facebook Login) et publication de Reels.

Prérequis : compte Instagram professionnel relié à une Page Facebook, app Meta avec
Facebook Login + Instagram Graph API. La vidéo est envoyée par upload « resumable »
(rupload.facebook.com) : aucune URL publique n'est nécessaire.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import httpx

from ..errors import PublishError

log = logging.getLogger("liveclipper.instagram")

GRAPH_VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
RUPLOAD = f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}"
SCOPES = ["instagram_basic", "instagram_content_publish", "pages_show_list",
          "pages_read_engagement", "business_management"]
REFRESH_MARGIN = 7 * 24 * 3600   # rafraîchir le jeton longue durée 7 jours avant expiration


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60, connect=15), follow_redirects=True)


def _check(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        data = {}
    err = data.get("error") if isinstance(data, dict) else None
    if r.status_code >= 400 or err:
        err = err or {}
        code, msg = err.get("code"), err.get("message") or r.text[:300]
        sub = err.get("error_subcode")
        if code == 190 or r.status_code == 401:
            raise PublishError("La connexion Instagram a expiré : reconnecte le compte.", reconnect=True)
        if code in (4, 17, 32, 613):
            raise PublishError("Limite de requêtes Instagram atteinte : nouvel essai plus tard.")
        if code == 9 or sub == 2207042:
            raise PublishError("Limite de publications Instagram atteinte (50 par 24 h).")
        if code == 10 or code == 200:
            raise PublishError("Autorisation Instagram manquante : reconnecte le compte et accepte toutes "
                               "les autorisations demandées.", reconnect=True)
        raise PublishError(f"Erreur Instagram : {msg}")
    return data


def auth_url(app_id: str, redirect_uri: str, state: str) -> str:
    return f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?" + urlencode({
        "client_id": app_id, "redirect_uri": redirect_uri, "state": state,
        "scope": ",".join(SCOPES), "response_type": "code"})


def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str) -> dict:
    with _client() as c:
        short = _check(c.get(f"{GRAPH}/oauth/access_token", params={
            "client_id": app_id, "client_secret": app_secret, "redirect_uri": redirect_uri, "code": code}))
        return _long_lived(c, app_id, app_secret, short["access_token"])


def _long_lived(c: httpx.Client, app_id: str, app_secret: str, token: str) -> dict:
    data = _check(c.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": token}))
    return {"access_token": data["access_token"],
            "expires_at": time.time() + float(data.get("expires_in") or 60 * 24 * 3600)}


def needs_refresh(tokens: dict) -> bool:
    return float(tokens.get("expires_at") or 0) - time.time() < REFRESH_MARGIN


def refresh(tokens: dict, app_id: str, app_secret: str) -> dict:
    if float(tokens.get("expires_at") or 0) < time.time():
        raise PublishError("La connexion Instagram a expiré : reconnecte le compte.", reconnect=True)
    with _client() as c:
        return {**tokens, **_long_lived(c, app_id, app_secret, tokens["access_token"])}


def list_accounts(token: str) -> list[dict]:
    """Comptes Instagram professionnels accessibles via les Pages Facebook de l'utilisateur."""
    out = []
    url, params = f"{GRAPH}/me/accounts", {
        "fields": "name,instagram_business_account{id,username,profile_picture_url}",
        "access_token": token, "limit": 50}
    with _client() as c:
        while url:
            data = _check(c.get(url, params=params))
            for page in data.get("data", []):
                ig = page.get("instagram_business_account")
                if ig:
                    out.append({"id": ig["id"], "username": ig.get("username") or page.get("name"),
                                "picture": ig.get("profile_picture_url"), "page": page.get("name")})
            url, params = (data.get("paging") or {}).get("next"), None
    return out


def publish_reel(ig_user_id: str, token: str, video: Path, caption: str,
                 progress: Callable[[str], None] = lambda m: None, poll_every: float = 5.0,
                 max_wait: float = 900) -> str:
    """Publie un Reel et renvoie son lien (permalink)."""
    video = Path(video)
    size = video.stat().st_size
    with _client() as c:
        progress("Création du conteneur Reel…")
        cont = _check(c.post(f"{GRAPH}/{ig_user_id}/media", data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption,
            "share_to_feed": "true", "access_token": token}))
        cid = cont["id"]
        progress("Envoi de la vidéo…")
        with open(video, "rb") as f:
            up = c.post(cont.get("uri") or f"{RUPLOAD}/{cid}", content=f.read(), timeout=600, headers={
                "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
        _check(up)
        progress("Traitement par Instagram…")
        t0 = time.time()
        while True:
            st = _check(c.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": token}))
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise PublishError(f"Instagram a refusé la vidéo : {st.get('status') or code}")
            if time.time() - t0 > max_wait:
                raise PublishError("Instagram met trop de temps à traiter la vidéo.")
            time.sleep(poll_every)
        progress("Publication…")
        pub = _check(c.post(f"{GRAPH}/{ig_user_id}/media_publish",
                            data={"creation_id": cid, "access_token": token}))
        media_id = pub["id"]
        try:
            info = _check(c.get(f"{GRAPH}/{media_id}", params={"fields": "permalink", "access_token": token}))
            return info.get("permalink") or f"https://www.instagram.com/reel/{media_id}/"
        except PublishError:
            return f"https://www.instagram.com/reel/{media_id}/"
