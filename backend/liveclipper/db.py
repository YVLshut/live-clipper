"""Connexion SQLite."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401  (enregistre les tables)
from . import paths

_engine = None
_lock = threading.Lock()


def engine():
    global _engine
    with _lock:
        if _engine is None:
            _engine = create_engine(f"sqlite:///{paths.db_path()}",
                                    connect_args={"check_same_thread": False, "timeout": 30})

            @event.listens_for(_engine, "connect")
            def _pragma(conn, _):
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

            SQLModel.metadata.create_all(_engine)
        return _engine


def reset_engine() -> None:
    """Pour les tests : force la reconnexion (après changement de LIVECLIPPER_HOME)."""
    global _engine
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None


@contextmanager
def session() -> Iterator[Session]:
    with Session(engine(), expire_on_commit=False) as s:
        yield s
