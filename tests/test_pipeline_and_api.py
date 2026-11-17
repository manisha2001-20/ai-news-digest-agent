import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ingestion.extractor import extract_text_from_html, fetch_article_text
from app.ingestion.rss_collector import FeedError, parse_feed
from app.models import Feed
from app.pipeline import NotFoundError
from app.web.main import create_app
from tests.conftest import ROOT


def test_parse_sample_feed():
    arts = parse_feed(str(ROOT / "data/sample_feeds/technology.xml"), "Sample", "technology")
    assert len(arts) == 5
    assert all(a.title and a.link.startswith("https://") for a in arts)
    assert arts[0].published is not None


def test_missing_feed_raises_feed_error(tmp_path):
    with pytest.raises(FeedError):
        parse_feed(f"file://{tmp_path / 'nope.xml'}", "x", "y")


def test_extractor_prefers_article_paragraphs():
    html = ("<html><nav><p>Menu menu menu menu menu menu menu menu menu menu menu menu</p></nav><article>"
            "<p>This paragraph is the real body of the article and it is long enough to keep.</p></article></html>")
    assert extract_text_from_html(html).startswith("This paragraph")


def test_extractor_returns_fallback_for_non_http():
    assert fetch_article_text("file:///x", "fallback") == "fallback"


def test_run_is_idempotent_and_summarises(pipeline):
    first = pipeline.run()
    assert first.feeds_ok == 4 and first.feeds_failed == 0
    assert first.new_articles == 14 and first.summarised == 14
    second = pipeline.run()
    assert second.new_articles == 0  # duplicates are skipped by link


def test_broken_feed_is_reported_not_fatal(pipeline):
    with pipeline.db.session() as s:
        s.add(Feed(name="Broken", url="file:///definitely/missing.xml", category="x"))
    run = pipeline.run()
    assert run.feeds_failed == 1 and run.feeds_ok == 4
    assert any("Broken" in line for line in run.log)


def test_personalised_feed_and_feedback(pipeline):
    pipeline.run()
    user, ranked = pipeline.personalised_feed(1, k=5)
    assert len(ranked) == 5
    top_article = ranked[0][1]
    pipeline.record_feedback(1, top_article.id, -1)
    _, ranked2 = pipeline.personalised_feed(1, k=20)
    assert top_article.id not in {a.id for _, a in ranked2}  # disliked articles are hidden


def test_unknown_user_raises(pipeline):
    with pytest.raises(NotFoundError):
        pipeline.personalised_feed(999)


def test_digest_is_saved_as_preview_without_smtp(pipeline):
    pipeline.run()
    d = pipeline.build_digest(1)
    assert d.status == "preview"
    assert len(d.article_ids) == 8
    assert "Your AI News Digest" in d.html


@pytest.fixture()
def client(settings, offline_feeds, monkeypatch):
    monkeypatch.setattr("app.pipeline.DEFAULT_FEEDS_FILE", offline_feeds)
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_web_pages_render(client):
    client.post("/api/run")
    for path in ["/", "/feeds", "/profile", "/digests"]:
        r = client.get(path)
        assert r.status_code == 200, path
    assert "Recommended for you" in client.get("/").text


def test_api_flow(client):
    assert client.get("/api/health").json()["status"] == "ok"
    run = client.post("/api/run").json()
    assert run["new_articles"] == 14
    feed = client.get("/api/users/1/feed?k=3").json()
    assert len(feed) == 3 and {"score", "relevance", "summary_method"} <= feed[0].keys()
    assert client.post("/api/feedback", json={"user_id": 1, "article_id": feed[0]["id"], "value": 1}).json()["ok"]
    assert client.post("/api/feedback", json={"user_id": 1, "article_id": feed[0]["id"], "value": 5}).status_code == 422
    assert client.get("/api/users/42/feed").status_code == 404
    d = client.post("/api/users/1/digest").json()
    assert d["status"] == "preview" and d["articles"] > 0


def test_profile_create_and_validation(client):
    r = client.post("/profile", data={"name": "Asha", "email": "asha@example.com", "interests": "space, climate"},
                    follow_redirects=False)
    assert r.status_code == 303
    bad = client.post("/profile", data={"name": "X", "email": "not-an-email"})
    assert "valid email" in bad.text


def test_add_feed_rejects_bad_url(client):
    r = client.post("/feeds", data={"name": "x", "url": "ftp://bad", "category": "t"})
    assert "must start with" in r.text


YOUTUBE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <title>Example Channel</title>
 <entry>
  <id>yt:video:abc123def45</id><yt:videoId>abc123def45</yt:videoId>
  <title>Gradient descent explained</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=abc123def45"/>
  <published>2026-11-01T10:00:00+00:00</published>
  <media:group><media:title>Gradient descent explained</media:title>
   <media:description>We explain gradient descent and learning rates with simple examples for beginners.</media:description></media:group>
 </entry>
</feed>"""


def test_youtube_channel_feed_format(tmp_path):
    f = tmp_path / "yt.xml"
    f.write_text(YOUTUBE_ATOM, encoding="utf-8")
    arts = parse_feed(str(f), "YouTube – Example", "youtube")
    assert len(arts) == 1
    assert arts[0].link == "https://www.youtube.com/watch?v=abc123def45"
    assert "gradient descent" in arts[0].summary.lower()
    assert arts[0].published is not None


def test_default_feed_list_has_15_plus_real_sources():
    import json
    feeds = json.loads((ROOT / "data" / "feeds.json").read_text(encoding="utf-8"))
    real = [f for f in feeds if f["url"].startswith("http")]
    assert len(real) >= 15
    assert sum("youtube.com/feeds" in f["url"] for f in real) >= 5
