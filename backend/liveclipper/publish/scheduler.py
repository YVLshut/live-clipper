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
from ..models import Account, Campaign, Clip, Publication, now

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


# ------------------------------------------------------------------ campagnes (onglet Publier)
def campaign_counts(campaign_id: int, account_id: int) -> dict[str, int]:
    with db.session() as s:
        pubs = s.exec(select(Publication).where(Publication.campaign_id == campaign_id,
                                                Publication.account_id == account_id)).all()
    out = {"published": 0, "scheduled": 0, "running": 0, "paused": 0, "failed": 0}
    for p in pubs:
        if p.status in out:
            out[p.status] += 1
    return out


def campaign_candidates(account: Account) -> list[Clip]:
    """Clips publiables sur ce compte, du plus intéressant au moins intéressant :
    d'abord ceux encore jamais utilisés sur un autre compte (« différents si possible »), puis par score."""
    with db.session() as s:
        clips = s.exec(select(Clip).where(Clip.status != "rejected", Clip.rendering == False)).all()  # noqa: E712
        active = s.exec(select(Publication).where(Publication.status.in_(ACTIVE))).all()
    taken_here = {p.clip_id for p in active if p.account_id == account.id}
    usage: dict[str, int] = {}
    for p in active:
        usage[p.clip_id] = usage.get(p.clip_id, 0) + 1
    clips = [c for c in clips if c.id not in taken_here and (c.score or 0) >= (account.min_score or 0)]
    return sorted(clips, key=lambda c: (usage.get(c.id, 0), -(c.score or 0), c.created_at))


JITTER_MINUTES = 5   # petite variation aléatoire autour de l'intervalle (évite un rythme de robot)


MAX_CONSECUTIVE_FAILURES = 3


def last_post_time(account_id: int) -> datetime | None:
    """Heure du dernier post de ce compte (publié, prévu, ou tentative en échec), toutes campagnes
    confondues : un échec compte aussi, pour ne pas réessayer en boucle sans attendre l'intervalle."""
    with db.session() as s:
        pubs = s.exec(select(Publication).where(Publication.account_id == account_id,
                                                Publication.status.in_(ACTIVE + ("failed",)))).all()
    times = [p.published_at or p.scheduled_at for p in pubs]
    return max(times) if times else None


def consecutive_failures(campaign_id: int, account_id: int) -> int:
    with db.session() as s:
        pubs = s.exec(select(Publication).where(Publication.campaign_id == campaign_id,
                                                Publication.account_id == account_id)
                      .order_by(Publication.id.desc())).all()
    n = 0
    for p in pubs:
        if p.status != "failed":
            break
        n += 1
    return n


def plan_campaigns(current: datetime | None = None, rng: random.Random | None = None) -> list[Publication]:
    """Pour chaque campagne active et chaque compte : programme le PROCHAIN clip seulement,
    un intervalle (1 h par défaut) après le dernier post du compte, jusqu'au nombre demandé."""
    rng = rng or random.Random()
    current = (current or datetime.now(timezone.utc)).astimezone(timezone.utc)
    created: list[Publication] = []
    with db.session() as s:
        campaigns = s.exec(select(Campaign).where(Campaign.status == "active").order_by(Campaign.id)).all()
        accounts = {a.id: a for a in s.exec(select(Account)).all()}
    for camp in campaigns:
        interval = timedelta(minutes=int(camp.interval_minutes or 60))
        all_done = True
        for aid in camp.account_ids or []:
            acc = accounts.get(aid)
            if acc is None:
                continue
            counts = campaign_counts(camp.id, aid)
            if counts["published"] < camp.count:
                all_done = False
            pending = counts["scheduled"] + counts["running"] + counts["paused"]
            remaining = camp.count - counts["published"] - pending
            if remaining <= 0 or pending > 0 or acc.status != "connected":
                continue          # un seul post en attente à la fois par compte
            if consecutive_failures(camp.id, aid) >= MAX_CONSECUTIVE_FAILURES:
                continue          # en pause : l'utilisateur doit regarder l'erreur (Réessayer relance)
            candidates = campaign_candidates(acc)
            if not candidates:
                continue          # plus de clip disponible : on attendra les prochains lives
            last = last_post_time(aid)
            slot = current
            if last is not None:
                jitter = timedelta(minutes=rng.uniform(0, JITTER_MINUTES))
                slot = max(current, last.astimezone(timezone.utc) + interval + jitter)
            pub = Publication(clip_id=candidates[0].id, account_id=aid, scheduled_at=slot, auto=True,
                              campaign_id=camp.id)
            with db.session() as s:
                s.add(pub)
                s.commit()
                s.refresh(pub)
            created.append(pub)
            bus.publish("publication.updated", pub)
        if all_done and camp.account_ids:
            with db.session() as s:
                c = s.get(Campaign, camp.id)
                c.status, c.finished_at = "done", now()
                s.add(c)
                s.commit()
            bus.publish("campaign.updated", {"id": camp.id})
            bus.notify(f"✔ Publication terminée : {camp.count} clips postés sur chaque compte.", "success")
    return created


def respace_overdue(account: Account, due: list[Publication], rng: random.Random | None = None) -> list[Publication]:
    """Après une fermeture de l'application, plusieurs posts d'un même compte peuvent être en retard.
    On n'en publie qu'un tout de suite et on réétale les autres selon les règles du compte
    (sinon ils partiraient tous à la suite, comme un robot). Renvoie la publication à lancer maintenant."""
    if not due:
        return []
    first, rest = due[0], due[1:]
    if not rest:
        return [first]
    ids = {p.id for p in rest}
    current = datetime.now(timezone.utc).astimezone()
    exist = [t for p_id, t in _times_by_pub(account.id) if p_id not in ids] + [current]
    for p in rest:
        slot = next_slot(current, account.time_windows, exist, account.max_per_day,
                         account.delay_min_minutes, account.delay_max_minutes, rng) or current + timedelta(days=1)
        exist.append(slot)
        with db.session() as s:
            row = s.get(Publication, p.id)
            row.scheduled_at = slot.astimezone(timezone.utc)
            s.add(row)
            s.commit()
            s.refresh(row)
        bus.publish("publication.updated", row)
        log.info("Publication %s en retard réétalée à %s", p.id, slot)
    return [first]


def _times_by_pub(account_id: int) -> list[tuple[int, datetime]]:
    with db.session() as s:
        pubs = s.exec(select(Publication).where(Publication.account_id == account_id,
                                                Publication.status.in_(ACTIVE))).all()
    return [(p.id, p.published_at or p.scheduled_at) for p in pubs]


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
        try:
            plan_campaigns()
        except Exception:
            log.exception("Planification des campagnes")
        by_id = {a.id: a for a in accounts if a.status == "connected"}
        with db.session() as s:
            due = s.exec(select(Publication).where(Publication.status == "scheduled",
                                                   Publication.scheduled_at <= now())
                         .order_by(Publication.scheduled_at)).all()
        per_account: dict[int, list[Publication]] = {}
        for p in due:
            if p.account_id in by_id:
                per_account.setdefault(p.account_id, []).append(p)
        for aid, pubs in per_account.items():
            for p in respace_overdue(by_id[aid], pubs):
                self.enqueue(p.id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Planificateur")
            self._stop.wait(self.interval)
