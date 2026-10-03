"""All settings come from env vars so models and paths can be swapped without
touching code (PLT-5)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    model: str = field(default_factory=lambda: os.getenv("ORDER_MODEL", "qwen2.5:7b"))
    sorter_model: str = field(default_factory=lambda: os.getenv("ORDER_SORTER_MODEL", "qwen2.5:3b"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parallel: int = field(default_factory=lambda: max(1, int(os.getenv("ORDER_PARALLEL", "3"))))
    port: int = field(default_factory=lambda: int(os.getenv("ORDER_PORT", "8000")))
    db_path: str = field(default_factory=lambda: os.getenv("ORDER_DB", os.path.join("data", "order_taker.db")))

    @property
    def data_dir(self) -> str:
        return os.path.dirname(os.path.abspath(self.db_path))


def get_settings() -> Settings:
    return Settings()
