"""Comptes : OAuth (démarrage / retour), jetons dans keyring, rafraîchissement automatique."""
from __future__ import annotations

import logging
import secrets as pysecrets
import shutil
import threading
import time
from urllib.parse import parse_qs, urlparse

from .. import config, db, paths, secrets
from ..errors import PublishError, UserError
from ..events import bus
from ..models import Account
from . import instagram_api, tiktok_api

log = logging.getLogger("liveclipper.accounts")

_pending: dict[str, dict] = {}       # state OAuth -> {account_id, platform, verifier, t}
_lock = threading.Lock()


# ------------------------------------------------------------------ helpers
def get_account(account_id: int) -> Account:
    with db.session() as s:
        a = s.get(Account, account_id)
    if a is None:
        raise UserError("Compte introuvable.", status=404)
    return a


def update_account(account_id: int, **fields) -> Account:
    with db.session() as s:
        a = s.get(Account, account_id)
        if a is None:
            raise UserError("Compte introuvable.", status=404)
        for k, v in fields.items():
            setattr(a, k, v)
        s.add(a)
        s.commit()
        s.refresh(a)
    from ..api.serializers import account_out
    bus.publish("account.updated", account_out(a))
    return a


def mark_reconnect(account_id: int, message: str) -> None:
    a = update_account(account_id, status="reconnect", status_message=message)
    bus.notify(f"Le compte « {a.name} » doit être reconnecté : {message}", "warning", account_id=account_id)


def redirect_uri(platform: str) -> str:
    return f"http://localhost:{config.get('oauth_port')}/oauth/{platform}/callback"


def app_credentials(platform: str) -> tuple[str, str]:
    cfg = config.get_all()
    if platform == "instagram":
        key, sec = cfg.get("meta_app_id"), secrets.get(secrets.META_APP_SECRET)
        name = "Meta (ID de l'app et clé secrète)"
    else:
        key, sec = cfg.get("tiktok_client_key"), secrets.get(secrets.TIKTOK_CLIENT_SECRET)
        name = "TikTok (client key et client secret)"
    if not key or not sec:
        raise UserError(f"Renseigne d'abord les identifiants de ton app {name} dans les Paramètres.",
                        code="missing_app")
    return key, sec


def save_tokens(account_id: int, tokens: dict | None) -> None:
    secrets.set_json(secrets.account_tokens_key(account_id), tokens)


def load_tokens(account_id: int) -> dict | None:
    return secrets.get_json(secrets.account_tokens_key(account_id))


# ------------------------------------------------------------------ OAuth
def start_oauth(account_id: int) -> str:
    a = get_account(account_id)
    key, _sec = app_credentials(a.platform)
    state = pysecrets.token_urlsafe(24)
    entry = {"account_id": account_id, "platform": a.platform, "t": time.time()}
    if a.platform == "instagram":
        url = instagram_api.auth_url(key, redirect_uri("instagram"), state)
    else:
        verifier, challenge = tiktok_api.new_pkce()
        entry["verifier"] = verifier
        url = tiktok_api.auth_url(key, redirect_uri("tiktok"), state, challenge)
    with _lock:
        for k in [k for k, v in _pending.items() if time.time() - v["t"] > 1800]:
            _pending.pop(k, None)
        _pending[state] = entry
    return url


def _pop_state(state: str | None, account_id: int | None = None) -> dict:
    with _lock:
        if state and state in _pending:
            return _pending.pop(state)
        if account_id is not None:   # code collé à la main sans state : dernière demande du compte
            for k, v in sorted(_pending.items(), key=lambda kv: -kv[1]["t"]):
                if v["account_id"] == account_id:
                    return _pending.pop(k)
    raise UserError("Demande de connexion expirée ou inconnue : recommence la connexion.")


