"""Orchestrator that coordinates the collector and the four agents against the database."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.email_agent import EmailAgent, to_email_items
from app.agents.personalization import PersonalizationAgent
from app.agents.relevance import ArticleView, RelevanceAgent
from app.agents.summarizer import SummarizerAgent
from app.config import BASE_DIR, Settings
from app.database import Database
from app.ingestion.extractor import fetch_article_text
from app.ingestion.rss_collector import FeedError, parse_feed
from app.llm import LLMClient
from app.models import Article, Digest, Feed, Feedback, PipelineRun, UserProfile, utcnow
from app.text_utils import top_keywords

log = logging.getLogger(__name__)
DEFAULT_FEEDS_FILE = BASE_DIR / "data" / "feeds.json"


class NotFoundError(Exception):
    pass


class NewsDigestPipeline:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.llm = LLMClient(settings)
        self.summarizer = SummarizerAgent(self.llm)
        self.relevance = RelevanceAgent()
        self.personalization = PersonalizationAgent()
        self.email = EmailAgent(settings, self.llm)

    # ------------------------------------------------------------------ setup
    def seed_defaults(self, feeds_file: Path | None = None) -> None:
        """Insert default feeds and a demo user if the database is empty."""
        feeds_file = feeds_file or DEFAULT_FEEDS_FILE
        with self.db.session() as s:
            if s.scalar(select(func.count(Feed.id))) == 0 and feeds_file.exists():
                for f in json.loads(feeds_file.read_text(encoding="utf-8")):
                    url = f["url"]
                    if not url.startswith(("http://", "https://", "file://")):
                        url = (BASE_DIR / url).as_posix()  # relative sample file
                    s.add(Feed(name=f["name"], url=url, category=f.get("category", "general")))
            if s.scalar(select(func.count(UserProfile.id))) == 0:
                s.add(UserProfile(name="Demo Reader", email="demo@example.com",
                                  interests=["artificial intelligence", "machine learning", "space exploration", "climate"]))

    # ---------------------------------------------------------------- ingest
    def run(self, fetch_full: bool | None = None) -> PipelineRun:
        """Collect all active feeds, store new articles, summarise the ones without a summary."""
        fetch_full = self.settings.fetch_full_articles if fetch_full is None else fetch_full
        start = time.perf_counter()
        run_log: list[str] = []
        ok = failed = new = summarised = 0
        with self.db.session() as s:
            feeds = s.scalars(select(Feed).where(Feed.active.is_(True))).all()
            existing = set(s.scalars(select(Article.link)).all())
            for feed in feeds:
                try:
                    raw = parse_feed(feed.url, feed.name, feed.category, self.settings.request_timeout,
                                     self.settings.max_articles_per_feed)
                    feed.last_error = None
                    ok += 1
                except FeedError as exc:
                    feed.last_error = str(exc)[:500]
                    failed += 1
                    run_log.append(f"FAILED {feed.name}: {exc}")
                    continue
                finally:
                    feed.last_fetched = utcnow()
                added = 0
                for r in raw:
                    if r.link in existing:
                        continue
                    content = fetch_article_text(r.link, r.summary, self.settings.request_timeout) if fetch_full else r.summary
                    s.add(Article(feed_id=feed.id, title=r.title[:500], link=r.link[:1000], source=r.source[:200],
                                  category=r.category, published=r.published, raw_summary=r.summary,
                                  content=content, keywords=top_keywords(f"{r.title} {content}")))
                    existing.add(r.link)
                    added += 1
                new += added
                run_log.append(f"{feed.name}: {len(raw)} entries, {added} new")
            s.flush()
            for art in s.scalars(select(Article).where(Article.ai_summary.is_(None))).all():
                res = self.summarizer.summarize(art.title, art.content or art.raw_summary)
                art.ai_summary, art.summary_method = res.text, res.method
                summarised += 1
            run = PipelineRun(feeds_ok=ok, feeds_failed=failed, new_articles=new, summarised=summarised,
                              duration_s=round(time.perf_counter() - start, 2), log=run_log)
            s.add(run)
        return run

    # --------------------------------------------------------------- ranking
    @staticmethod
    def _view(a: Article) -> ArticleView:
        ref = a.published or a.created_at
        age = max(0.0, (utcnow() - ref).total_seconds() / 3600) if ref else 0.0
        return ArticleView(a.id, a.title, a.ai_summary or a.content or a.raw_summary, a.category, a.source,
                           list(a.keywords or []), age)

    def personalised_feed(self, user_id: int, k: int = 20, exclude_disliked: bool = True):
        with self.db.session() as s:
            user = s.get(UserProfile, user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            articles = s.scalars(select(Article).order_by(Article.created_at.desc()).limit(500)).all()
            views = [self._view(a) for a in articles]
            exclude = set()
            if exclude_disliked:
                exclude = set(s.scalars(select(Feedback.article_id).where(Feedback.user_id == user_id, Feedback.value < 0)).all())
            rel = self.relevance.score(views, user.interests or [])
            ranked = self.personalization.rank(views, rel, user.category_weights or {}, user.keyword_weights or {}, k, exclude)
            by_id = {a.id: a for a in articles}
            return user, [(r, by_id[r.article.id]) for r in ranked]

    def record_feedback(self, user_id: int, article_id: int, value: int) -> None:
        with self.db.session() as s:
            user, art = s.get(UserProfile, user_id), s.get(Article, article_id)
            if user is None or art is None:
                raise NotFoundError("user or article not found")
            cw, kw = self.personalization.update_weights(user.category_weights, user.keyword_weights, self._view(art), value)
            user.category_weights, user.keyword_weights = cw, kw
            s.add(Feedback(user_id=user_id, article_id=article_id, value=value))

    # ---------------------------------------------------------------- digest
    def build_digest(self, user_id: int, send: bool = True) -> Digest:
        with self.db.session() as s:
            user = s.get(UserProfile, user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            _, ranked = self.personalised_feed(user_id, k=user.digest_size)
            lookup = {a.id: {"title": a.title, "link": a.link, "source": a.source, "category": a.category,
                             "summary": a.ai_summary or a.raw_summary} for _, a in ranked}
            items = to_email_items([r for r, _ in ranked], lookup)
            rendered = self.email.render(user.name, items)
            status, error = "preview", None
            if send and items:
                sent, error = self.email.send(user.email, rendered)
                status = "sent" if sent else ("failed" if error else "preview")
            digest = Digest(user_id=user.id, subject=rendered.subject, html=rendered.html,
                            article_ids=[i for i in lookup], scores={str(r.article.id): r.score for r, _ in ranked},
                            status=status, error=error)
            s.add(digest)
            s.flush()
            return digest
