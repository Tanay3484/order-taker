"""FastAPI app factory (001)."""

from __future__ import annotations

import os
import secrets
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .. import db
from .. import orders as orders_mod
from ..agents.ollama import OllamaClient
from ..config import Settings, get_settings
from . import deps, net, routes_admin, routes_auth, routes_customer

HERE = Path(__file__).parent


def _secret_key(settings: Settings) -> str:
    """AUTH-11: generated on first start, kept next to the database."""
    path = Path(settings.data_dir) / "secret.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def _pretty_date(value: str) -> str:
    d = orders_mod.parse_date(value)
    if d is None:
        return value or "No date"
    today = date.today()
    if d == today:
        return "Today"
    if (d - today).days == 1:
        return "Tomorrow"
    return d.strftime("%a %d %b").replace(" 0", " ")


def wa_link(phone: str, text: str) -> str:
    digits = "".join(c for c in phone or "" if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return f"https://wa.me/{digits}?text={quote(text)}"


def create_app(settings: Settings | None = None, client=None) -> FastAPI:
    settings = settings or get_settings()
    conn = db.connect(settings.db_path)
    db.migrate(conn)  # PLT-3, PLT-4
    conn.close()

    app = FastAPI(title="Order Taker", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.ollama = client or OllamaClient(settings.ollama_url, settings.parallel)
    app.state.public_url = os.getenv("ORDER_PUBLIC_URL") or f"http://{net.lan_ip()}:{settings.port}"

    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.filters.update(
        items=orders_mod.items_text, qty=orders_mod.fmt_qty, nice_date=_pretty_date,
        admin_label=lambda s: orders_mod.ADMIN_LABEL[s],
    )
    templates.env.globals.update(wa_link=wa_link, FLOW=orders_mod.FLOW, customer_label=orders_mod.customer_label,
                                 NEXT_ACTION=orders_mod.NEXT_ACTION)
    app.state.templates = templates

    app.add_middleware(SessionMiddleware, secret_key=_secret_key(settings), session_cookie="ot_session",
                       max_age=deps.CUSTOMER_SESSION_SECONDS, same_site="lax", https_only=False)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.include_router(routes_auth.router)
    app.include_router(routes_admin.router)
    app.include_router(routes_customer.router)

    @app.exception_handler(deps.LoginRequired)
    async def _login(request: Request, exc):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(deps.PinChangeRequired)
    async def _pin(request: Request, exc):
        return RedirectResponse("/change-pin", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) and exc.status_code != 404 else "We couldn't find that page."
        html = templates.get_template("error.html").render(message=message)
        return HTMLResponse(html, status_code=exc.status_code)

    return app
