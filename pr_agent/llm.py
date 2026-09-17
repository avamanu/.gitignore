import json
import os
import re

import anthropic

from .config import MODEL

_client = None


def client():
    global _client
    if _client is None:
        if not (os.getenv("ANTHROPIC_API_KEY") or "").strip():
            raise SystemExit(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and paste your key "
                "from console.anthropic.com. See README, section 1."
            )
        _client = anthropic.Anthropic()
    return _client


def ask(system, user, max_tokens=1500, web_search=False, max_searches=5):
    """Single request, with optional server-side web search. Returns list of text blocks."""
    extra = {}
    if web_search:
        extra["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    messages = [{"role": "user", "content": user}]
    resp = None
    for _ in range(4):  # web search can pause long turns; continue them
        resp = client().messages.create(
            model=MODEL, max_tokens=max_tokens, system=system, messages=messages, **extra
        )
        if resp.stop_reason == "pause_turn":
            messages = messages + [{"role": "assistant", "content": resp.content}]
            continue
        break
    return [b.text for b in resp.content if getattr(b, "type", "") == "text"]


def parse_json(blocks):
    """Find a JSON object in the model output, preferring the last text block."""
    candidates = list(reversed(blocks)) + ["\n".join(blocks)]
    for text in candidates:
        text = re.sub(r"```(?:json)?", "", text)
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("Model did not return valid JSON:\n" + "\n".join(blocks)[:800])
