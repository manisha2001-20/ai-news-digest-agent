"""Central configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _default_db_url() -> str:
    # PostgreSQL is the production database (docker-compose / Render).
    # SQLite is used only as a zero-setup fallback for local runs and tests.
    return f"sqlite:///{(BASE_DIR / 'data' / 'news_digest.db').as_posix()}"


def _normalise_db_url(url: str) -> str:
    # Render/Heroku hand out "postgres://", which SQLAlchemy 2 no longer accepts.
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _normalise_db_url(os.getenv("DATABASE_URL") or _default_db_url()))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    fetch_full_articles: bool = field(default_factory=lambda: os.getenv("FETCH_FULL_ARTICLES", "false").lower() == "true")
    request_timeout: float = field(default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT", "10")))
    max_articles_per_feed: int = field(default_factory=lambda: int(os.getenv("MAX_ARTICLES_PER_FEED", "20")))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    email_from: str = field(default_factory=lambda: os.getenv("EMAIL_FROM", "digest@example.com"))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


settings = Settings()
