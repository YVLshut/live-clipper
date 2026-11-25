"""Conversion des tables en JSON pour le front."""
from __future__ import annotations

from .. import config
from ..events import to_jsonable
from ..models import Account, Clip, Job, Publication, Source
from ..pipeline.caption import build_caption, credit_line


def source_out(s: Source | None) -> dict | None:
    if s is None:
        return None
    d = to_jsonable(s)
    d.pop("work_dir", None)
    d["credit"] = credit_line(d)
    return d


def clip_out(c: Clip, source: Source | None, cfg: dict | None = None, pubs: list[Publication] | None = None) -> dict:
    cfg = cfg or config.get_all()
    d = to_jsonable(c)
    src = source_out(source) or {"author": "inconnu", "url": None}
    d["source"] = src
    d["final_caption"] = build_caption(d, src, cfg.get("default_hashtags") or [])
    d["video_url"] = f"/api/clips/{c.id}/video?v={c.version}"
    d["publications"] = [to_jsonable(p) for p in (pubs or [])]
    return d


def job_out(j: Job, source: Source | None = None) -> dict:
    d = to_jsonable(j)
    d["source"] = source_out(source)
    return d


def account_out(a: Account) -> dict:
    d = to_jsonable(a)
    extra = d.pop("extra", {}) or {}
    d["pending_choices"] = extra.get("pending_choices")
    d["avatar_url"] = (f"/api/accounts/{a.id}/avatar" if a.avatar and not a.avatar.startswith("http")
                       else a.avatar)
    return d


def publication_out(p: Publication, clip: Clip | None, account: Account | None) -> dict:
    d = to_jsonable(p)
    d["clip"] = ({"id": clip.id, "title": clip.title, "hook": clip.hook, "score": clip.score,
                  "video_url": f"/api/clips/{clip.id}/video?v={clip.version}"} if clip else None)
    d["account"] = ({"id": account.id, "name": account.name, "platform": account.platform,
                     "mode": account.mode, "avatar_url": account_out(account)["avatar_url"]} if account else None)
    d["screenshot_url"] = f"/api/publications/{p.id}/screenshot" if p.screenshot else None
    return d
