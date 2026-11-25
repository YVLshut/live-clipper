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
            _add_missing_columns(_engine)
        return _engine


def _add_missing_columns(eng) -> None:
    """Migration légère : ajoute aux tables existantes les colonnes apparues dans une nouvelle version
    (create_all ne crée que les tables manquantes). Les nouvelles colonnes sont toujours facultatives."""
    from sqlalchemy import inspect, text
    insp = inspect(eng)
    with eng.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ddl = col.type.compile(dialect=eng.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


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
