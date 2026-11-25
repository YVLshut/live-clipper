"""Jobs, sources et clips."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from .. import config, db
from ..errors import UserError
from ..events import bus
from ..jobs.clip_job import delete_clip_files, effective_config, normalize_section
from ..models import Clip, Job, Publication, Source
from ..services import job_queue
from .serializers import clip_out, job_out, source_out

router = APIRouter(prefix="/api")

URL_RE = re.compile(r"https?://[^\s,;\"'<>]+")
SUPPORTED = ("twitch.tv", "youtube.com", "youtu.be", "kick.com")


# ------------------------------------------------------------------ jobs
class JobOptions(BaseModel):
    max_clips: Optional[int] = None
    min_len: Optional[float] = None
    max_len: Optional[float] = None
    layout: Optional[str] = None
    section: Optional[str] = None


class JobCreate(BaseModel):
    urls: str | list[str]
    options: JobOptions = JobOptions()


def parse_urls(raw: str | list[str]) -> list[str]:
    text = raw if isinstance(raw, str) else "\n".join(raw)
    urls = list(dict.fromkeys(u.rstrip(").]") for u in URL_RE.findall(text)))
    # chemins de fichiers locaux (une ligne = un fichier)
    for line in text.splitlines():
        line = line.strip().strip('"')
        if line and not line.startswith("http") and Path(line).is_file():
            urls.append(line)
    return urls


@router.post("/jobs")
def create_jobs(body: JobCreate):
    urls = parse_urls(body.urls)
    if not urls:
        raise UserError("Aucun lien valide trouvé. Colle un ou plusieurs liens Twitch, YouTube ou Kick.")
    opts = body.options.model_dump(exclude_none=True)
    effective_config(opts)                     # valide les durées / options
    if "section" in opts:
        opts["section"] = normalize_section(opts["section"])
    unsupported = [u for u in urls if u.startswith("http") and not any(s in u for s in SUPPORTED)]
    jobs = [job_queue.submit("clip", url=u, options=opts) for u in urls]
    out = {"jobs": [job_out(j) for j in jobs]}
    if unsupported:
        out["warning"] = ("Plateforme non reconnue pour : " + ", ".join(unsupported)
                          + ". Le téléchargement sera tenté quand même.")
    return out


def _sources(ids) -> dict[str, Source]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    with db.session() as s:
        return {x.id: x for x in s.exec(select(Source).where(Source.id.in_(ids))).all()}


@router.get("/jobs")
def list_jobs(limit: int = 100):
    with db.session() as s:
        jobs = s.exec(select(Job).order_by(Job.id.desc()).limit(limit)).all()
    srcs = _sources(j.source_id for j in jobs)
    return [job_out(j, srcs.get(j.source_id)) for j in jobs]


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    j = job_queue.cancel(job_id)
    if j is None:
        raise UserError("Job introuvable.", status=404)
    return job_out(j)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int):
    with db.session() as s:
        j = s.get(Job, job_id)
    if j is None:
        raise UserError("Job introuvable.", status=404)
    if j.status not in ("failed", "cancelled"):
        raise UserError("Seuls les jobs en échec ou annulés peuvent être relancés.")
    nj = job_queue.submit(j.kind, url=j.url, options=j.options, clip_id=j.clip_id)
    return job_out(nj)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int):
    with db.session() as s:
        j = s.get(Job, job_id)
        if j is None:
            raise UserError("Job introuvable.", status=404)
        if j.status in ("running", "queued"):
            raise UserError("Annule d'abord ce job.")
        s.delete(j)
        s.commit()
    bus.publish("job.deleted", {"id": job_id})
    return {"ok": True}


@router.delete("/jobs")
def clear_finished_jobs():
    with db.session() as s:
        for j in s.exec(select(Job).where(Job.status.in_(["done", "failed", "cancelled"]))).all():
            s.delete(j)
        s.commit()
    bus.publish("jobs.cleared", {})
    return {"ok": True}


# ------------------------------------------------------------------ sources
@router.get("/sources")
def list_sources():
    with db.session() as s:
        rows = s.exec(select(Source).order_by(Source.created_at.desc())).all()
    return [source_out(r) for r in rows]


# ------------------------------------------------------------------ clips
def _clip_or_404(s, clip_id: str) -> Clip:
    c = s.get(Clip, clip_id)
    if c is None:
        raise UserError("Clip introuvable.", status=404)
    return c


def clips_payload(clips: list[Clip]) -> list[dict]:
    cfg = config.get_all()
    srcs = _sources(c.source_id for c in clips)
    ids = [c.id for c in clips]
    pubs: dict[str, list[Publication]] = {}
    if ids:
        with db.session() as s:
            for p in s.exec(select(Publication).where(Publication.clip_id.in_(ids))).all():
                pubs.setdefault(p.clip_id, []).append(p)
    return [clip_out(c, srcs.get(c.source_id), cfg, pubs.get(c.id)) for c in clips]


def clip_payload(clip_id: str) -> dict:
    with db.session() as s:
        c = _clip_or_404(s, clip_id)
    return clips_payload([c])[0]


@router.get("/clips")
def list_clips(status: Optional[str] = None, source_id: Optional[str] = None):
    q = select(Clip)
    if status:
        q = q.where(Clip.status.in_(status.split(",")))
    if source_id:
        q = q.where(Clip.source_id == source_id)
    with db.session() as s:
        clips = s.exec(q.order_by(Clip.created_at.desc(), Clip.start)).all()
    return clips_payload(clips)


@router.get("/clips/{clip_id}")
def get_clip(clip_id: str):
    return clip_payload(clip_id)


class ClipPatch(BaseModel):
    title: Optional[str] = None
    hook: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[list[str] | str] = None
    status: Optional[str] = None


@router.patch("/clips/{clip_id}")
def patch_clip(clip_id: str, body: ClipPatch):
    rerender = False
    with db.session() as s:
        c = _clip_or_404(s, clip_id)
        if body.title is not None:
            c.title = body.title.strip()
        if body.caption is not None:
            c.caption = body.caption.strip()
        if body.hashtags is not None:
            tags = body.hashtags.split() if isinstance(body.hashtags, str) else body.hashtags
            c.hashtags = [t if t.startswith("#") else f"#{t}" for t in (x.strip() for x in tags) if t]
        if body.status is not None:
            if body.status not in ("pending", "approved", "rejected"):
                raise UserError("Statut invalide.")
            c.status = body.status
        if body.hook is not None and body.hook.strip() != c.hook:
            if c.rendering:
                raise UserError("Ce clip est déjà en cours de remontage.")
            if len(body.hook.strip()) > 80:
                raise UserError("Accroche trop longue (80 caractères maximum).")
            c.hook, c.rendering, rerender = body.hook.strip(), True, True
        s.add(c)
        s.commit()
    if rerender:
        job_queue.submit("rerender", clip_id=clip_id, options={})
    out = clip_payload(clip_id)
    bus.publish("clip.updated", out)
    return out


@router.post("/clips/{clip_id}/approve")
def approve_clip(clip_id: str):
    return patch_clip(clip_id, ClipPatch(status="approved"))


@router.post("/clips/{clip_id}/reject")
def reject_clip(clip_id: str):
    out = patch_clip(clip_id, ClipPatch(status="rejected"))
    _cancel_pubs(clip_id, "Clip rejeté")
    return out


def _cancel_pubs(clip_id: str, reason: str) -> None:
    with db.session() as s:
        for p in s.exec(select(Publication).where(Publication.clip_id == clip_id,
                                                  Publication.status.in_(["scheduled", "paused"]))).all():
            p.status, p.error = "cancelled", reason
            s.add(p)
            bus.publish("publication.updated", p)
        s.commit()


@router.delete("/clips/{clip_id}")
def delete_clip(clip_id: str):
    with db.session() as s:
        c = _clip_or_404(s, clip_id)
        if c.rendering:
            raise UserError("Ce clip est en cours de montage : réessaie dans un instant.")
        running = s.exec(select(Publication).where(Publication.clip_id == clip_id,
                                                   Publication.status == "running")).first()
        if running:
            raise UserError("Ce clip est en cours de publication.")
        delete_clip_files(c)
        s.delete(c)
        s.commit()
    _cancel_pubs(clip_id, "Clip supprimé")
    bus.publish("clip.deleted", {"id": clip_id})
    return {"ok": True}


@router.get("/clips/{clip_id}/thumb")
def clip_thumb(clip_id: str):
    from ..pipeline.render import make_thumb
    with db.session() as s:
        c = _clip_or_404(s, clip_id)
    thumb = Path(c.file).parent / "thumb.jpg"
    if not thumb.exists() or thumb.stat().st_mtime < Path(c.file).stat().st_mtime:
        if not Path(c.file).exists() or make_thumb(Path(c.file), thumb, min(1.0, c.duration / 2)) is None:
            raise UserError("Miniature indisponible.", status=404)
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/clips/{clip_id}/video")
def clip_video(clip_id: str):
    with db.session() as s:
        c = _clip_or_404(s, clip_id)
    f = Path(c.file)
    if not f.exists():
        raise UserError("Fichier vidéo introuvable (supprimé ou déplacé).", status=404)
    return FileResponse(f, media_type="video/mp4", headers={"Cache-Control": "no-cache"})
