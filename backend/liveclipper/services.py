"""Instances partagées (file de jobs, planificateur de publication)."""
from __future__ import annotations

from .jobs import clip_job
from .jobs.queue import JobContext, JobQueue


def _rerender(ctx: JobContext) -> None:
    try:
        clip_job.rerender(ctx)
    except BaseException:
        clip_job.on_rerender_failed(ctx.job().clip_id)
        raise


HANDLERS = {"clip": clip_job.run, "rerender": _rerender}

job_queue = JobQueue(HANDLERS)
