"""TikTok : Login Kit (OAuth v2 + PKCE) et Content Posting API (Direct Post, upload de fichier).

Tant que l'app n'a pas passé l'audit TikTok, seules les publications privées (SELF_ONLY) sont acceptées.
"""
from __future__ import annotations

import hashlib
import logging
import math
import secrets as pysecrets
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import httpx

from ..errors import PublishError

log = logging.getLogger("liveclipper.tiktok")

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = ["user.info.basic", "video.publish", "video.upload"]
MAX_SINGLE_CHUNK = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024
REFRESH_MARGIN = 10 * 60

ERRORS = {
    "access_token_invalid": ("La connexion TikTok a expiré : reconnecte le compte.", True),
    "scope_not_authorized": ("Autorisation TikTok manquante : reconnecte le compte et accepte la publication.", True),
    "spam_risk_too_many_posts": ("TikTok limite le nombre de publications : réessaie plus tard.", False),
    "spam_risk_user_banned_from_posting": ("Ce compte TikTok ne peut plus publier pour le moment.", False),
    "reached_active_user_cap": ("Quota quotidien de l'app TikTok atteint.", False),
    "unaudited_client_can_only_post_to_private_accounts": (
        "Ton app TikTok n'est pas encore auditée : choisis la visibilité « Moi uniquement » "
        "dans les règles du compte.", False),
    "privacy_level_option_mismatch": ("Visibilité TikTok non autorisée pour ce compte.", False),
    "rate_limit_exceeded": ("Limite de requêtes TikTok atteinte : nouvel essai plus tard.", False),
}

FAIL_REASONS = {
    "file_format_check_failed": "format de fichier refusé",
    "duration_check_failed": "durée de vidéo refusée",
    "frame_rate_check_failed": "fréquence d'images refusée",
    "picture_size_check_failed": "résolution refusée",
    "internal": "erreur interne TikTok",
    "video_pull_failed": "téléchargement de la vidéo impossible",
    "publish_cancelled": "publication annulée",
    "auth_removed": "autorisation retirée",
    "spam_risk_too_many_posts": "trop de publications",
    "spam_risk": "risque de spam détecté",
}


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60, connect=15))


def _check(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        data = {}
    err = data.get("error") if isinstance(data, dict) else None
    code = (err or {}).get("code") if isinstance(err, dict) else None
    if code in (None, "", "ok") and r.status_code < 400 and "error_description" not in data:
        return data
    if "error_description" in data:   # endpoint OAuth
        if data.get("error") == "invalid_grant":
            raise PublishError("La connexion TikTok a expiré : reconnecte le compte.", reconnect=True)
        raise PublishError(f"Erreur TikTok : {data.get('error_description')}")
    msg, reconnect = ERRORS.get(code or "", (None, False))
    if msg:
        raise PublishError(msg, reconnect=reconnect)
    if r.status_code == 401:
        raise PublishError("La connexion TikTok a expiré : reconnecte le compte.", reconnect=True)
    raise PublishError(f"Erreur TikTok : {(err or {}).get('message') or code or r.text[:300]}")


def new_pkce() -> tuple[str, str]:
    """(verifier, challenge). TikTok attend le SHA-256 du verifier encodé en hexadécimal."""
    verifier = pysecrets.token_urlsafe(48)[:64]
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()


def auth_url(client_key: str, redirect_uri: str, state: str, challenge: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_key": client_key, "scope": ",".join(SCOPES), "response_type": "code",
        "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256"})


def _tokens(data: dict) -> dict:
    now = time.time()
    return {"access_token": data["access_token"], "refresh_token": data.get("refresh_token"),
            "open_id": data.get("open_id"), "scope": data.get("scope"),
            "expires_at": now + float(data.get("expires_in") or 86400),
            "refresh_expires_at": now + float(data.get("refresh_expires_in") or 365 * 86400)}


def exchange_code(client_key: str, client_secret: str, redirect_uri: str, code: str, verifier: str) -> dict:
    with _client() as c:
        return _tokens(_check(c.post(f"{API}/oauth/token/", data={
            "client_key": client_key, "client_secret": client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri, "code_verifier": verifier},
            headers={"Content-Type": "application/x-www-form-urlencoded"})))


