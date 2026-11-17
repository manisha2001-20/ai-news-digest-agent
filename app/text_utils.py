"""Small, dependency-light text helpers shared by the agents."""
from __future__ import annotations

import html
import re
from collections import Counter

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having
he her here hers herself him himself his how i if in into is it its itself just me more most my myself new
no nor not now of off on once only or other our ours ourselves out over own said same says she should so some
such than that the their theirs them themselves then there these they this those through to too under until
up very was we were what when where which while who whom why will with would you your yours yourself
yourselves year years one two us its it's also may might could would via per more most many much
""".split())

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]{2,}")


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [s.strip() for s in _SENT_RE.split(text) if len(s.strip()) > 20]


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if w.lower() not in STOPWORDS]


def top_keywords(text: str, k: int = 8) -> list[str]:
    counts = Counter(tokenize(text))
    return [w for w, _ in counts.most_common(k)]


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"