def complete_oauth(platform: str, code: str, state: str | None, account_id: int | None = None) -> Account:
    entry = _pop_state(state, account_id)
    if entry["platform"] != platform:
        raise UserError("Réponse de connexion incohérente.")
    aid = entry["account_id"]
    key, sec = app_credentials(platform)
    if platform == "instagram":
        tokens = instagram_api.exchange_code(key, sec, redirect_uri("instagram"), code)
        igs = instagram_api.list_accounts(tokens["access_token"])
        save_tokens(aid, tokens)
        if not igs:
            update_account(aid, status="reconnect",
                           status_message="Aucun compte Instagram professionnel relié à une Page Facebook.")
            raise UserError("Aucun compte Instagram professionnel n'est relié à tes Pages Facebook. "
                            "Passe ton compte en mode professionnel et relie-le à une Page.")
        if len(igs) == 1:
            return link_instagram(aid, igs[0])
        acc = get_account(aid)
        return update_account(aid, status="reconnect", status_message="Choisis le compte Instagram à utiliser.",
                              extra={**(acc.extra or {}), "pending_choices": igs})
    tokens = tiktok_api.exchange_code(key, sec, redirect_uri("tiktok"), code, entry.get("verifier", ""))
    save_tokens(aid, tokens)
    try:
        user = tiktok_api.user_info(tokens["access_token"])
    except PublishError:
        user = {}
    acc = get_account(aid)
    return update_account(aid, status="connected", status_message=None, external_id=tokens.get("open_id"),
                          username=user.get("username") or user.get("display_name"),
                          avatar=acc.avatar or user.get("avatar_url"))


def link_instagram(account_id: int, ig: dict) -> Account:
    acc = get_account(account_id)
    extra = {k: v for k, v in (acc.extra or {}).items() if k != "pending_choices"}
    extra["page"] = ig.get("page")
    return update_account(account_id, status="connected", status_message=None, external_id=ig["id"],
                          username=ig.get("username"), avatar=acc.avatar or ig.get("picture"), extra=extra)


def choose_instagram(account_id: int, ig_id: str) -> Account:
    acc = get_account(account_id)
    for ig in (acc.extra or {}).get("pending_choices") or []:
        if ig["id"] == ig_id:
            return link_instagram(account_id, ig)
    raise UserError("Compte Instagram inconnu.")


def parse_pasted(text: str) -> tuple[str, str | None]:
    """Accepte l'URL complète de la page de retour, ou le code seul."""
    text = text.strip()
    if text.startswith("http"):
        q = parse_qs(urlparse(text).query)
        if "error" in q:
            raise UserError("Connexion refusée : " + (q.get("error_description") or q["error"])[0])
        if "code" not in q:
            raise UserError("Cette adresse ne contient pas de code d'autorisation.")
        return q["code"][0], (q.get("state") or [None])[0]
    if not text:
        raise UserError("Colle l'adresse de la page de retour.")
    return text, None


# ------------------------------------------------------------------ jetons valides
def valid_token(account: Account) -> str:
    """Jeton d'accès valide (rafraîchi si nécessaire). Lève PublishError(reconnect) sinon."""
    tokens = load_tokens(account.id)
    if not tokens or not tokens.get("access_token"):
        raise PublishError("Compte non connecté : clique sur « Se connecter ».", reconnect=True)
    mod = instagram_api if account.platform == "instagram" else tiktok_api
    if mod.needs_refresh(tokens):
        try:
            key, sec = app_credentials(account.platform)
        except UserError as e:
            raise PublishError(e.message) from e
        tokens = mod.refresh(tokens, key, sec)
        save_tokens(account.id, tokens)
        log.info("Jeton rafraîchi pour le compte %s", account.id)
    return tokens["access_token"]


def refresh_all() -> None:
    """Appelé périodiquement : garde les jetons en vie, signale les comptes à reconnecter."""
    from sqlmodel import select
    with db.session() as s:
        accounts = s.exec(select(Account).where(Account.mode == "api", Account.status == "connected")).all()
    for a in accounts:
        try:
            valid_token(a)
        except PublishError as e:
            if e.reconnect:
                mark_reconnect(a.id, e.message)
            else:
                log.warning("Rafraîchissement du compte %s : %s", a.id, e.message)
        except Exception as e:  # réseau...
            log.warning("Rafraîchissement du compte %s impossible : %s", a.id, e)


def delete_account_data(account_id: int) -> None:
    save_tokens(account_id, None)
    prof = paths.profiles_dir() / str(account_id)
    if prof.exists():
        shutil.rmtree(prof, ignore_errors=True)
    for f in paths.avatars_dir().glob(f"{account_id}.*"):
        f.unlink(missing_ok=True)
