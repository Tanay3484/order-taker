"""All settings come from env vars so models and paths can be swapped without
touching code (PLT-5)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    model: str = field(default_factory=lambda: os.getenv("ORDER_MODEL", "qwen2.5:7b"))
    sorter_model: str = field(default_factory=lambda: os.getenv("ORDER_SORTER_MODEL", "qwen2.5:3b"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parallel: int = field(default_factory=lambda: max(1, int(os.getenv("ORDER_PARALLEL", "3"))))
    port: int = field(default_factory=lambda: int(os.getenv("ORDER_PORT", "8000")))
    db_path: str = field(default_factory=lambda: os.getenv("ORDER_DB", os.path.join("data", "order_taker.db")))
    # Hosted demo (006). All off by default, so a laptop install is unchanged.
    admin_username: str = field(default_factory=lambda: os.getenv("ORDER_ADMIN_USERNAME", "").strip())
    admin_password: str = field(default_factory=lambda: os.getenv("ORDER_ADMIN_PASSWORD", ""))
    shop_name: str = field(default_factory=lambda: os.getenv("ORDER_SHOP_NAME", "").strip())
    shop_whatsapp: str = field(default_factory=lambda: os.getenv("ORDER_SHOP_WHATSAPP", "").strip())
    secure_cookies: bool = field(default_factory=lambda: _flag("ORDER_SECURE_COOKIES"))
    cookie_samesite: str = field(default_factory=lambda: os.getenv("ORDER_COOKIE_SAMESITE", "lax").strip().lower())
    demo: bool = field(default_factory=lambda: _flag("ORDER_DEMO"))
    max_chat_chars: int = field(default_factory=lambda: int(os.getenv("ORDER_MAX_CHAT_CHARS", "50000")))

    @property
    def env_admin(self) -> bool:
        return bool(self.admin_username and self.admin_password)

    @property
    def samesite(self) -> str:
        """HOST-2: browsers reject SameSite=None without Secure, so fall back to lax."""
        if self.cookie_samesite == "none" and not self.secure_cookies:
            return "lax"
        return self.cookie_samesite if self.cookie_samesite in ("lax", "strict", "none") else "lax"

    @property
    def data_dir(self) -> str:
        return os.path.dirname(os.path.abspath(self.db_path))


def get_settings() -> Settings:
    return Settings()
