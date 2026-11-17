"""RelevanceAgent: scores how well each article matches a user's stated interests."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.text_utils import tokenize


@dataclass
class ArticleView:
    """Plain data passed between agents (decoupled from the ORM)."""

    id: int
    title: str
    text: str
    category: str
    source: str
    keywords: list[str]
    age_hours: float = 0.0


class RelevanceAgent:
    name = "relevance"

    def __init__(self, semantic_weight: float = 0.7):
        self.semantic_weight = semantic_weight

    def score(self, articles: list[ArticleView], interests: list[str]) -> dict[int, float]:
        """Return article_id -> relevance in [0, 1]. Combines TF-IDF cosine and keyword overlap."""
        if not articles:
            return {}
        interests = [i.strip() for i in interests if i and i.strip()]
        if not interests:
            return {a.id: 0.5 for a in articles}  # neutral when no interests are set
        docs = [f"{a.title} {a.title} {a.text}" for a in articles]
        try:
            vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
            doc_m = vec.fit_transform(docs)
            int_m = vec.transform(interests)
            sem = cosine_similarity(doc_m, int_m).max(axis=1)
        except ValueError:
            sem = np.zeros(len(articles))
        if sem.max() > 0:
            sem = sem / sem.max()

        interest_tokens = {t for i in interests for t in tokenize(i)}
        overlap = []
        for a in articles:
            tokens = set(tokenize(a.title)) | set(a.keywords) | {a.category.lower()}
            overlap.append(len(tokens & interest_tokens) / max(1, len(interest_tokens)))
        overlap = np.minimum(1.0, np.array(overlap) * 2)

        combined = self.semantic_weight * sem + (1 - self.semantic_weight) * overlap
        return {a.id: float(round(s, 4)) for a, s in zip(articles, combined)}
