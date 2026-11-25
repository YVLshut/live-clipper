"""Planification des publications : règles par compte (plages horaires, quotas, délais aléatoires)."""
from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlmodel import select

from .. import db
from ..events import bus
from ..models import Account, Clip, Publication, now

log = logging.getLogger("liveclipper.scheduler")

ACTIVE = ("scheduled", "running", "published", "paused")


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def parse_windows(windows: list) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    out = []
    for w in windows or []:
        try:
            a, b = _hm(w[0]), _hm(w[1])
        except (ValueError, IndexError, TypeError, AttributeError):
            continue
        if a < b:
            out.append((a, b))
    return sorted(out) or [((0, 0), (23, 59))]


def next_slot(start: datetime, windows: list, existing: list[datetime], max_per_day: int,
              delay_min: int, delay_max: int, rng: random.Random | None = None,
              horizon_days: int = 14) -> datetime | None:
    """Premier créneau ≥ start qui respecte les plages horaires (heure locale de `start`),
    le quota quotidien et un délai aléatoire entre deux posts. Renvoie None si rien dans l'horizon."""
    rng = rng or random.Random()
    tz = start.tzinfo
    wins = parse_windows(windows)
    exist = sorted(e.astimezone(tz) for e in existing)
    lo, hi = sorted((max(0, int(delay_min)), max(0, int(delay_max))))
    gap = timedelta(minutes=rng.uniform(lo, hi)) if hi else timedelta(0)
    cand = start
    limit = start + timedelta(days=horizon_days)
    for _ in range(500):
        if cand > limit:
            return None
        day = cand.date()
        if max_per_day and sum(1 for e in exist if e.date() == day) >= max_per_day:
            cand = datetime.combine(day + timedelta(days=1), datetime.min.time(), tz)
            continue
        placed = None
        for (ah, am), (bh, bm) in wins:
            ws = datetime.combine(day, datetime.min.time(), tz).replace(hour=ah, minute=am)
            we = datetime.combine(day, datetime.min.time(), tz).replace(hour=bh, minute=bm)
            if cand <= we:
                placed = max(cand, ws)
                break
        if placed is None:
            cand = datetime.combine(day + timedelta(days=1), datetime.min.time(), tz)
            continue
        clash = [e for e in exist if abs((e - placed).total_seconds()) < gap.total_seconds()]
        if clash:
            cand = max(clash) + gap
            continue
        return placed
    return None


def eligible_clips(account: Account) -> list[Clip]:
    statuses = ["approved"] if account.require_approval else ["approved", "pending"]
    with db.session() as s:
        clips = s.exec(select(Clip).where(Clip.status.in_(statuses), Clip.rendering == False)).all()  # noqa: E712
        taken = {p.clip_id for p in s.exec(select(Publication).where(
            Publication.account_id == account.id, Publication.status.in_(ACTIVE))).all()}
    clips = [c for c in clips if c.id not in taken and (c.score or 0) >= account.min_score]
    return sorted(clips, key=lambda c: -(c.score or 0))


def existing_times(account_id: int) -> list[datetime]:
    with db.session() as s:
        pubs = s.exec(select(Publication).where(Publication.account_id == account_id,
                                                Publication.status.in_(ACTIVE))).all()
    return [(p.published_at or p.scheduled_at) for p in pubs]


def plan_auto(account: Account, current: datetime | None = None, rng: random.Random | None = None,
              horizon_hours: int = 48) -> list[Publication]:
    """Programme automatiquement les clips éligibles d'un compte (publication automatique activée)."""
    if not account.auto_publish or account.status != "connected":
        return []
    current = (current or datetime.now(timezone.utc)).astimezone()
    created = []
    exist = existing_times(account.id)
    for clip in eligible_clips(account):
        slot = next_slot(current, account.time_windows, exist, account.max_per_day,
                         account.delay_min_minutes, account.delay_max_minutes, rng)
        if slot is None or slot > current + timedelta(hours=horizon_hours):
            break
        pub = Publication(clip_id=clip.id, account_id=account.id, scheduled_at=slot.astimezone(timezone.utc),
                          auto=True)
        with db.session() as s:
            s.add(pub)
            s.commit()
            s.refresh(pub)
        exist.append(slot)
        created.append(pub)
        bus.publish("publication.updated", pub)
        log.info("Publication auto programmée : clip %s sur compte %s à %s", clip.id, account.id, slot)
    return created


class Scheduler:
    """Thread qui programme les publications automatiques et déclenche celles qui sont dues."""

    def __init__(self, enqueue: Callable[[int], None], refresh_tokens: Callable[[], None]):
        self.enqueue, self.refresh_tokens = enqueue, refresh_tokens
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_refresh = 0.0
        self.interval = 20.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        with db.session() as s:  # publications interrompues par un arrêt brutal
            for p in s.exec(select(Publication).where(Publication.status == "running")).all():
                p.status, p.error = "failed", "Interrompue par la fermeture de l'application"
                s.add(p)
            s.commit()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(3)

    def tick(self) -> None:
        if time.time() - self._last_refresh > 3600:
            self._last_refresh = time.time()
            try:
                self.refresh_tokens()
            except Exception:
                log.exception("Rafraîchissement des jetons")
        with db.session() as s:
            accounts = s.exec(select(Account)).all()
        for a in accounts:
            try:
                plan_auto(a)
            except Exception:
                log.exception("Planification du compte %s", a.id)
        connected = {a.id for a in accounts if a.status == "connected"}
        with db.session() as s:
            due = s.exec(select(Publication).where(Publication.status == "scheduled",
                                                   Publication.scheduled_at <= now())
                         .order_by(Publication.scheduled_at)).all()
        for p in due:
            if p.account_id in connected:
                self.enqueue(p.id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Planificateur")
            self._stop.wait(self.interval)
