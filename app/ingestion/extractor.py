"""Extracts readable article text from a web page, falling back to the RSS summary."""
from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

from app.ingestion.rss_collector import USER_AGENT
from app.text_utils import clean_html

log = logging.getLogger(__name__)

_BOILERPLATE_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "noscript", "figure")


def extract_text_from_html(page_html: str, min_paragraph_chars: int = 60) -> str:
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup(_BOILERPLATE_TAGS):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [clean_html(p.get_text(" ")) for p in container.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) >= min_paragraph_chars]
    return "\n".join(paragraphs)


def fetch_article_text(url: str, fallback: str, timeout: float = 10) -> str:
    """Download the article page and extract body text. Never raises: returns fallback on any error."""
    if not url.startswith(("http://", "https://")):
        return fallback
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        if "html" not in resp.headers.get("Content-Type", "html"):
            return fallback
        text = extract_text_from_html(resp.text)
        return text if len(text) > len(fallback) else fallback
    except requests.RequestException as exc:
        log.info("Article extraction failed for %s: %s", url, exc)
        return fallback
