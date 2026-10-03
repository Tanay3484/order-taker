"""Async Ollama client with schema-constrained output, one retry, and a shared
concurrency limit (INT-5, INT-12)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class HelperDown(Exception):
    """Ollama isn't reachable."""


class BadOutput(Exception):
    """The model's answer didn't fit the schema, even after a retry."""


def strict_schema(schema: type[BaseModel]) -> dict:
    """JSON schema with every property required. With structured output, models tend to
    leave out anything optional (units, kind…), so ask for every field explicitly."""
    js = schema.model_json_schema()

    def tighten(node: dict) -> None:
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"])
        for value in node.get("$defs", {}).values():
            tighten(value)

    tighten(js)
    return js


class OllamaClient:
    def __init__(self, base_url: str, parallel: int = 3, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.limit = asyncio.Semaphore(parallel)
        self.timeout = timeout

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as http:
                r = await http.get(f"{self.base_url}/api/tags")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def has_model(self, name: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                r = await http.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise HelperDown() from e
        names = {m.get("name", "") for m in r.json().get("models", [])}
        return name in names or f"{name}:latest" in names

    async def structured(self, model: str, system: str, user: str, schema: type[T], num_predict: int | None = None) -> T:
        """Call the model with a JSON schema; retry once if the answer doesn't validate."""
        options = {"temperature": 0}
        if num_predict:
            options["num_predict"] = num_predict
        payload = {
            "model": model, "stream": False, "keep_alive": "30m", "options": options,
            "format": strict_schema(schema),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        last: Exception | None = None
        for _ in range(2):
            async with self.limit:  # INT-5: never more than ORDER_PARALLEL calls at once
                try:
                    content = await self._chat(payload)
                except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                    raise HelperDown() from e
                except (httpx.HTTPError, KeyError, ValueError) as e:
                    last = e
                    continue
            try:
                return schema.model_validate(json.loads(content))
            except (ValueError, ValidationError) as e:
                log.warning("model %s gave unusable output: %s", model, e)
                last = e
        raise BadOutput(str(last))

    async def _chat(self, payload: dict) -> str:
        """One raw call; returns the message content. Tests replace this."""
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.post(f"{self.base_url}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]
