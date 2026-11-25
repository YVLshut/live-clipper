"""File de publication et historique."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from .. import db
from ..errors import UserError
from ..events import bus
from ..models import Account, Clip, Publication, now
from ..services import publish_worker
from .serializers import publication_out

router = APIRouter(prefix="/api")


@router.get("/publications")
def list_publications(account_id: Optional[int] = None, status: Optional[str] = None, limit: int = 500):
    q = select(Publication)
    if account_id:
        q = q.where(Publication.account_id == account_id)
    if status:
        q = q.where(Publication.status.in_(status.split(",")))
    with db.session() as s:
        pubs = s.exec(q.order_by(Publication.scheduled_at.desc()).limit(limit)).all()
        clips = {c.id: c for c in s.exec(select(Clip).where(Clip.id.in_({p.clip_id for p in pubs}))).all()}
        accs = {a.id: a for a in s.exec(select(Account)).all()}
    return [publication_out(p, clips.get(p.clip_id), accs.get(p.account_id)) for p in pubs]


class PubCreate(BaseModel):
    clip_id: str
    account_ids: list[int]
    scheduled_at: Optional[datetime] = None    # None = dès que possible
    caption: Optional[str] = None


@router.post("/publications")
def create_publications(body: PubCreate):
    if not body.account_ids:
        raise UserError("Choisis au moins un compte.")
    when = body.scheduled_at or now()
    if when.tzinfo is None:
        when = when.astimezone()  # heure locale du PC
    when = when.astimezone(timezone.utc)
    created = []
    with db.session() as s:
        clip = s.get(Clip, body.clip_id)
        if clip is None:
            raise UserError("Clip introuvable.", status=404)
        if clip.status != "approved":
            raise UserError("Approuve d'abord ce clip avant de le publier.")
        for aid in body.account_ids:
            acc = s.get(Account, aid)
            if acc is None:
                raise UserError("Compte introuvable.", status=404)
            dup = s.exec(select(Publication).where(
                Publication.clip_id == clip.id, Publication.account_id == aid,
                Publication.status.in_(["scheduled", "running", "published", "paused"]))).first()
            if dup:
                raise UserError(f"Ce clip est déjà programmé ou publié sur « {acc.name} ».")
            p = Publication(clip_id=clip.id, account_id=aid, scheduled_at=when,
                            caption=(body.caption or None))
            s.add(p)
            created.append(p)
        s.commit()
        for p in created:
            s.refresh(p)
    for p in created:
        bus.publish("publication.updated", p)
    return {"created": len(created)}


def _pub_or_404(s, pub_id: int) -> Publication:
    p = s.get(Publication, pub_id)
    if p is None:
        raise UserError("Publication introuvable.", status=404)
    return p


class PubPatch(BaseModel):
    scheduled_at: Optional[datetime] = None
    caption: Optional[str] = None


@router.patch("/publications/{pub_id}")
def patch_publication(pub_id: int, body: PubPatch):
    with db.session() as s:
        p = _pub_or_404(s, pub_id)
        if p.status not in ("scheduled", "failed", "paused"):
            raise UserError("Cette publication ne peut plus être modifiée.")
        if body.scheduled_at:
            when = body.scheduled_at if body.scheduled_at.tzinfo else body.scheduled_at.astimezone()
            p.scheduled_at = when.astimezone(timezone.utc)
        if body.caption is not None:
            p.caption = body.caption or None
        s.add(p)
        s.commit()
        s.refresh(p)
    bus.publish("publication.updated", p)
    return {"ok": True}


@router.post("/publications/{pub_id}/retry")
def retry_publication(pub_id: int):
    """Réessayer (échec) ou Reprendre (pause après vérification) : relance tout de suite."""
    with db.session() as s:
        p = _pub_or_404(s, pub_id)
        if p.status not in ("failed", "paused", "cancelled"):
            raise UserError("Seules les publications en échec, en pause ou annulées peuvent être relancées.")
        resumed = p.status == "paused"
        p.status, p.error, p.scheduled_at = "scheduled", None, now()
        s.add(p)
        s.commit()
        s.refresh(p)
    bus.publish("publication.updated", p)
    with db.session() as s:
        acc = s.get(Account, p.account_id)
    if acc and (acc.status == "connected" or resumed):
        publish_worker.enqueue_publication(pub_id)
    return {"ok": True}


@router.post("/publications/{pub_id}/publish-now")
def publish_now(pub_id: int):
    with db.session() as s:
        p = _pub_or_404(s, pub_id)
        if p.status != "scheduled":
            raise UserError("Cette publication n'est pas en attente.")
        p.scheduled_at = now()
        s.add(p)
        s.commit()
    publish_worker.enqueue_publication(pub_id)
    return {"ok": True}


@router.post("/publications/{pub_id}/cancel")
def cancel_publication(pub_id: int):
    with db.session() as s:
        p = _pub_or_404(s, pub_id)
        if p.status not in ("scheduled", "paused", "failed"):
            raise UserError("Cette publication ne peut pas être annulée.")
        was_paused = p.status == "paused"
        p.status, p.error = "cancelled", "Annulée"
        s.add(p)
        s.commit()
        s.refresh(p)
    if was_paused:
        publish_worker.enqueue_close(p.account_id)
    bus.publish("publication.updated", p)
    return {"ok": True}


@router.delete("/publications/{pub_id}")
def delete_publication(pub_id: int):
    with db.session() as s:
        p = _pub_or_404(s, pub_id)
        if p.status == "running":
            raise UserError("Publication en cours : attends la fin.")
        s.delete(p)
        s.commit()
    bus.publish("publication.updated", {"id": pub_id, "deleted": True})
    return {"ok": True}


@router.get("/publications/{pub_id}/screenshot")
def screenshot(pub_id: int):
    with db.session() as s:
        p = _pub_or_404(s, pub_id)
    if not p.screenshot or not Path(p.screenshot).exists():
        raise UserError("Aucune capture d'écran.", status=404)
    return FileResponse(p.screenshot, media_type="image/png")
