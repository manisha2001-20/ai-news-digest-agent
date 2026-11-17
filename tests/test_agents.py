import pytest

from app.agents.personalization import PersonalizationAgent
from app.agents.relevance import ArticleView, RelevanceAgent
from app.agents.summarizer import SummarizerAgent
from app.text_utils import clean_html, split_sentences, top_keywords


def view(i, title, text, cat="technology", source="S", kws=None, age=1.0):
    return ArticleView(i, title, text, cat, source, kws or top_keywords(title + " " + text), age)


def test_clean_html_strips_tags_and_entities():
    assert clean_html("<p>Hello&nbsp;<b>world</b> &amp; co</p>") == "Hello world & co"


def test_split_sentences():
    s = split_sentences("This is the first sentence here. And this is the second one! Short.")
    assert len(s) == 2


def test_extractive_summary_has_at_most_three_sentences_from_source():
    text = ("Machine learning models are being deployed widely. Engineers monitor model drift in production. "
            "Weather was pleasant today in the city. Data pipelines feed models with fresh features. "
            "Teams evaluate models before release to avoid regressions.")
    out = SummarizerAgent(llm=None).summarize("Machine learning in production", text)
    assert out.method == "extractive"
    sents = split_sentences(out.text)
    assert 1 <= len(sents) <= 3
    assert all(s in text for s in sents)


def test_summarizer_handles_empty_text():
    out = SummarizerAgent(llm=None).summarize("Only a title", "")
    assert out.text == "Only a title"


def test_relevance_prefers_matching_articles():
    arts = [view(1, "New AI model improves machine learning accuracy", "artificial intelligence research"),
            view(2, "Cricket team wins the final", "sports match report", cat="sports")]
    scores = RelevanceAgent().score(arts, ["machine learning", "artificial intelligence"])
    assert scores[1] > scores[2]
    assert all(0 <= v <= 1 for v in scores.values())


def test_relevance_neutral_without_interests():
    assert RelevanceAgent().score([view(1, "x title", "y text")], []) == {1: 0.5}


def test_feedback_updates_weights_and_is_clipped():
    agent = PersonalizationAgent(learning_rate=0.6)
    a = view(1, "Space telescope", "galaxy images", cat="science")
    cw, kw = {}, {}
    for _ in range(5):
        cw, kw = agent.update_weights(cw, kw, a, 1)
    assert cw["science"] == 1.0
    cw, kw = agent.update_weights(cw, kw, a, -1)
    assert cw["science"] < 1.0


def test_feedback_rejects_invalid_value():
    with pytest.raises(ValueError):
        PersonalizationAgent().update_weights({}, {}, view(1, "a b c", "d e f"), 0)


def test_rank_respects_k_source_cap_and_exclusions():
    agent = PersonalizationAgent(max_per_source=2)
    titles = ["Rocket launch delayed", "Stock market rallies", "New vaccine trial", "Monsoon arrives early",
              "Chess champion crowned", "Library opens downtown"]
    arts = [view(i, t, "text", source="same") for i, t in enumerate(titles)]
    rel = {a.id: 0.5 for a in arts}
    ranked = agent.rank(arts, rel, {}, {}, k=5, exclude_ids={0})
    assert len(ranked) == 2
    assert all(r.article.id != 0 for r in ranked)


def test_liked_category_ranks_higher():
    agent = PersonalizationAgent()
    a = view(1, "Telescope finds galaxy", "astronomy", cat="science", source="A")
    b = view(2, "Market rises on earnings", "stocks", cat="business", source="B")
    rel = {1: 0.5, 2: 0.5}
    ranked = agent.rank([a, b], rel, {"science": 1.0, "business": -1.0}, {}, k=2)
    assert ranked[0].article.id == 1


def test_recency_decays():
    agent = PersonalizationAgent(half_life_hours=10)
    assert agent.recency(0) == pytest.approx(1.0)
    assert agent.recency(10) == pytest.approx(0.5)
