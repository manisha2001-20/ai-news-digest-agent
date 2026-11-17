# Deployment guide

## What has been verified (and how)

| Item | Status | Evidence |
|---|---|---|
| App + API on SQLite | ✅ Tested | `pytest` (all tests) |
| **PostgreSQL integration** | ✅ Tested against a real PostgreSQL 16 server | `tests/test_postgres_integration.py`, run with the embedded `pgserver` (`pip install -r requirements-dev.txt`) or `TEST_DATABASE_URL` |
| LLM summarization via the OpenAI client | ✅ Tested live through an OpenAI-compatible endpoint (local Ollama, `qwen2.5:3b`); OpenAI calls mocked in unit tests | `tests/test_llm_agents.py` |
| 18 real RSS sources (incl. 5 YouTube channel feeds) | ✅ Fetched and parsed live on 2026-11-17 | `data/feeds.json` |
| `docker-compose.yml` / `render.yaml` | ⚠️ Structure validated only | Docker was not available on the development laptop, and no Render account was connected |
| Docker image build / Render deployment | ❌ **Not yet executed** | Follow the steps below |

## Option A: Docker Compose (app + PostgreSQL)

Requires Docker Desktop (Windows/macOS) or Docker Engine (Linux).

```bash
cp .env.example .env            # change POSTGRES_PASSWORD; optionally set OPENAI_API_KEY
docker compose up --build -d
docker compose ps               # web should become "healthy"
curl http://localhost:8000/api/health
```

Open http://localhost:8000 and click **Collect news**. To run the PostgreSQL tests against the container database:

```bash
TEST_DATABASE_URL=postgresql+psycopg2://digest:<password>@localhost:5432/news_digest pytest tests/test_postgres_integration.py
```

(Publish port 5432 in `docker-compose.yml` under `db:` first, or run the tests inside the `web` container.)

## Option B: Render (Blueprint)

1. Push this repository to GitHub (already done: `manisha2001-20/ai-news-digest-agent`).
2. Sign in at https://dashboard.render.com, then choose **New → Blueprint** and select the repository.
3. Render reads `render.yaml` and creates:
   - **news-digest-db**: a PostgreSQL database (free plan; Render deletes free databases after a limited period, see their current limits);
   - **ai-news-digest-agent**: a Docker web service, with `DATABASE_URL` wired to the database automatically.
4. In the web service's **Environment** tab, set `OPENAI_API_KEY` (optional; without it, summaries are extractive).
5. Wait for the deploy. The health check path is `/api/health`.
6. Open the `.onrender.com` URL and click **Collect news**.

Notes:
- Free Render web services sleep when idle, so the first request after a pause is slow.
- `postgres://` URLs from Render are normalised automatically to `postgresql+psycopg2://` (`app/config.py`).
- To send real emails, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `EMAIL_FROM`.

## Option C: Local LLM instead of OpenAI

```bash
ollama pull qwen2.5:3b
# .env
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=qwen2.5:3b
```
