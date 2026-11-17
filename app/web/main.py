"""FastAPI application: HTML dashboard + JSON API."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import Settings, settings as default_settings
from app.database import Database
from app.models import Article, Digest, Feed, PipelineRun, UserProfile
from app.pipeline import NewsDigestPipeline, NotFoundError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
WEB_DIR = Path(__file__).resolve().parent


class FeedbackIn(BaseModel):
    user_id: int
    article_id: int
    value: int = Field(..., description="+1 like, -1 dislike")


def create_app(settings: Settings = default_settings, seed: bool = True) -> FastAPI:
    db = Database(settings.database_url)
    db.create_all()
    pipeline = NewsDigestPipeline(db, settings)
    if seed:
        pipeline.seed_defaults()

    app = FastAPI(title="AI News Digest Agent", version="1.0.0")
    app.state.db, app.state.pipeline = db, pipeline
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=WEB_DIR / "templates")

    def current_user_id(request: Request) -> int:
        uid = request.query_params.get("user") or request.cookies.get("user_id")
        if uid and uid.isdigit():
            return int(uid)
        with db.session() as s:
            first = s.scalar(select(UserProfile.id).order_by(UserProfile.id))
        if first is None:
            raise HTTPException(404, "No user profile exists yet. Create one on the Profile page.")
        return first

    def page(request: Request, name: str, **ctx):
        with db.session() as s:
            users = s.scalars(select(UserProfile).order_by(UserProfile.id)).all()
        ctx.update(request=request, users=users, llm_enabled=settings.llm_enabled, smtp_enabled=settings.smtp_enabled,
                   db_kind="PostgreSQL" if settings.database_url.startswith("postgresql") else "SQLite")
        return templates.TemplateResponse(request, name, ctx)

    # ------------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        uid = current_user_id(request)
        try:
            user, ranked = pipeline.personalised_feed(uid, k=24)
        except NotFoundError:
            return RedirectResponse("/profile", status_code=303)
        with db.session() as s:
            stats = {
                "articles": s.scalar(select(func.count(Article.id))) or 0,
                "feeds": s.scalar(select(func.count(Feed.id)).where(Feed.active.is_(True))) or 0,
                "digests": s.scalar(select(func.count(Digest.id))) or 0,
                "last_run": s.scalars(select(PipelineRun).order_by(PipelineRun.id.desc())).first(),
            }
            cats = s.execute(select(Article.category, func.count(Article.id)).group_by(Article.category)).all()
        resp = page(request, "dashboard.html", user=user, ranked=ranked, stats=stats,
                    categories=[{"name": c, "count": n} for c, n in cats], active="dashboard")
        resp.set_cookie("user_id", str(uid), samesite="lax")
        return resp

    @app.post("/run")
    def run_pipeline():
        pipeline.run()
        return RedirectResponse("/", status_code=303)

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request):
        user = None
        if not request.query_params.get("new"):
            with db.session() as s:
                uid = request.cookies.get("user_id")
                user = s.get(UserProfile, int(uid)) if uid and uid.isdigit() else s.scalars(select(UserProfile)).first()
        return page(request, "profile.html", user=user, active="profile", error=None)

    @app.post("/profile")
    def save_profile(request: Request, name: str = Form(...), email: str = Form(...), interests: str = Form(""),
                     digest_size: int = Form(8), user_id: str = Form("")):
        name, email = name.strip(), email.strip().lower()
        if not name or "@" not in email:
            return page(request, "profile.html", user=None, active="profile", error="Please enter a name and a valid email.")
        topics = [t.strip() for t in interests.replace("\n", ",").split(",") if t.strip()]
        try:
            with db.session() as s:
                user = s.get(UserProfile, int(user_id)) if user_id.isdigit() else None
                if user is None:
                    user = UserProfile(name=name, email=email)
                    s.add(user)
                user.name, user.email, user.interests = name, email, topics
                user.digest_size = max(3, min(20, digest_size))
                s.flush()
                uid = user.id
        except IntegrityError:
            return page(request, "profile.html", user=None, active="profile", error="That email is already used by another profile.")
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("user_id", str(uid), samesite="lax")
        return resp

    @app.get("/feeds", response_class=HTMLResponse)
    def feeds_page(request: Request):
        with db.session() as s:
            feeds = s.scalars(select(Feed).order_by(Feed.name)).all()
            runs = s.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(10)).all()
        return page(request, "feeds.html", feeds=feeds, runs=runs, active="feeds", error=None)

    @app.post("/feeds")
    def add_feed(request: Request, name: str = Form(...), url: str = Form(...), category: str = Form("general")):
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            with db.session() as s:
                feeds = s.scalars(select(Feed).order_by(Feed.name)).all()
            return page(request, "feeds.html", feeds=feeds, runs=[], active="feeds", error="Feed URL must start with http:// or https://")
        try:
            with db.session() as s:
                s.add(Feed(name=name.strip()[:200], url=url, category=category.strip().lower() or "general"))
        except IntegrityError:
            pass  # already present
        return RedirectResponse("/feeds", status_code=303)

    @app.post("/feeds/{feed_id}/toggle")
    def toggle_feed(feed_id: int):
        with db.session() as s:
            feed = s.get(Feed, feed_id)
            if feed is None:
                raise HTTPException(404, "Feed not found")
            feed.active = not feed.active
        return RedirectResponse("/feeds", status_code=303)

    @app.get("/digests", response_class=HTMLResponse)
    def digests_page(request: Request):
        with db.session() as s:
            digests = s.scalars(select(Digest).order_by(Digest.id.desc()).limit(30)).all()
            names = {u.id: u.name for u in s.scalars(select(UserProfile)).all()}
        return page(request, "digests.html", digests=digests, names=names, active="digests")

    @app.post("/digests")
    def create_digest(request: Request):
        try:
            d = pipeline.build_digest(current_user_id(request))
        except NotFoundError as exc:
            raise HTTPException(404, str(exc))
        return RedirectResponse(f"/digests/{d.id}", status_code=303)

    @app.get("/digests/{digest_id}", response_class=HTMLResponse)
    def digest_view(request: Request, digest_id: int):
        with db.session() as s:
            d = s.get(Digest, digest_id)
            if d is None:
                raise HTTPException(404, "Digest not found")
        return page(request, "digest_view.html", digest=d, active="digests")

    @app.get("/digests/{digest_id}/raw", response_class=HTMLResponse)
    def digest_raw(digest_id: int):
        with db.session() as s:
            d = s.get(Digest, digest_id)
            if d is None:
                raise HTTPException(404, "Digest not found")
            return HTMLResponse(d.html)

    # -------------------------------------------------------------------- API
    @app.get("/api/health")
    def health():
        with db.session() as s:
            s.execute(select(1))
        return {"status": "ok", "llm": settings.llm_enabled, "smtp": settings.smtp_enabled}

    @app.post("/api/run")
    def api_run():
        r = pipeline.run()
        return {"feeds_ok": r.feeds_ok, "feeds_failed": r.feeds_failed, "new_articles": r.new_articles,
                "summarised": r.summarised, "duration_s": r.duration_s, "log": r.log}

    @app.get("/api/users/{user_id}/feed")
    def api_feed(user_id: int, k: int = 10):
        try:
            _, ranked = pipeline.personalised_feed(user_id, k=max(1, min(k, 50)))
        except NotFoundError as exc:
            raise HTTPException(404, str(exc))
        return [{"id": a.id, "title": a.title, "link": a.link, "source": a.source, "category": a.category,
                 "summary": a.ai_summary, "summary_method": a.summary_method, "score": r.score,
                 "relevance": r.relevance, "preference": round(r.preference, 4), "recency": round(r.recency, 4)}
                for r, a in ranked]

    @app.post("/api/feedback")
    def api_feedback(fb: FeedbackIn):
        if fb.value not in (1, -1):
            raise HTTPException(422, "value must be +1 or -1")
        try:
            pipeline.record_feedback(fb.user_id, fb.article_id, fb.value)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc))
        return {"ok": True}

    @app.post("/api/users/{user_id}/digest")
    def api_digest(user_id: int, send: bool = False):
        try:
            d = pipeline.build_digest(user_id, send=send)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc))
        return {"id": d.id, "subject": d.subject, "status": d.status, "articles": len(d.article_ids), "error": d.error}

    return app


app = create_app()