def needs_refresh(tokens: dict) -> bool:
    return float(tokens.get("expires_at") or 0) - time.time() < REFRESH_MARGIN


def refresh(tokens: dict, client_key: str, client_secret: str) -> dict:
    if not tokens.get("refresh_token") or float(tokens.get("refresh_expires_at") or 0) < time.time():
        raise PublishError("La connexion TikTok a expiré : reconnecte le compte.", reconnect=True)
    with _client() as c:
        return {**tokens, **_tokens(_check(c.post(f"{API}/oauth/token/", data={
            "client_key": client_key, "client_secret": client_secret, "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"]},
            headers={"Content-Type": "application/x-www-form-urlencoded"})))}


def user_info(token: str) -> dict:
    with _client() as c:
        data = _check(c.get(f"{API}/user/info/", params={"fields": "open_id,avatar_url,display_name,username"},
                            headers={"Authorization": f"Bearer {token}"}))
    return (data.get("data") or {}).get("user") or {}


def creator_info(token: str) -> dict:
    with _client() as c:
        data = _check(c.post(f"{API}/post/publish/creator_info/query/", json={},
                             headers={"Authorization": f"Bearer {token}",
                                      "Content-Type": "application/json; charset=UTF-8"}))
    return data.get("data") or {}


def choose_privacy(options: list[str], wanted: str | None) -> str:
    if wanted and wanted in options:
        return wanted
    for p in ("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"):
        if p in options:
            return p
    return wanted or "SELF_ONLY"


def chunk_plan(size: int) -> tuple[int, int]:
    """(taille de morceau, nombre de morceaux) selon les règles de TikTok."""
    if size <= MAX_SINGLE_CHUNK:
        return size, 1
    return CHUNK, max(1, math.floor(size / CHUNK))


def publish_video(token: str, video: Path, caption: str, privacy: str | None = None,
                  progress: Callable[[str], None] = lambda m: None, poll_every: float = 5.0,
                  max_wait: float = 900) -> str:
    """Publie une vidéo (Direct Post) et renvoie le lien du post (ou du profil)."""
    video = Path(video)
    size = video.stat().st_size
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    info = creator_info(token)
    level = choose_privacy(info.get("privacy_level_options") or [], privacy)
    username = info.get("creator_username")
    chunk_size, count = chunk_plan(size)
    with _client() as c:
        progress("Initialisation de l'envoi…")
        init = _check(c.post(f"{API}/post/publish/video/init/", headers=auth, json={
            "post_info": {"title": caption[:2200], "privacy_level": level, "disable_duet": False,
                          "disable_comment": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size,
                            "total_chunk_count": count}}))["data"]
        publish_id, upload_url = init["publish_id"], init["upload_url"]
        with open(video, "rb") as f:
            for i in range(count):
                start = i * chunk_size
                end = size - 1 if i == count - 1 else start + chunk_size - 1
                f.seek(start)
                body = f.read(end - start + 1)
                progress(f"Envoi de la vidéo ({i + 1}/{count})…")
                r = c.put(upload_url, content=body, timeout=600, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {start}-{end}/{size}"})
                if r.status_code not in (200, 201, 206):
                    raise PublishError(f"Envoi de la vidéo à TikTok refusé (HTTP {r.status_code}).")
        progress("Traitement par TikTok…")
        t0 = time.time()
        while True:
            st = _check(c.post(f"{API}/post/publish/status/fetch/", headers=auth,
                               json={"publish_id": publish_id})).get("data") or {}
            status = st.get("status")
            if status == "PUBLISH_COMPLETE":
                ids = st.get("publicaly_available_post_id") or st.get("publicly_available_post_id") or []
                if ids and username:
                    return f"https://www.tiktok.com/@{username}/video/{ids[0]}"
                return f"https://www.tiktok.com/@{username}" if username else "https://www.tiktok.com/"
            if status == "FAILED":
                reason = st.get("fail_reason") or "inconnue"
                raise PublishError(f"TikTok a refusé la vidéo : {FAIL_REASONS.get(reason, reason)}")
            if time.time() - t0 > max_wait:
                raise PublishError("TikTok met trop de temps à traiter la vidéo.")
            time.sleep(poll_every)
