"""Thin wrapper around the OpenAI API. Returns None (never raises) so callers can fall back."""
from __future__ import annotations

import logging

from app.config import Settings

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        if settings.llm_enabled:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.openai_api_key, timeout=30)
            except Exception as exc:  # pragma: no cover - import/config problems
                log.warning("OpenAI client unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(self, system: str, user: str, max_tokens: int = 220) -> str | None:
        if not self._client:
            return None
        try:
            resp = self._client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text or None
        except Exception as exc:
            log.warning("OpenAI request failed, using fallback: %s", exc)
            return None
