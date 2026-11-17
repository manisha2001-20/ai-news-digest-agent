"""Collects articles from RSS/Atom feeds (remote URLs or local sample files)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import mktime

import feedparser
import requests

from app.text_utils import clean_html

log = logging.getLogger(__name__)
USER_AGENT = "ai-news-digest-agent/1.0 (+https://github.com/)"


@dataclass
class RawArticle:
    title: str
    link: str
    source: str
    category: str
    summary: str = ""
    published: datetime | None = None
    extra: dict = field(default_factory=dict)


class FeedError(Exception):
    """Raised when a feed cannot be fetched or parsed."""


def _load_feed_bytes(url: str, timeout: float) -> bytes:
    if url.startswith("file://") or Path(url).exists():
        path = Path(url.replace("file://", "", 1))
        if not path.exists():
            raise FeedError(f"Local feed file not found: {path}")
        return path.read_bytes()
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise FeedError(f"Could not download feed {url}: {exc}") from exc
    return resp.content


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime.fromtimestamp(mktime(value))
            except (OverflowError, ValueError, TypeError):
                continue
    return None


def parse_feed(url: str, source_name: str, category: str, timeout: float = 10, limit: int = 20) -> list[RawArticle]:
    """Fetch + parse one feed. Raises FeedError on network/parse failure."""
    data = _load_feed_bytes(url, timeout)
    parsed = feedparser.parse(data)
    if parsed.bozo and not parsed.entries:
        raise FeedError(f"Malformed feed {url}: {parsed.get('bozo_exception')}")
    articles: list[RawArticle] = []
    for entry in parsed.entries[:limit]:
        title = clean_html(entry.get("title"))
        link = entry.get("link") or ""
        if not title or not link:
            continue  # skip entries we cannot identify
        content = ""
        if entry.get("content"):
            content = clean_html(entry["content"][0].get("value", ""))
        articles.append(
            RawArticle(
                title=title,
                link=link.strip(),
                source=source_name or clean_html(parsed.feed.get("title", "")),
                category=category,
                summary=content or clean_html(entry.get("summary") or entry.get("description")),
                published=_entry_datetime(entry),
            )
        )
    return articles
