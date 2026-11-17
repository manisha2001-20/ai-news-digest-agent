"""SQLAlchemy engine/session setup (PostgreSQL in production, SQLite fallback)."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        db_path = url.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


class Database:
    """Owns an engine + session factory so tests can use an isolated database."""

    def __init__(self, url: str):
        self.url = url
        self.engine = make_engine(url)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        from app import models  # noqa: F401  (register models on Base.metadata)

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
