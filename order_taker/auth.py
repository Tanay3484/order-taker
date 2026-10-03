"""Accounts: phone normalisation, secret hashing, PINs, login checks (002)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timedelta

from .db import now, transaction

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def normalise_phone(raw: str | None) -> str | None:
    """AUTH-3: one canonical form per number. Indian mobiles become their 10 digits."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 7:
        return None
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        digits = digits[1:]
    return digits


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(secret.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_secret(secret: str, stored: str) -> bool:
    try:
        scheme, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(secret.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_secret("not-a-real-pin")


def new_pin() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def valid_new_pin(pin: str) -> bool:
    return bool(re.fullmatch(r"\d{4,6}", pin or ""))


# ---- users ----

def admin_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone() is not None


def create_admin(conn: sqlite3.Connection, name: str, username: str, password: str) -> int:
    cur = conn.execute(
        "INSERT INTO users (role, username, name, pin_hash, created_at) VALUES ('admin', ?, ?, ?, ?)",
        (username.strip().lower(), name.strip(), hash_secret(password), now()),
    )
    return cur.lastrowid


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def customer_by_phone(conn: sqlite3.Connection, phone: str | None) -> sqlite3.Row | None:
    norm = normalise_phone(phone)
    if not norm:
        return None
    return conn.execute("SELECT * FROM users WHERE role = 'customer' AND phone = ?", (norm,)).fetchone()


def ensure_customer(conn: sqlite3.Connection, name: str, phone: str) -> tuple[sqlite3.Row | None, str | None]:
    """AUTH-4: find or create the customer for this phone. Returns (user, new_pin_or_None)."""
    norm = normalise_phone(phone)
    if not norm:
        return None, None
    existing = customer_by_phone(conn, norm)
    if existing:
        return existing, None
    pin = new_pin()
    cur = conn.execute(
        "INSERT INTO users (role, phone, name, pin_hash, starter_pin, must_change_pin, created_at) "
        "VALUES ('customer', ?, ?, ?, ?, 1, ?)",
        (norm, name.strip(), hash_secret(pin), pin, now()),
    )
    return get_user(conn, cur.lastrowid), pin


def reset_pin(conn: sqlite3.Connection, user_id: int) -> str:
    """AUTH-8: new starter PIN; customer must change it on next login."""
    pin = new_pin()
    conn.execute(
        "UPDATE users SET pin_hash = ?, starter_pin = ?, must_change_pin = 1, failed_attempts = 0, locked_until = NULL "
        "WHERE id = ? AND role = 'customer'",
        (hash_secret(pin), pin, user_id),
    )
    return pin


def change_pin(conn: sqlite3.Connection, user_id: int, pin: str) -> None:
    """The customer's own PIN is only ever stored hashed; the starter PIN is erased (AUTH-13)."""
    conn.execute("UPDATE users SET pin_hash = ?, starter_pin = NULL, must_change_pin = 0 WHERE id = ?",
                 (hash_secret(pin), user_id))


class LoginError(Exception):
    """Carries a plain-English message safe to show (AUTH-12)."""


BAD_CUSTOMER = "That phone number and PIN don't match."
BAD_ADMIN = "That username and password don't match."
LOCKED = "Too many tries. Please wait 15 minutes or ask the shop to reset your PIN."


def login(conn: sqlite3.Connection, kind: str, ident: str, secret: str, at: datetime | None = None) -> sqlite3.Row:
    """Check credentials with lockout (AUTH-7). Raises LoginError with a safe message."""
    at = at or datetime.now()
    if kind == "customer":
        user = customer_by_phone(conn, ident)
        bad = BAD_CUSTOMER
    else:
        user = conn.execute(
            "SELECT * FROM users WHERE role = 'admin' AND username = ?", ((ident or "").strip().lower(),)
        ).fetchone()
        bad = BAD_ADMIN
    if user is None:
        verify_secret(secret or "", _DUMMY_HASH)  # same work either way, so timing reveals nothing
        raise LoginError(bad)
    if user["locked_until"] and datetime.fromisoformat(user["locked_until"]) > at:
        raise LoginError(LOCKED)
    if not verify_secret(secret or "", user["pin_hash"]):
        with transaction(conn):
            attempts = user["failed_attempts"] + 1
            locked = (at + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds") if attempts >= MAX_ATTEMPTS else None
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                (0 if locked else attempts, locked, user["id"]),
            )
        raise LoginError(LOCKED if locked else bad)
    conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user["id"],))
    return get_user(conn, user["id"])
