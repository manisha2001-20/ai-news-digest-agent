"""ORM models: feeds, articles, user profiles, feedback and generated digests."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Feed(Base):
    __tablename__ = "feeds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    category: Mapped[str] = mapped_column(String(100), default="general")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("link", name="uq_article_link"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feed_id: Mapped[int | None] = mapped_column(ForeignKey("feeds.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    link: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(100), default="general")
    published: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_method: Mapped[str | None] = mapped_column(String(30), nullable=True)  # "openai" | "extractive"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    feed: Mapped[Feed | None] = relationship()


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    interests: Mapped[list] = mapped_column(JSON, default=list)          # free-text topics
    category_weights: Mapped[dict] = mapped_column(JSON, default=dict)   # learned from feedback
    keyword_weights: Mapped[dict] = mapped_column(JSON, default=dict)    # learned from feedback
    digest_size: Mapped[int] = mapped_column(Integer, default=8)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    value: Mapped[int] = mapped_column(Integer)  # +1 like, -1 dislike
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Digest(Base):
    __tablename__ = "digests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"))
    subject: Mapped[str] = mapped_column(String(300))
    html: Mapped[str] = mapped_column(Text)
    article_ids: Mapped[list] = mapped_column(JSON, default=list)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="preview")  # preview | sent | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[UserProfile] = relationship()


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    feeds_ok: Mapped[int] = mapped_column(Integer, default=0)
    feeds_failed: Mapped[int] = mapped_column(Integer, default=0)
    new_articles: Mapped[int] = mapped_column(Integer, default=0)
    summarised: Mapped[int] = mapped_column(Integer, default=0)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    log: Mapped[list] = mapped_column(JSON, default=list)
