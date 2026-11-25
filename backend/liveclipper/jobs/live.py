"""Lives EN DIRECT : enregistrement par tranches, clipping de chaque tranche dès qu'elle est terminée.

Chaque live tourne dans son propre fil (l'enregistrement dure des heures et ne doit pas bloquer la file).
Une tranche finie devient un job « clip » ordinaire (fichier local + source du live), traité par la file
principale : la transcription et le montage restent séquentiels (un seul calcul lourd à la fois).
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from sqlmodel import select

from .. import config, db, paths
from ..errors import Cancelled, humanize
from ..events import bus
from ..models import Job, now
from ..pipeline import download
from ..pipeline.utils import duration, hms, run, safe, tool
from .queue import JobContext, JobQueue

log = logging.getLogger("liveclipper.live")

MIN_SEGMENT = 20.0          # tranche plus courte : ignorée
END_AFTER_FAILURES = 3      # le flux est introuvable N fois de suite -> live terminé


class LiveManager:
    def __init__(self, job_queue: JobQueue):
        self.queue = job_queue
        self.threads: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()
        # surchargeables (tests)
        self.stream_url: Callable[[str], str] = download.live_stream_url
        self.segment_seconds: Callable[[], float] = lambda: float(config.get("live_segment_minutes") or 30) * 60
        self.retry_wait = 20.0

    # ------------------------------------------------------------ cycle de vie
    def start(self) -> None:
        """Reprend les lives qui étaient en cours d'enregistrement à la fermeture de l'application."""
        with db.session() as s:
            jobs = s.exec(select(Job).where(Job.kind == "live", Job.status.in_(["running", "queued"]))).all()
        for j in jobs:
            src = (j.extra or {}).get("source")
            if src:
                self._spawn(j.id, j.url, src, j.options or {})

    def adopt(self, job_id: int, url: str, src: dict, options: dict) -> None:
        """Un job « clip » s'est révélé être un live en direct : il devient un job « live »."""
        extra = {"source": src, "recorded": 0.0, "segments": 0, "started": time.time()}
        JobContext(self.queue, job_id).update(kind="live", status="running", step="record", progress=0.0,
                                              source_id=None, extra=extra,
                                              message="En direct : enregistrement de la première tranche…")
        bus.notify(f"🔴 Live en direct détecté ({src.get('author')}) : clips créés toutes les "
                   f"{int(self.segment_seconds() // 60)} min pendant le live.", "info", job_id=job_id)
        self._spawn(job_id, url, src, options)

    def _spawn(self, job_id: int, url: str, src: dict, options: dict) -> None:
        with self._lock:
            t = self.threads.get(job_id)
            if t and t.is_alive():
                return
            t = threading.Thread(target=self._run_safe, args=(job_id, url, src, options),
                                 name=f"live-{job_id}", daemon=True)
            self.threads[job_id] = t
            t.start()

    def join(self, job_id: int, timeout: float | None = None) -> None:
        t = self.threads.get(job_id)
        if t:
            t.join(timeout)

    # ------------------------------------------------------------ enregistrement
    def _run_safe(self, job_id: int, url: str, src: dict, options: dict) -> None:
        ctx = JobContext(self.queue, job_id)
        try:
            self._record(ctx, url, src, options)
        except Cancelled:
            ctx.update(status="cancelled", message=self._summary(ctx, "Enregistrement arrêté"), finished_at=now())
        except Exception as e:
            log.error("Live %s : %s", job_id, traceback.format_exc())
            ctx.update(status="failed", error=humanize(e), message="Échec", finished_at=now())
            bus.notify(f"Échec de l'enregistrement du live : {humanize(e)}", "error", job_id=job_id)
        finally:
            self.queue._cancel.discard(job_id)

    @staticmethod
    def _summary(ctx: JobContext, prefix: str) -> str:
        ex = ctx.job().extra or {}
        return f"{prefix} : {hms(ex.get('recorded', 0))} enregistrées, {ex.get('segments', 0)} tranche(s) clippée(s)"

    def _record(self, ctx: JobContext, url: str, src: dict, options: dict) -> None:
        folder = paths.work_dir() / "lives" / safe(src["id"])
        folder.mkdir(parents=True, exist_ok=True)
        extra = dict(ctx.job().extra or {})
        k = int(extra.get("segments", 0))
        failures = 0
        while True:
            if ctx.cancelled():
                raise Cancelled()
            try:
                stream = self.stream_url(url)
                failures = 0
            except (subprocess.CalledProcessError, OSError) as e:
                failures += 1
                log.info("Live %s : flux introuvable (%s/%s) : %s", ctx.job_id, failures, END_AFTER_FAILURES, e)
                if failures >= END_AFTER_FAILURES:
                    break
                self._sleep(ctx, self.retry_wait)
                continue

            seg_len = self.segment_seconds()
            seg = folder / f"{safe(src['id'])}_tranche{k + 1:03d}.ts"
            ctx.update(step="record", message=f"🔴 En direct : enregistrement de la tranche {k + 1} "
                                              f"({hms(seg_len)} max)…")
            cancelled = False
            try:
                run([tool("ffmpeg"), "-y", "-v", "error", "-i", stream, "-t", f"{seg_len:.0f}",
                     "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy", "-f", "mpegts", str(seg)],
                    cancel=ctx.cancelled)
            except Cancelled:
                cancelled = True       # on clippe quand même ce qui a été enregistré
            except subprocess.CalledProcessError as e:
                log.warning("Live %s : enregistrement interrompu : %s", ctx.job_id, (e.stderr or "")[-300:])
            got = duration(seg) if seg.exists() else 0.0
            if got >= MIN_SEGMENT:
                self._submit_segment(ctx, seg, k, src, options, got)
                k += 1
            elif seg.exists():
                seg.unlink(missing_ok=True)
            if cancelled:
                raise Cancelled()
            if got < seg_len * 0.9:
                # tranche écourtée : coupure réseau ou fin du live -> on revérifie le flux
                failures += 0 if got >= MIN_SEGMENT else 1
                if failures >= END_AFTER_FAILURES:
                    break
                self._sleep(ctx, 3)
        ctx.update(status="done", progress=1.0, finished_at=now(), message=self._summary(ctx, "Live terminé"))
        bus.notify(f"Live de {src.get('author')} terminé : dernières tranches en cours de clipping.", "success",
                   job_id=ctx.job_id)

    def _submit_segment(self, ctx: JobContext, seg: Path, k: int, src: dict, options: dict, got: float) -> None:
        extra = dict(ctx.job().extra or {})
        extra["recorded"] = float(extra.get("recorded", 0)) + got
        extra["segments"] = k + 1
        ctx.update(extra=extra, message=f"🔴 En direct : tranche {k + 1} envoyée au clipping")
        opts = {key: v for key, v in options.items() if key != "section"}
        opts.update(live_source={kk: vv for kk, vv in src.items() if kk != "is_live"}, segment=k,
                    live_job_id=ctx.job_id)
        self.queue.submit("clip", url=str(seg), options=opts)
        log.info("Live %s : tranche %s (%.0f s) envoyée au clipping", ctx.job_id, k + 1, got)

    @staticmethod
    def _sleep(ctx: JobContext, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            if ctx.cancelled():
                raise Cancelled()
            time.sleep(0.5)

    def cancel(self, job_id: int) -> None:
        self.queue._cancel.add(job_id)
