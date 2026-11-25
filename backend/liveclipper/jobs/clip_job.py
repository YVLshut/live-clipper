"""Job « clip » : téléchargement → transcription → repérage IA → montage."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from .. import config, db, paths, secrets
from ..errors import UserError
from ..events import bus
from ..models import Clip, Source
from ..pipeline import download, highlights, peaks, render, transcribe
from ..pipeline.utils import check, duration, hms
from .queue import JobContext

log = logging.getLogger("liveclipper.jobs")

OPTION_KEYS = ("max_clips", "min_len", "max_len", "layout")


def effective_config(options: dict) -> dict:
    cfg = config.get_all()
    for k in OPTION_KEYS:
        if options.get(k) not in (None, ""):
            cfg[k] = options[k]
    cfg["max_clips"] = max(1, min(30, int(cfg["max_clips"])))
    cfg["min_len"], cfg["max_len"] = float(cfg["min_len"]), float(cfg["max_len"])
    if cfg["min_len"] < 3 or cfg["max_len"] > 180 or cfg["min_len"] >= cfg["max_len"]:
        raise UserError("Durées invalides : il faut 3 s ≤ durée min < durée max ≤ 180 s.")
    if cfg["layout"] not in config.LAYOUTS:
        cfg["layout"] = "blur"
    return cfg


def normalize_section(section: str | None) -> str | None:
    """« 1:00:00-1:30:00 » -> « 01:00:00-01:30:00 » (vérifié)."""
    if not section or not str(section).strip():
        return None
    from ..pipeline.utils import to_sec
    try:
        a, b = [x.strip() for x in str(section).split("-", 1)]
        sa, sb = to_sec(a), to_sec(b)
    except (ValueError, TypeError):
        raise UserError("Passage invalide : utilise le format HH:MM:SS-HH:MM:SS (ex : 01:00:00-01:30:00).")
    if sb <= sa:
        raise UserError("Passage invalide : la fin doit être après le début.")
    return f"{hms(sa)}-{hms(sb)}"


def save_source(src: dict, d: Path, total: float) -> Source:
    fields = {k: src.get(k) for k in ("url", "author", "author_url", "title", "platform", "date", "was_live")}
    with db.session() as s:
        row = s.get(Source, src["id"])
        if row is None:
            row = Source(id=src["id"], **fields)
        else:
            for k, v in fields.items():
                setattr(row, k, v)
        row.work_dir, row.duration = str(d), total
        s.add(row)
        s.commit()
        s.refresh(row)
    bus.publish("source.updated", row)
    return row


def run(ctx: JobContext) -> None:
    job = ctx.job()
    opts = job.options or {}
    cfg = effective_config(opts)
    section = normalize_section(opts.get("section"))

    # 1. Téléchargement
    ctx.step("download", 0, "Téléchargement…")
    d, src = download.download(job.url, paths.work_dir(), section,
                               progress=ctx.progress_for("download"), cancel=ctx.cancelled)
    total = duration(d / "video.mp4")
    if total <= 0:
        raise UserError("La vidéo téléchargée est vide ou illisible.")
    source = save_source(src, d, total)
    ctx.update(source_id=source.id)

    # 2. Transcription
    ctx.step("transcribe", 0, "Transcription…")
    segs = transcribe.transcribe(d, cfg, progress=ctx.progress_for("transcribe"), cancel=ctx.cancelled)
    check(ctx.cancelled)
    if not segs:
        ctx.warn("Aucune parole détectée dans la vidéo : les clips n'auront pas de sous-titres.")

    # 3. Repérage
    ctx.step("detect", 0, "Repérage des moments forts…")
    pk = peaks.loudness_peaks(d)
    hl, warns = highlights.find_highlights(segs, pk, src, cfg["max_clips"], total, cfg,
                                           secrets.get(secrets.ANTHROPIC_KEY),
                                           progress=ctx.progress_for("detect"), cancel=ctx.cancelled)
    for w in warns:
        ctx.warn(w)
    (d / f"highlights_{job.id}.json").write_text(json.dumps(hl, ensure_ascii=False, indent=2), encoding="utf-8")
    if not hl:
        raise UserError("Aucun moment fort trouvé dans cette vidéo.")

    # 4. Montage
    out_root = config.clips_dir(cfg)
    created = 0
    for i, h in enumerate(hl):
        check(ctx.cancelled)
        ctx.step("render", i / len(hl), f"Montage {i + 1}/{len(hl)} : {hms(h['start'])} → {hms(h['end'])}")
        cid = f"{source.id}_{int(h['start']):06d}"
        with db.session() as s:
            if s.get(Clip, cid) is not None:
                log.info("Clip %s déjà présent : ignoré", cid)
                continue
        out = render.render_clip(d / "video.mp4", segs, h["start"], h["end"], h.get("hook", ""),
                                 cfg["layout"], out_root / cid, cfg, cancel=ctx.cancelled)
        clip = Clip(id=cid, source_id=source.id, job_id=job.id, file=str(out), start=h["start"], end=h["end"],
                    duration=round(h["end"] - h["start"], 1), score=_score(h.get("score")),
                    title=h.get("title", ""), hook=h.get("hook", ""), caption=h.get("caption", ""),
                    hashtags=[t for t in (h.get("hashtags") or []) if isinstance(t, str)], layout=cfg["layout"])
        with db.session() as s:
            s.add(clip)
            s.commit()
            s.refresh(clip)
        created += 1
        bus.publish("clip.created", clip)
    ctx.update(clips_count=created, message=f"{created} clip(s) créé(s)")
    bus.notify(f"{created} clip(s) prêt(s) pour « {source.title or source.author} »", "success", job_id=job.id)


def _score(v) -> float | None:
    try:
        return round(max(0.0, min(10.0, float(v))), 1)
    except (TypeError, ValueError):
        return None


def rerender(ctx: JobContext) -> None:
    """Remonte un seul clip (accroche modifiée) en réutilisant la transcription en cache."""
    job = ctx.job()
    with db.session() as s:
        clip = s.get(Clip, job.clip_id)
        source = s.get(Source, clip.source_id) if clip else None
    if clip is None or source is None:
        raise UserError("Clip introuvable.")
    d = Path(source.work_dir or "")
    if not (d / "video.mp4").exists() or not (d / "transcript.json").exists():
        raise UserError("Les fichiers de travail de ce live ont été supprimés : impossible de remonter le clip.")
    ctx.update(source_id=source.id, message=f"Remontage de {clip.id}…")
    ctx.step("render", 0.1, "Remontage du clip…")
    cfg = config.get_all()
    segs = json.loads((d / "transcript.json").read_text(encoding="utf-8"))
    out = render.render_clip(d / "video.mp4", segs, clip.start, clip.end, clip.hook, clip.layout,
                             Path(clip.file).parent, cfg, cancel=ctx.cancelled)
    with db.session() as s:
        c = s.get(Clip, clip.id)
        c.file, c.rendering, c.version = str(out), False, c.version + 1
        s.add(c)
        s.commit()
        s.refresh(c)
    bus.publish("clip.updated", c)
    ctx.update(message="Clip remonté")


def on_rerender_failed(clip_id: str) -> None:
    with db.session() as s:
        c = s.get(Clip, clip_id)
        if c and c.rendering:
            c.rendering = False
            s.add(c)
            s.commit()
            bus.publish("clip.updated", c)


def delete_clip_files(clip: Clip) -> None:
    folder = Path(clip.file).parent
    try:
        if folder.is_dir() and folder.name == clip.id:
            shutil.rmtree(folder, ignore_errors=True)
        elif Path(clip.file).exists():
            Path(clip.file).unlink()
    except OSError as e:
        log.warning("Suppression des fichiers de %s impossible : %s", clip.id, e)
