"""Startup steps for a hosted demo (006): admin from env, demo data."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import auth, db
from . import orders as om
from .config import Settings
from .models import Order, OrderItem

# HOST-6: shown on the login page in demo mode
DEMO_CUSTOMER = {"name": "Kavya", "phone": "9811122233", "pin": "2468"}


def apply(conn: sqlite3.Connection, settings: Settings) -> None:
    if settings.env_admin:
        ensure_env_admin(conn, settings)
    if settings.demo and conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
        seed_demo(conn)


def ensure_env_admin(conn: sqlite3.Connection, settings: Settings) -> None:
    """HOST-1: create the admin from env, or bring its password in line with the env."""
    with db.transaction(conn, immediate=True):
        username = settings.admin_username.lower()
        row = conn.execute("SELECT * FROM users WHERE role = 'admin'").fetchone()
        if row is None:
            auth.create_admin(conn, settings.shop_name or "Shop owner", username, settings.admin_password)
        else:
            conn.execute("UPDATE users SET username = ?, pin_hash = ?, failed_attempts = 0, locked_until = NULL "
                         "WHERE id = ?", (username, auth.hash_secret(settings.admin_password), row["id"]))
        if settings.shop_name:
            db.set_setting(conn, "shop_name", settings.shop_name)
        phone = auth.normalise_phone(settings.shop_whatsapp)
        if phone:
            db.set_setting(conn, "shop_whatsapp", phone)
        if not db.get_setting(conn, "shop_name"):
            db.set_setting(conn, "shop_name", "Order Taker demo")


def _order(conn, name: str, phone: str, items, day: date, status: str, address: str = "", notes: str = "",
           time_: str = "") -> int:
    user, _ = auth.ensure_customer(conn, name, phone)
    order = Order(customer=name, phone=phone, items=[OrderItem(name=n, quantity=q, unit=u) for n, q, u in items],
                  delivery_date=day.isoformat(), delivery_time=time_, address=address, notes=notes)
    oid = om.create_order(conn, order, user["id"], None)
    if status == "cancelled":
        om.cancel(conn, oid, None)
    else:
        for _ in om.FLOW[1: om.FLOW.index(status) + 1]:
            om.advance(conn, oid, None)
    return oid


def seed_demo(conn: sqlite3.Connection, today: date | None = None) -> None:
    """HOST-5: a shop mid-week. Nobody here is a sender in samples/sample_chat.txt."""
    today = today or date.today()
    tomorrow, later = today + timedelta(days=1), today + timedelta(days=3)
    with db.transaction(conn, immediate=True):
        k = DEMO_CUSTOMER
        _order(conn, k["name"], k["phone"], [("pineapple cake", 1, "kg")], today, "ready",
               address="22 MG Road, Jayanagar", notes="Less sugar, it's for my dadi", time_="5 pm")
        _order(conn, k["name"], k["phone"], [("coconut ladoo", 24, "pcs")], later, "confirmed", notes="pickup",
               time_="evening")
        kavya = auth.customer_by_phone(conn, k["phone"])
        auth.change_pin(conn, kavya["id"], k["pin"])  # a customer who has already chosen their PIN

        _order(conn, "Arjun", "9900044455", [("red velvet cake", 1.5, "kg")], tomorrow, "preparing",
               address="7 Lake View Layout", notes="Write 'Happy Anniversary'", time_="7 pm")  # starter PIN unused
        _order(conn, "Divya", "9988776655", [("brownies", 2, "box"), ("cupcakes", 6, "pcs")], today, "received",
               notes="pickup", time_="11 am")
        _order(conn, "Farhan", "9876501234", [("cheesecake", 1, "kg")], today - timedelta(days=1), "delivered",
               address="Flat 3B, Palm Grove")
