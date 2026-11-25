"""Liste « Mes lives » (onglet Lives) : un œil par live pour activer / couper le clipping.

- œil ouvert : le live est clippé. Une CHAÎNE (twitch.tv/pseudo, kick.com/pseudo, youtube.com/@x/live) est
  surveillée : dès qu'elle passe en direct, l'enregistrement par tranches démarre tout seul.
- œil barré : plus aucun clip sur ce live (enregistrement arrêté, tranches en attente annulées).
"""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlmodel import select

from .. import db
from ..events import bus
from ..models import Job, Stream, now
from .queue import JobQueue

log = logging.getLogger("liveclipper.streams")

ACTIVE = ("queued", "running")
CHECK_EVERY = timedelta(minutes=5)

_CHANNEL_PATTERNS = [
    r"^https?://(www\.|m\.)?twitch\.tv/(?!videos/)(?!directory)[A-Za-z0-9_]+/?$",
    r"^https?://(www\.)?kick\.com/(?!video/)[A-Za-z0-9_-]+/?$",
    r"^https?://(www\.)?youtube\.com/(@[^/]+|channel/[^/]+|c/[^/]+)(/live|/streams)?/?$",
]


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("http"):
        url = re.sub(r"[?#].*$", "", url) if "youtube.com/watch" not in url else url
        url = url.rstrip("/")
    return url


def is_channel_url(url: str) -> bool:
    """Lien d'une chaîne (peut passer en direct plusieurs fois) plutôt que d'une vidéo précise."""
    return any(re.match(p, url, re.I) for p in _CHANNEL_PATTERNS)


def update_stream_meta(stream_id: int | None, src: dict, live: bool = False) -> None:
    if not stream_id:
        return
    with db.session() as s:
        st = s.get(Stream, stream_id)
        if st is None:
            return
        st.author = src.get("author") or st.author
        st.title = src.get("title") or st.title
        st.platform = src.get("platform") or st.platform
        if live:
            st.last_live_at = now()
        s.add(st)
        s.commit()
    bus.publish("stream.updated", {"id": stream_id})


def stream_enabled(stream_id: int | None) -> bool:
    """Vrai si le live n'est pas dans la liste, ou si son œil est ouvert."""
    if not stream_id:
        return True
    with db.session() as s:
        st = s.get(Stream, stream_id)
    return st is None or bool(st.enabled)


def active_jobs(stream_id: int) -> list[Job]:
    with db.session() as s:
        return s.exec(select(Job).where(Job.stream_id == stream_id, Job.status.in_(ACTIVE))).all()


def stream_status(st: Stream) -> dict:
    """État affiché dans la liste, calculé à partir des jobs du live."""
    with db.session() as s:
        jobs = s.exec(select(Job).where(Job.stream_id == st.id)).all()
    clips = sum(j.clips_count or 0 for j in jobs if j.kind == "clip")
    live_running = any(j.kind == "live" and j.status == "running" for j in jobs)
    processing = any(j.kind == "clip" and j.status in ACTIVE for j in jobs)
    channel = is_channel_url(st.url)
    last = max(jobs, key=lambda j: j.id) if jobs else None
    current = next((j for j in sorted(jobs, key=lambda j: j.id) if j.kind == "clip" and j.status == "running"), None)
    queued = sum(1 for j in jobs if j.kind == "clip" and j.status == "queued")
    if not st.enabled:
        state, label = "paused", "Clipping coupé"
    elif live_running:
        state, label = "live", "En direct : enregistrement en cours"
    elif processing:
        state, label = "processing", "Clipping en cours"
    elif channel:
        state, label = "watching", "Hors ligne : surveillance (vérifié toutes les 5 min)"
    elif last and last.status == "failed":
        state, label = "failed", last.error or "Échec"
    else:
        state, label = "done", "Clippé"
    if st.enabled and current is not None:
        seg = (current.options or {}).get("segment")
        prefix = f"Tranche {seg + 1} : " if seg is not None else ""
        detail = f"{prefix}{current.message or 'Traitement'}"
        label = f"{label} · {detail}" if state == "live" else detail
    elif st.enabled and queued and state in ("live", "processing"):
        label = f"{label} · {queued} tranche(s) en attente" if state == "live" else f"{queued} traitement(s) en attente"
    return {"state": state, "label": label, "clips": clips, "channel": channel,
            "progress": round(current.progress, 3) if (st.enabled and current) else None,
            "recorded": sum(float((j.extra or {}).get("recorded", 0)) for j in jobs if j.kind == "live")}


