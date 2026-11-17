import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.database import Database
from app.pipeline import NewsDigestPipeline

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def settings(tmp_path):
    # isolated SQLite file per test, no OpenAI key, no SMTP => fully offline
    return replace(Settings(), database_url=f"sqlite:///{(tmp_path / 't.db').as_posix()}", openai_api_key="",
                   smtp_host="", smtp_user="", smtp_password="", fetch_full_articles=False)


@pytest.fixture()
def offline_feeds(tmp_path):
    feeds = [f for f in json.loads((ROOT / "data" / "feeds.json").read_text()) if not f["url"].startswith("http")]
    p = tmp_path / "feeds.json"
    p.write_text(json.dumps(feeds))
    return p


@pytest.fixture()
def pipeline(settings, offline_feeds):
    db = Database(settings.database_url)
    db.create_all()
    p = NewsDigestPipeline(db, settings)
    p.seed_defaults(offline_feeds)
    return p
