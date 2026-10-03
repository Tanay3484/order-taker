"""The original single-call extraction: the whole chat in one request.
Kept only as the baseline for scripts/bench_intake.py (INT-20); the app uses
the multi-agent pipeline in order_taker/agents/."""

from __future__ import annotations

import json
from datetime import date

import httpx

from .config import get_settings
from .models import Order, OrderBatch

SYSTEM_PROMPT = """You extract food/business orders from WhatsApp messages for a small home business.
Rules:
- One entry per customer order. Ignore greetings, thanks, and chit-chat.
- If a later message changes or cancels an earlier one from the same person, keep only the final version.
- Resolve relative dates ("tomorrow", "Sunday") using today's date: {today}.
- Never invent details. Leave a field empty if it isn't in the messages.
- Messages may mix English, Hindi, Kannada or Tamil written in English letters. Translate item names to plain English.
Return JSON only."""


def extract_orders(chat_text: str, today: date | None = None, model: str | None = None,
                   ollama_url: str | None = None) -> list[Order]:
    """Send the whole chat to the local model in one call and return validated orders."""
    settings = get_settings()
    today = today or date.today()
    payload = {
        "model": model or settings.model,
        "stream": False,
        "format": OrderBatch.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(today=today.isoformat())},
            {"role": "user", "content": chat_text},
        ],
    }
    resp = httpx.post(f"{ollama_url or settings.ollama_url}/api/chat", json=payload, timeout=300)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return OrderBatch.model_validate(json.loads(content)).orders
