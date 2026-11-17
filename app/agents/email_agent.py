"""EmailAgent: renders the personalised digest as HTML and (optionally) sends it via SMTP."""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.personalization import RankedArticle
from app.config import Settings
from app.llm import LLMClient

log = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"


@dataclass
class EmailItem:
    title: str
    link: str
    source: str
    category: str
    summary: str
    score: float


@dataclass
class RenderedDigest:
    subject: str
    html: str
    text: str


class EmailAgent:
    name = "email"

    def __init__(self, settings: Settings, llm: LLMClient | None = None):
        self.settings = settings
        self.llm = llm
        self.env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))

    def _intro(self, user_name: str, items: list[EmailItem]) -> str:
        if self.llm is not None and self.llm.available and items:
            headlines = "\n".join(f"- {i.title}" for i in items[:8])
            out = self.llm.complete(
                "You write a friendly two-sentence intro for a personalised news email. Mention only the given headlines.",
                f"Reader: {user_name}\nHeadlines:\n{headlines}",
                max_tokens=90,
            )
            if out:
                return out
        cats = sorted({i.category for i in items})
        return f"Hi {user_name}, here are {len(items)} stories picked for you" + (f" across {', '.join(cats)}." if cats else ".")

    def render(self, user_name: str, items: list[EmailItem], now: datetime | None = None) -> RenderedDigest:
        now = now or datetime.now()
        subject = f"Your AI News Digest — {now:%d %b %Y}"
        intro = self._intro(user_name, items)
        html = self.env.get_template("email_digest.html").render(subject=subject, intro=intro, items=items, date=now)
        text = intro + "\n\n" + "\n\n".join(f"{i.title}\n{i.summary}\n{i.link}" for i in items)
        return RenderedDigest(subject, html, text)

    def send(self, to_address: str, digest: RenderedDigest) -> tuple[bool, str | None]:
        """Send via SMTP if configured. Returns (sent, error). Without SMTP the digest stays a preview."""
        if not self.settings.smtp_enabled:
            return False, None
        msg = MIMEMultipart("alternative")
        msg["Subject"] = digest.subject
        msg["From"] = self.settings.email_from
        msg["To"] = to_address
        msg.attach(MIMEText(digest.text, "plain", "utf-8"))
        msg.attach(MIMEText(digest.html, "html", "utf-8"))
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
                smtp.starttls()
                smtp.login(self.settings.smtp_user, self.settings.smtp_password)
                smtp.send_message(msg)
            return True, None
        except (smtplib.SMTPException, OSError) as exc:
            log.error("Sending digest failed: %s", exc)
            return False, str(exc)


def to_email_items(ranked: list[RankedArticle], lookup: dict[int, dict]) -> list[EmailItem]:
    items = []
    for r in ranked:
        meta = lookup[r.article.id]
        items.append(EmailItem(meta["title"], meta["link"], meta["source"], meta["category"], meta["summary"], r.score))
    return items