def start_clipping(stream: Stream, queue: JobQueue) -> Job | None:
    """Lance le clipping de ce live s'il n'y a pas déjà un traitement en cours."""
    if any(j.kind in ("live", "clip") and not (j.options or {}).get("live_source") for j in active_jobs(stream.id)):
        return None
    return queue.submit("clip", url=stream.url, options=dict(stream.options or {}), stream_id=stream.id)


def add_streams(urls: list[str], options: dict, queue: JobQueue) -> tuple[list[Stream], list[Job]]:
    streams, jobs = [], []
    for raw in urls:
        url = normalize_url(raw)
        with db.session() as s:
            st = s.exec(select(Stream).where(Stream.url == url)).first()
            if st is None:
                st = Stream(url=url, options=options)
            else:
                st.enabled, st.options = True, options or st.options
            s.add(st)
            s.commit()
            s.refresh(st)
        streams.append(st)
        j = start_clipping(st, queue)
        if j:
            jobs.append(j)
        bus.publish("stream.updated", {"id": st.id})
    return streams, jobs


def set_enabled(stream_id: int, enabled: bool, queue: JobQueue) -> Stream:
    with db.session() as s:
        st = s.get(Stream, stream_id)
        if st is None:
            from ..errors import UserError
            raise UserError("Live introuvable.", status=404)
        st.enabled = enabled
        s.add(st)
        s.commit()
        s.refresh(st)
    if enabled:
        status = stream_status(st)
        if status["channel"] or status["state"] in ("failed",) or not status["clips"]:
            start_clipping(st, queue)
        bus.notify(f"👁 Clipping réactivé pour « {st.author or st.url} ».", "success")
    else:
        stop_clipping(stream_id, queue)
        bus.notify(f"Clipping coupé pour « {st.author or st.url} » : plus aucun clip sur ce live.", "info")
    bus.publish("stream.updated", {"id": stream_id})
    return st


def stop_clipping(stream_id: int, queue: JobQueue) -> None:
    """Arrête l'enregistrement et annule les tranches en attente ou en cours de ce live."""
    for j in active_jobs(stream_id):
        queue.cancel(j.id)


def delete_stream(stream_id: int, queue: JobQueue) -> None:
    stop_clipping(stream_id, queue)
    with db.session() as s:
        st = s.get(Stream, stream_id)
        if st is not None:
            s.delete(st)
            s.commit()
    bus.publish("stream.deleted", {"id": stream_id})


class StreamWatcher:
    """Vérifie régulièrement si les chaînes surveillées (œil ouvert) sont passées en direct."""

    def __init__(self, queue: JobQueue):
        self.queue = queue
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.interval = 60.0
        self.is_live: Callable[[str], bool] = self._probe_is_live

    @staticmethod
    def _probe_is_live(url: str) -> bool:
        from ..pipeline import download
        try:
            return bool(download.probe(url).get("is_live"))
        except (subprocess.CalledProcessError, ValueError, OSError):
            return False   # hors ligne (yt-dlp : « not currently live ») ou réseau indisponible

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="stream-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def tick(self, current: datetime | None = None) -> list[Job]:
        current = current or datetime.now(timezone.utc)
        started: list[Job] = []
        with db.session() as s:
            streams = s.exec(select(Stream).where(Stream.enabled == True)).all()  # noqa: E712
        for st in streams:
            if not is_channel_url(st.url) or active_jobs(st.id):
                continue
            last = st.last_checked.astimezone(timezone.utc) if st.last_checked else None
            if last and current - last < CHECK_EVERY:
                continue
            live = self.is_live(st.url)
            with db.session() as s:
                row = s.get(Stream, st.id)
                if row is None:
                    continue
                row.last_checked = current
                s.add(row)
                s.commit()
            if live:
                log.info("La chaîne %s est passée en direct : clipping lancé", st.url)
                j = start_clipping(st, self.queue)
                if j:
                    started.append(j)
            bus.publish("stream.updated", {"id": st.id})
        return started

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Surveillance des lives")
            self._stop.wait(self.interval)
