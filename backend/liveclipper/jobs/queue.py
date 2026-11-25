"""File de jobs persistée en SQLite, exécutée par un thread unique (un job lourd à la fois)."""
from __future__ import annotations

import logging
import threading
import traceback
from typing import Callable

from sqlmodel import select

from .. import db
from ..errors import Cancelled, humanize
from ..events import bus
from ..models import Job, now

log = logging.getLogger("liveclipper.jobs")

STEPS = {  # étape -> (début, fin) dans la progression globale
    "download": (0.0, 0.30),
    "transcribe": (0.30, 0.70),
    "detect": (0.70, 0.80),
    "render": (0.80, 1.0),
}
STEP_LABELS = {"download": "Téléchargement", "transcribe": "Transcription",
               "detect": "Repérage IA", "render": "Montage"}


class JobContext:
    def __init__(self, queue: "JobQueue", job_id: int):
        self.queue, self.job_id = queue, job_id
        self.warnings: list[str] = []

    def job(self) -> Job:
        with db.session() as s:
            return s.get(Job, self.job_id)

    def cancelled(self) -> bool:
        return self.job_id in self.queue._cancel

    def update(self, **fields) -> Job:
        with db.session() as s:
            j = s.get(Job, self.job_id)
            for k, v in fields.items():
                setattr(j, k, v)
            s.add(j)
            s.commit()
            s.refresh(j)
        bus.publish("job.updated", j)
        return j

    def step(self, step: str, frac: float = 0.0, message: str | None = None) -> None:
        a, b = STEPS.get(step, (0.0, 1.0))
        self.update(step=step, progress=round(a + (b - a) * max(0.0, min(1.0, frac)), 4),
                    message=message or STEP_LABELS.get(step))

    def progress_for(self, step: str):
        return lambda f, m=None: self.step(step, f, m)

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)
            self.update(warnings=list(self.warnings))


Handler = Callable[[JobContext], None]


class Detached(Exception):
    """Le job a été confié à un autre exécutant (ex. enregistrement d'un live en direct) : la file
    ne doit pas changer son statut."""


class JobQueue:
    def __init__(self, handlers: dict[str, Handler]):
        self.handlers = handlers
        self._cancel: set[int] = set()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.current: int | None = None

    # ------------------------------------------------------------ cycle de vie
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        with db.session() as s:  # reprise après un arrêt brutal
            for j in s.exec(select(Job).where(Job.status == "running", Job.kind != "live")).all():
                j.status, j.message = "queued", "Repris après redémarrage"
                s.add(j)
            s.commit()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        self._wake.set()
        if self.current is not None:
            self._cancel.add(self.current)
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------ API
    def submit(self, kind: str, url: str | None = None, options: dict | None = None,
               clip_id: str | None = None) -> Job:
        with db.session() as s:
            j = Job(kind=kind, url=url, options=options or {}, clip_id=clip_id,
                    message="En attente")
            s.add(j)
            s.commit()
            s.refresh(j)
        bus.publish("job.updated", j)
        self._wake.set()
        return j

    def cancel(self, job_id: int) -> Job | None:
        with db.session() as s:
            j = s.get(Job, job_id)
            if j is None:
                return None
            if j.status == "queued":
                j.status, j.message, j.finished_at = "cancelled", "Annulé", now()
                s.add(j)
                s.commit()
                s.refresh(j)
                bus.publish("job.updated", j)
            elif j.status == "running":
                self._cancel.add(job_id)
            return j

    # ------------------------------------------------------------ boucle
    def _next(self) -> Job | None:
        with db.session() as s:
            jobs = s.exec(select(Job).where(Job.status == "queued", Job.kind != "live").order_by(Job.id)).all()
        if not jobs:
            return None
        # les remontages (rapides) passent avant les nouveaux lives
        jobs.sort(key=lambda j: (j.kind != "rerender", j.id))
        return jobs[0]

    def _loop(self) -> None:
        while not self._stop.is_set():
            job = self._next()
            if job is None:
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            self._run(job)

    def run_sync(self, job_id: int) -> Job:
        """Exécute un job dans le thread courant (CLI, tests)."""
        with db.session() as s:
            job = s.get(Job, job_id)
        self._run(job)
        with db.session() as s:
            return s.get(Job, job_id)

    def _run(self, job: Job) -> None:
        ctx = JobContext(self, job.id)
        self.current = job.id
        ctx.update(status="running", started_at=now(), error=None, message="Démarrage…")
        try:
            handler = self.handlers[job.kind]
            handler(ctx)
            ctx.update(status="done", progress=1.0, finished_at=now(), message=ctx.job().message or "Terminé")
        except Detached:
            log.info("Job %s confié à un autre exécutant", job.id)
        except Cancelled:
            ctx.update(status="cancelled", message="Annulé", finished_at=now())
        except Exception as e:
            log.error("Job %s (%s) en échec : %s\n%s", job.id, job.kind, e, traceback.format_exc())
            msg = humanize(e)
            ctx.update(status="failed", error=msg, message="Échec", finished_at=now())
            bus.notify(f"Échec du job : {msg}", "error", job_id=job.id)
        finally:
            self._cancel.discard(job.id)
            self.current = None
