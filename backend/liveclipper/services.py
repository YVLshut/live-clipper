"""Instances partagées : file de jobs, worker de publication, planificateur."""
from __future__ import annotations

from .jobs import clip_job
from .jobs.live import LiveManager
from .jobs.queue import JobContext, JobQueue
from .jobs.streams import StreamWatcher
from .publish import accounts
from .publish.scheduler import Scheduler
from .publish.worker import PublishWorker


def _rerender(ctx: JobContext) -> None:
    try:
        clip_job.rerender(ctx)
    except BaseException:
        clip_job.on_rerender_failed(ctx.job().clip_id)
        raise


HANDLERS = {"clip": clip_job.run, "rerender": _rerender}

job_queue = JobQueue(HANDLERS)
live_manager = LiveManager(job_queue)
stream_watcher = StreamWatcher(job_queue)
publish_worker = PublishWorker()
scheduler = Scheduler(publish_worker.enqueue_publication, accounts.refresh_all)


def start_publishing() -> None:
    publish_worker.start()
    scheduler.start()


def stop_publishing() -> None:
    scheduler.stop()
    publish_worker.stop()
