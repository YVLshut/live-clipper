"""Comptes Instagram / TikTok (API officielles ou mode navigateur) et retours OAuth."""
from __future__ import annotations

import html
import re
import webbrowser
from typing import Optional

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlmodel import select

from .. import db, paths
from ..errors import PublishError, UserError, humanize
from ..events import bus
from ..models import Account, Publication
from ..publish import accounts as acc_service
from ..services import publish_worker
from .serializers import account_out

router = APIRouter(prefix="/api")
oauth_router = APIRouter()

PRIVACY = ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"]
HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@router.get("/accounts")
def list_accounts():
    with db.session() as s:
        rows = s.exec(select(Account).order_by(Account.platform, Account.id)).all()
    return [account_out(a) for a in rows]


class AccountCreate(BaseModel):
    platform: str
    name: str
    mode: str = "api"


@router.post("/accounts")
def create_account(body: AccountCreate):
    if body.platform not in ("instagram", "tiktok"):
        raise UserError("Plateforme inconnue.")
    if body.mode not in ("api", "browser"):
        raise UserError("Mode de connexion inconnu.")
    if not body.name.strip():
        raise UserError("Donne un nom au compte.")
    a = Account(platform=body.platform, name=body.name.strip()[:60], mode=body.mode)
    with db.session() as s:
        s.add(a)
        s.commit()
        s.refresh(a)
    out = account_out(a)
    bus.publish("account.updated", out)
    return out


