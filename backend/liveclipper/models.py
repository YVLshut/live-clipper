"""Tables SQLite (SQLModel)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))


class Source(SQLModel, table=True):
    """Un live (ou une VOD) d'où proviennent des clips."""
    id: str = Field(primary_key=True)          # ex : twitch_v123456
    url: str                                   # URL du live
    author: str = "inconnu"
    author_url: Optional[str] = None           # URL de la chaîne
    title: Optional[str] = None
    platform: Optional[str] = None             # Twitch / YouTube / Kick / Fichier local
    date: Optional[str] = None                 # AAAA-MM-JJ
    was_live: bool = False
    duration: Optional[float] = None
    work_dir: Optional[str] = None
    created_at: datetime = Field(default_factory=now)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = "clip"                          # clip | rerender
    url: Optional[str] = None
    options: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "queued"                      # queued | running | done | failed | cancelled
    step: Optional[str] = None                  # download | transcribe | detect | render
    progress: float = 0.0                       # 0..1 sur l'ensemble du job
    message: Optional[str] = None
    error: Optional[str] = None
    warnings: list = Field(default_factory=list, sa_column=Column(JSON))
    source_id: Optional[str] = None
    clip_id: Optional[str] = None
    clips_count: int = 0
    extra: Optional[dict] = Field(default_factory=dict, sa_column=Column(JSON))  # live : durée enregistrée, tranches
    stream_id: Optional[int] = Field(default=None, index=True)   # live de la liste « Mes lives »
    created_at: datetime = Field(default_factory=now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class Clip(SQLModel, table=True):
    id: str = Field(primary_key=True)          # <source>_<NN>
    source_id: str = Field(index=True)
    job_id: Optional[int] = None
    file: str
    start: float
    end: float
    duration: float
    score: Optional[float] = None
    title: str = ""
    hook: str = ""
    caption: str = ""
    hashtags: list = Field(default_factory=list, sa_column=Column(JSON))
    layout: str = "blur"
    status: str = "pending"                     # pending | approved | rejected
    rendering: bool = False
    version: int = 1                            # incrémenté à chaque remontage (cache du lecteur)
    created_at: datetime = Field(default_factory=now)


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str                               # instagram | tiktok
    name: str
    mode: str = "api"                           # api | browser
    avatar: Optional[str] = None                # URL ou chemin local
    status: str = "disconnected"                # connected | reconnect | disconnected
    status_message: Optional[str] = None
    external_id: Optional[str] = None           # id IG business / open_id TikTok
    username: Optional[str] = None
    extra: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # Règles de publication
    auto_publish: bool = False
    require_approval: bool = True
    min_score: float = 7.0
    max_per_day: int = 3
    time_windows: list = Field(default_factory=lambda: [["10:00", "13:00"], ["18:00", "23:00"]],
                               sa_column=Column(JSON))
    delay_min_minutes: int = 45
    delay_max_minutes: int = 120
    privacy_level: Optional[str] = None         # TikTok : PUBLIC_TO_EVERYONE, SELF_ONLY...
    created_at: datetime = Field(default_factory=now)


class Publication(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    clip_id: str = Field(index=True)
    account_id: int = Field(index=True)
    status: str = "scheduled"   # scheduled | running | published | failed | paused | cancelled
    scheduled_at: datetime = Field(default_factory=now)
    published_at: Optional[datetime] = None
    post_url: Optional[str] = None
    error: Optional[str] = None
    screenshot: Optional[str] = None
    caption: Optional[str] = None
    attempts: int = 0
    auto: bool = False                          # créée par la publication automatique
    campaign_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=now)


class Campaign(SQLModel, table=True):
    """« Publier N clips sur chacun de ces comptes » (onglet Publier)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    count: int                                   # clips à publier PAR compte
    account_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    interval_minutes: Optional[int] = 60         # un clip toutes les N minutes, par compte
    status: str = "active"                       # active | done | cancelled
    created_at: datetime = Field(default_factory=now)
    finished_at: Optional[datetime] = None


class Stream(SQLModel, table=True):
    """Un live ajouté dans l'onglet Lives (chaîne surveillée ou rediffusion). L'œil = enabled."""
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(index=True)
    enabled: bool = True
    author: Optional[str] = None
    title: Optional[str] = None
    platform: Optional[str] = None
    options: dict = Field(default_factory=dict, sa_column=Column(JSON))
    last_checked: Optional[datetime] = None
    last_live_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)
