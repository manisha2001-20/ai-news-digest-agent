"""PersonalizationAgent: learns from feedback and builds a diverse, ranked selection."""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.agents.relevance import ArticleView


@dataclass
class RankedArticle:
    article: ArticleView
    relevance: float
    preference: float
    recency: float
    score: float


class PersonalizationAgent:
    name = "personalization"

    def __init__(self, learning_rate: float = 0.2, half_life_hours: float = 36.0, max_per_source: int = 3):
        self.learning_rate = learning_rate
        self.half_life_hours = half_life_hours
        self.max_per_source = max_per_source

    # ---- learning -------------------------------------------------------------
    def update_weights(self, category_weights: dict, keyword_weights: dict, article: ArticleView, value: int) -> tuple[dict, dict]:
        """Nudge category/keyword weights toward +1 (like) or -1 (dislike). Weights are clipped to [-1, 1]."""
        if value not in (1, -1):
            raise ValueError("feedback value must be +1 or -1")
        cw = dict(category_weights or {})
        kw = dict(keyword_weights or {})
        cat = article.category.lower()
        cw[cat] = _clip(cw.get(cat, 0.0) + self.learning_rate * value)
        for k in article.keywords[:6]:
            kw[k] = _clip(kw.get(k, 0.0) + self.learning_rate * 0.5 * value)
        # keep the keyword table small
        if len(kw) > 200:
            kw = dict(sorted(kw.items(), key=lambda x: -abs(x[1]))[:200])
        return cw, kw

    # ---- ranking --------------------------------------------------------------
    def preference(self, article: ArticleView, category_weights: dict, keyword_weights: dict) -> float:
        cat = (category_weights or {}).get(article.category.lower(), 0.0)
        kws = [keyword_weights.get(k, 0.0) for k in article.keywords] if keyword_weights else []
        kw = sum(kws) / len(kws) if kws else 0.0
        return 0.6 * cat + 0.4 * kw  # in [-1, 1]

    def recency(self, age_hours: float) -> float:
        return math.exp(-math.log(2) * max(0.0, age_hours) / self.half_life_hours)

    def rank(
        self,
        articles: list[ArticleView],
        relevance: dict[int, float],
        category_weights: dict,
        keyword_weights: dict,
        k: int,
        exclude_ids: set[int] | None = None,
    ) -> list[RankedArticle]:
        exclude_ids = exclude_ids or set()
        scored = []
        for a in articles:
            if a.id in exclude_ids:
                continue
            rel = relevance.get(a.id, 0.0)
            pref = self.preference(a, category_weights, keyword_weights)
            rec = self.recency(a.age_hours)
            score = 0.55 * rel + 0.25 * (pref + 1) / 2 + 0.20 * rec
            scored.append(RankedArticle(a, rel, pref, rec, round(score, 4)))
        scored.sort(key=lambda r: r.score, reverse=True)

        # diversity: cap articles per source and avoid near-duplicate titles
        chosen: list[RankedArticle] = []
        per_source: dict[str, int] = {}
        seen_titles: list[set[str]] = []
        for r in scored:
            if per_source.get(r.article.source, 0) >= self.max_per_source:
                continue
            words = set(r.article.title.lower().split())
            if any(len(words & s) / max(1, len(words | s)) > 0.6 for s in seen_titles):
                continue
            chosen.append(r)
            per_source[r.article.source] = per_source.get(r.article.source, 0) + 1
            seen_titles.append(words)
            if len(chosen) >= k:
                break
        return chosen


def _clip(x: float) -> float:
    return max(-1.0, min(1.0, round(x, 4)))