class AccountPatch(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    auto_publish: Optional[bool] = None
    require_approval: Optional[bool] = None
    min_score: Optional[float] = None
    max_per_day: Optional[int] = None
    time_windows: Optional[list[list[str]]] = None
    delay_min_minutes: Optional[int] = None
    delay_max_minutes: Optional[int] = None
    privacy_level: Optional[str] = None


@router.patch("/accounts/{account_id}")
def patch_account(account_id: int, body: AccountPatch):
    fields = body.model_dump(exclude_none=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()[:60] or acc_service.get_account(account_id).name
    if "mode" in fields:
        if fields["mode"] not in ("api", "browser"):
            raise UserError("Mode de connexion inconnu.")
        if fields["mode"] != acc_service.get_account(account_id).mode:
            fields.update(status="disconnected", status_message="Mode changé : connecte le compte.")
    if "min_score" in fields and not 0 <= fields["min_score"] <= 10:
        raise UserError("Le score minimal doit être compris entre 0 et 10.")
    if "max_per_day" in fields and not 1 <= fields["max_per_day"] <= 50:
        raise UserError("Nombre de posts par jour : entre 1 et 50.")
    if "time_windows" in fields:
        for w in fields["time_windows"]:
            if len(w) != 2 or not all(HM.match(x) for x in w) or w[0] >= w[1]:
                raise UserError("Plage horaire invalide : utilise HH:MM et un début avant la fin (ex : 18:00 → 23:00).")
    if "delay_min_minutes" in fields or "delay_max_minutes" in fields:
        a = acc_service.get_account(account_id)
        lo = fields.get("delay_min_minutes", a.delay_min_minutes)
        hi = fields.get("delay_max_minutes", a.delay_max_minutes)
        if lo < 0 or hi < lo or hi > 24 * 60:
            raise UserError("Délai entre deux posts invalide (min ≤ max ≤ 1440 minutes).")
    if "privacy_level" in fields and fields["privacy_level"] not in PRIVACY:
        raise UserError("Visibilité inconnue.")
    a = acc_service.update_account(account_id, **fields)
    return account_out(a)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int):
    with db.session() as s:
        a = s.get(Account, account_id)
        if a is None:
            raise UserError("Compte introuvable.", status=404)
        for p in s.exec(select(Publication).where(Publication.account_id == account_id,
                                                  Publication.status.in_(["scheduled", "paused"]))).all():
            p.status, p.error = "cancelled", "Compte supprimé"
            s.add(p)
        s.delete(a)
        s.commit()
    publish_worker.enqueue_close(account_id)
    acc_service.delete_account_data(account_id)
    bus.publish("account.deleted", {"id": account_id})
    bus.publish("publication.updated", {})
    return {"ok": True}


@router.post("/accounts/{account_id}/avatar")
async def upload_avatar(account_id: int, file: UploadFile = File(...)):
    acc_service.get_account(account_id)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        raise UserError("Format d'image non pris en charge (PNG, JPG, WEBP ou GIF).")
    data = await file.read()
    if len(data) > 5_000_000:
        raise UserError("Image trop lourde (5 Mo maximum).")
    for old in paths.avatars_dir().glob(f"{account_id}.*"):
        old.unlink(missing_ok=True)
    dest = paths.avatars_dir() / f"{account_id}.{ext}"
    dest.write_bytes(data)
    return account_out(acc_service.update_account(account_id, avatar=str(dest)))


@router.get("/accounts/{account_id}/avatar")
def get_avatar(account_id: int):
    a = acc_service.get_account(account_id)
    if not a.avatar or a.avatar.startswith("http"):
        raise UserError("Pas d'avatar local.", status=404)
    return FileResponse(a.avatar)


@router.post("/accounts/{account_id}/connect")
def connect_account(account_id: int):
    """API : ouvre la page d'autorisation officielle dans le navigateur du système.
    Navigateur : ouvre une fenêtre avec le profil dédié du compte pour se connecter soi-même."""
    a = acc_service.get_account(account_id)
    if a.mode == "api":
        url = acc_service.start_oauth(account_id)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        acc_service.update_account(account_id, status_message="Autorisation en cours dans ton navigateur…")
        return {"mode": "api", "auth_url": url}
    publish_worker.enqueue_login(account_id)
    return {"mode": "browser"}


@router.post("/accounts/{account_id}/login-done")
def login_done(account_id: int):
    publish_worker.finish_login(account_id)
    return {"ok": True}


@router.post("/accounts/{account_id}/check")
def check_account(account_id: int):
    acc_service.get_account(account_id)
    publish_worker.enqueue_check(account_id)
    return {"ok": True}


class ChooseBody(BaseModel):
    external_id: str


@router.post("/accounts/{account_id}/choose")
def choose(account_id: int, body: ChooseBody):
    return account_out(acc_service.choose_instagram(account_id, body.external_id))


class PasteBody(BaseModel):
    url: str


@router.post("/accounts/{account_id}/oauth-code")
def paste_code(account_id: int, body: PasteBody):
    """Secours si l'URL de redirection locale n'est pas acceptée : l'utilisateur colle l'adresse de retour."""
    a = acc_service.get_account(account_id)
    code, state = acc_service.parse_pasted(body.url)
    try:
        acc = acc_service.complete_oauth(a.platform, code, state, account_id=account_id)
    except PublishError as e:
        raise UserError(e.message)
    return account_out(acc)


# ------------------------------------------------------------------ retours OAuth (navigateur du système)
PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Live Clipper</title>
<style>body{{background:#0b0d12;color:#e4e7ee;font-family:'Segoe UI',system-ui,sans-serif;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0}}.c{{max-width:520px;text-align:center;
padding:40px;border:1px solid #272e3d;border-radius:18px;background:#0f1218}}h1{{font-size:22px;margin:0 0 10px}}
p{{color:#b9bfcd;line-height:1.5}}.i{{font-size:44px}}</style></head><body><div class="c"><div class="i">{icon}</div>
<h1>{title}</h1><p>{text}</p></div></body></html>"""


def _page(ok: bool, title: str, text: str) -> HTMLResponse:
    return HTMLResponse(PAGE.format(icon="✅" if ok else "⚠️", title=html.escape(title), text=html.escape(text)),
                        status_code=200 if ok else 400)


def _callback(platform: str, code: str | None, state: str | None, error: str | None,
              error_description: str | None) -> HTMLResponse:
    if error or not code:
        return _page(False, "Connexion refusée", error_description or error or "Aucun code reçu.")
    try:
        acc = acc_service.complete_oauth(platform, code, state)
    except (UserError, PublishError) as e:
        bus.notify(e.message, "error")
        return _page(False, "Connexion impossible", e.message)
    except Exception as e:  # pragma: no cover
        msg = humanize(e)
        bus.notify(msg, "error")
        return _page(False, "Connexion impossible", msg)
    if acc.status == "connected":
        bus.notify(f"Compte « {acc.name} » connecté ({acc.username or platform}).", "success")
        return _page(True, "Compte connecté !", "Tu peux fermer cet onglet et revenir dans Live Clipper.")
    bus.notify(acc.status_message or "Termine la connexion dans Live Clipper.", "info")
    return _page(True, "Presque fini", "Reviens dans Live Clipper pour choisir le compte Instagram à utiliser.")


@oauth_router.get("/oauth/instagram/callback")
def instagram_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None,
                       error_description: Optional[str] = None):
    return _callback("instagram", code, state, error, error_description)


@oauth_router.get("/oauth/tiktok/callback")
def tiktok_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None,
                    error_description: Optional[str] = None):
    return _callback("tiktok", code, state, error, error_description)
