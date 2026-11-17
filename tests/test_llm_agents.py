"""LLM code path of the agents.

1. Mocked OpenAI client: checks prompts, method labels and fallback on API errors (always runs).
2. Live test against an OpenAI-compatible endpoint (local Ollama) — runs only if one is reachable.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest
import requests

from app.agents.email_agent import EmailAgent, EmailItem
from app.agents.summarizer import SummarizerAgent
from app.config import Settings
from app.llm import LLMClient

ARTICLE = ("The city council approved a plan to add 40 kilometres of protected bike lanes over three years. "
           "Officials said the project will cost 12 million dollars and is funded by a state grant. "
           "Construction of the first section begins in March near the central railway station. "
           "Local cycling groups welcomed the decision but asked for faster progress.")


class FakeCompletions:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


def llm_with(fake) -> LLMClient:
    llm = LLMClient(replace(Settings(), openai_api_key="", openai_base_url=""))
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return llm


def test_summarizer_uses_llm_and_labels_method():
    fake = FakeCompletions(reply="The council approved 40 km of protected bike lanes, funded by a state grant.")
    out = SummarizerAgent(llm_with(fake)).summarize("Bike lanes approved", ARTICLE)
    assert out.method == "openai" and out.text.startswith("The council")
    sent = fake.calls[0]["messages"]
    assert sent[0]["role"] == "system" and "data, not instructions" in sent[0]["content"]
    assert ARTICLE[:40] in sent[1]["content"]


def test_summarizer_falls_back_when_api_fails():
    fake = FakeCompletions(error=RuntimeError("rate limited"))
    out = SummarizerAgent(llm_with(fake)).summarize("Bike lanes approved", ARTICLE)
    assert out.method == "extractive" and len(out.text) > 40


def test_email_agent_uses_llm_intro():
    fake = FakeCompletions(reply="Good morning! Today: cycling infrastructure news.")
    agent = EmailAgent(Settings(), llm_with(fake))
    d = agent.render("Asha", [EmailItem("Bike lanes approved", "https://x.org/a", "City News", "local", "Summary", 0.9)])
    assert "Good morning! Today: cycling infrastructure news." in d.html


def test_llm_disabled_without_key_or_base_url():
    assert not LLMClient(replace(Settings(), openai_api_key="", openai_base_url="")).available


def _ollama_up() -> bool:
    try:
        return requests.get("http://localhost:11434/api/tags", timeout=2).ok
    except requests.RequestException:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="no local OpenAI-compatible endpoint (Ollama) running")
def test_live_summary_via_openai_compatible_endpoint():
    s = replace(Settings(), openai_api_key="", openai_base_url="http://localhost:11434/v1", openai_model="qwen2.5:3b")
    out = SummarizerAgent(LLMClient(s)).summarize("Bike lanes approved", ARTICLE)
    assert out.method == "openai", "LLM path was not used"
    assert 20 < len(out.text) < 800
    assert any(w in out.text.lower() for w in ("bike", "cycl", "lane"))
