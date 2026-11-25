"""Bus d'événements : les threads de travail publient, le WebSocket diffuse au front."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlmodel import SQLModel

log = logging.getLogger(__name__)


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, SQLModel):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    return obj


class EventBus:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self.history: list[dict] = []      # pour les tests

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self.queues.discard(q)

    def _fanout(self, msg: dict) -> None:
        with self._lock:
            qs = list(self.queues)
        for q in qs:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def publish(self, type_: str, data: Any = None) -> None:
        msg = {"type": type_, "data": to_jsonable(data)}
        self.history.append(msg)
        if len(self.history) > 500:
            del self.history[:250]
        loop = self.loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._fanout, msg)
            except RuntimeError:
                pass

    def notify(self, message: str, level: str = "info", **extra: Any) -> None:
        """Notification affichée en toast dans l'interface."""
        log.info("Notification [%s] %s", level, message)
        self.publish("notification", {"message": message, "level": level, **extra})


bus = EventBus()


def dumps(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False)
