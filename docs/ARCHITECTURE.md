# Architecture — Personalized AI News Digest Agent

## Overview

```
            ┌──────────────┐    ┌───────────────┐
 RSS feeds ─▶ RSS Collector ├───▶  Extractor     │  (optional full-page text)
            └──────┬───────┘    └───────┬───────┘
                   ▼                    ▼
            ┌──────────────────────────────────┐
            │   PostgreSQL / SQLite (SQLAlchemy) │  feeds · articles · profiles · feedback · digests · runs
            └──────┬───────────────────────────┘
                   ▼
   ┌───────────────────┐   ┌──────────────────┐   ┌────────────────────────┐   ┌──────────────┐
   │ 1 SummarizerAgent │──▶│ 2 RelevanceAgent │──▶│ 3 PersonalizationAgent │──▶│ 4 EmailAgent │──▶ SMTP / preview
   │ OpenAI | TF-IDF   │   │ TF-IDF + keywords│   │ feedback weights,      │   │ Jinja2 HTML  │
   └───────────────────┘   └──────────────────┘   │ recency, diversity     │   └──────────────┘
                                                  └────────────────────────┘
                   ▲
            FastAPI (HTML dashboard + JSON API)
```

`NewsDigestPipeline` (`app/pipeline.py`) is the orchestrator. Each agent is a small class with one job. Agents exchange plain `ArticleView` dataclasses rather than ORM objects, so they can be unit-tested without a database.

## Agents

### 1. SummarizerAgent
- **LLM path:** OpenAI Chat Completions with a system prompt that limits the summary to facts in the text and says to treat article text as data.
- **Fallback path:** splits the text into sentences, builds a TF-IDF matrix, scores each sentence against the document centroid plus the title (with a slight bias toward early sentences, since news puts key facts first), and keeps the top 3 in their original order.
- `LLMClient.complete()` returns `None` on any error, so a failed API call falls back to extractive mode instead of breaking the run.

### 2. RelevanceAgent
`relevance = 0.7 · cosine(TF-IDF(article), TF-IDF(interests)) / max + 0.3 · keyword overlap`

The title is counted twice to give it more weight. With no interests set, every article gets 0.5.

### 3. PersonalizationAgent
- **Learning:** feedback of +1 or -1 updates `category_weights[cat] += 0.2·v` and the top keywords by `0.1·v`. Weights are clipped to [-1, 1].
- **Ranking:** `score = 0.55·relevance + 0.25·(preference+1)/2 + 0.20·recency`, where `recency = 2^(−age/36h)`.
- **Diversity:** at most 3 articles per source, and titles with Jaccard similarity above 0.6 are dropped.
- Disliked articles are excluded from the feed.

### 4. EmailAgent
Renders `templates/email_digest.html` (table layout that works in email clients). The intro line comes from the LLM when available, otherwise from a template. Sends multipart (text + HTML) via SMTP with STARTTLS. Delivery status is stored as `preview`, `sent` or `failed`, with the error message when it fails.

## Data model

| Table | Purpose |
|---|---|
| `feeds` | Feed URL, category, active flag, last fetch time and last error |
| `articles` | Title, link (unique), source, category, content, keywords, AI summary and the method used |
| `user_profiles` | Interests, learned category and keyword weights, digest size |
| `feedback` | (user, article, ±1) |
| `digests` | Rendered HTML, article ids, per-article scores, delivery status |
| `pipeline_runs` | Statistics and log for each collection run |

## Error handling

| Failure | Behaviour |
|---|---|
| Feed download or parse error | Stored on the feed and logged in the run; other feeds continue |
| Article page fetch fails | Falls back to the RSS description |
| OpenAI error or missing key | Falls back to extractive summary and template intro |
| SMTP error | Digest stored with status `failed` and the error message |
| Unknown user or article, or invalid feedback | HTTP 404 / 422 |
| Duplicate profile email | Form error message |
| DB transaction error | Session rolled back (`Database.session()` context manager) |

## Configuration
All settings come from environment variables (`app/config.py`, `.env.example`). `postgres://` URLs from Render or Heroku are normalised to `postgresql+psycopg2://`.

## Design decisions
- **TF-IDF instead of embeddings** for relevance: CPU-only, no model download, and good enough for keyword-rich news headlines.
- **SQLite fallback** so the project runs and its tests pass with no infrastructure. PostgreSQL is the target for Docker and Render.
- **Server-rendered UI** (Jinja2 + one small JS function) keeps the frontend simple and fast. The JSON API supports other clients.
