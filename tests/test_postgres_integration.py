"""Runs the full pipeline + API against a REAL PostgreSQL server.

Uses TEST_DATABASE_URL if set (e.g. the docker-compose database), otherwise starts an embedded
PostgreSQL with the optional `pgserver` package (pip install -r requirements-dev.txt).
Skipped when neither is available, so the default test run stays dependency-free.
"""
import os
import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings
from app.database import Database
from app.pipeline import NewsDigestPipeline


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        yield url
        return
    pgserver = pytest.importorskip("pgserver", reason="set TEST_DATABASE_URL or pip install pgserver")
    srv = pgserver.get_server(str(tmp_path_factory.mktemp("pg")), cleanup_mode="stop")
    base = srv.get_uri()
    dbname = f"digest_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.replace("postgresql://", "postgresql+psycopg2://"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {dbname}"))
    admin.dispose()
    yield base.rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg2://") + f"/{dbname}"


@pytest.fixture()
def pg_settings(pg_url):
    return replace(Settings(), database_url=pg_url, openai_api_key="", smtp_host="", smtp_user="", smtp_password="")


def test_tables_created_in_postgres(pg_settings):
    db = Database(pg_settings.database_url)
    db.create_all()
    assert db.engine.dialect.name == "postgresql"
    with db.engine.connect() as c:
        tables = {r[0] for r in c.execute(text("select tablename from pg_tables where schemaname='public'"))}
    assert {"feeds", "articles", "user_profiles", "feedback", "digests", "pipeline_runs"} <= tables


def test_pipeline_on_postgres(pg_settings, offline_feeds):
    db = Database(pg_settings.database_url)
    db.create_all()
    with db.engine.begin() as c:  # isolate from other tests in this module
        c.execute(text("TRUNCATE feedback, digests, articles, feeds, user_profiles, pipeline_runs RESTART IDENTITY CASCADE"))
    p = NewsDigestPipeline(db, pg_settings)
    p.seed_defaults(offline_feeds)
    run = p.run()
    assert run.feeds_ok == 4 and run.new_articles == 14
    assert p.run().new_articles == 0                      # unique link constraint + dedup work on Postgres
    _, ranked = p.personalised_feed(1, k=5)
    p.record_feedback(1, ranked[0][1].id, 1)              # JSON columns update on Postgres
    d = p.build_digest(1)
    assert d.status == "preview" and len(d.article_ids) == 8


def test_api_on_postgres(pg_settings, offline_feeds, monkeypatch):
    monkeypatch.setattr("app.pipeline.DEFAULT_FEEDS_FILE", offline_feeds)
    from app.web.main import create_app

    with TestClient(create_app(pg_settings)) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        client.post("/api/run")
        assert client.get("/").status_code == 200
        assert len(client.get("/api/users/1/feed?k=3").json()) == 3
