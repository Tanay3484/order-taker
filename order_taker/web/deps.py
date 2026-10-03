"""Request helpers: DB connection, current user, role guards, CSRF, rendering (AUTH-10, AUTH-11)."""

from __future__ import annotations

import hmac
import secrets
import sqlite3
import time
from datetime import date

from fastapi import Depends, HTTPException, Request

from .. import auth, bootstrap, db, tours
from .. import orders as orders_mod

ADMIN_SESSION_SECONDS = 12 * 3600
CUSTOMER_SESSION_SECONDS = 30 * 24 * 3600


class LoginRequired(Exception):
    pass


class PinChangeRequired(Exception):
    pass


def get_conn(request: Request):
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def sign_in(request: Request, user: sqlite3.Row) -> None:
    request.session.clear()
    life = ADMIN_SESSION_SECONDS if user["role"] == "admin" else CUSTOMER_SESSION_SECONDS
    request.session.update(uid=user["id"], role=user["role"], exp=int(time.time()) + life,
                           csrf=secrets.token_urlsafe(24))


def current_user(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> sqlite3.Row | None:
    uid, exp = request.session.get("uid"), request.session.get("exp", 0)
    if not uid or exp < time.time():
        return None
    user = auth.get_user(conn, uid)
    if user is None or user["role"] != request.session.get("role"):
        return None
    return user


def require_admin(user=Depends(current_user)) -> sqlite3.Row:
    if user is None:
        raise LoginRequired()
    if user["role"] != "admin":
        raise HTTPException(403, "This page is only for the shop owner.")
    return user


def require_customer_any(user=Depends(current_user)) -> sqlite3.Row:
    """Customer, even one who still has to change their PIN (for /change-pin itself)."""
    if user is None:
        raise LoginRequired()
    if user["role"] != "customer":
        raise HTTPException(403, "This page is only for customers.")
    return user


def require_customer(user=Depends(require_customer_any)) -> sqlite3.Row:
    if user["must_change_pin"]:
        raise PinChangeRequired()  # AUTH-6
    return user


def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = request.session["csrf"] = secrets.token_urlsafe(24)
    return tok


async def check_csrf(request: Request) -> None:
    """Every state-changing POST carries the session's token in a hidden field."""
    form = await request.form()
    sent = str(form.get("csrf", ""))
    if not sent or not hmac.compare_digest(sent, request.session.get("csrf", "")):
        raise HTTPException(400, "This form has expired. Please go back, refresh the page and try again.")


def demo_logins(settings) -> dict:
    """HOST-6: the logins shown on the login page in demo mode."""
    if not settings.demo:
        return {}
    logins = {"customer": (bootstrap.DEMO_CUSTOMER["phone"], bootstrap.DEMO_CUSTOMER["pin"])}
    if settings.env_admin:
        logins["admin"] = (settings.admin_username, settings.admin_password)
    return logins


def render(request: Request, conn: sqlite3.Connection, template: str, status_code: int = 200, **ctx):
    templates = request.app.state.templates
    user = ctx.pop("user", None)
    base = {
        "user": user,
        "csrf": csrf_token(request),
        "shop_name": db.get_setting(conn, "shop_name", "Order Taker"),
        "changes_badge": orders_mod.changes_badge(conn) if user is not None and user["role"] == "admin" else 0,
        "today": date.today().isoformat(),
        "demo": request.app.state.settings.demo,
        "demo_logins": demo_logins(request.app.state.settings),
    }
    base["tour"] = tours.for_page(template, {**base, **ctx}, request.app.state.settings.demo)  # 007
    return templates.TemplateResponse(request, template, {**base, **ctx}, status_code=status_code)
