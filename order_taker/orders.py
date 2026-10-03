"""Order lifecycle: statuses, applying drafts, customer edits, diffs (005).
All rules live here; route handlers only call these functions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import auth
from .db import now, transaction
from .models import Order, OrderItem

FLOW = ["received", "confirmed", "preparing", "ready", "delivered"]
STATUSES = FLOW + ["cancelled"]
OPEN = ("received", "confirmed", "preparing", "ready")
UNDO_WINDOW = timedelta(minutes=5)

ADMIN_LABEL = {
    "received": "Received", "confirmed": "Confirmed", "preparing": "Preparing",
    "ready": "Ready", "delivered": "Delivered", "cancelled": "Cancelled",
}
NEXT_ACTION = {
    "received": "Confirm order", "confirmed": "Start preparing",
    "preparing": "Mark ready", "ready": "Mark delivered",
}


def customer_label(status: str, has_address: bool) -> str:
    return {
        "received": "We've got your order",
        "confirmed": "Confirmed by the shop",
        "preparing": "Being made",
        "ready": "Ready for delivery" if has_address else "Ready for pickup",
        "delivered": "Delivered. Enjoy!",
        "cancelled": "Cancelled",
    }[status]


class OrderError(Exception):
    """Plain-English message safe to show to the user."""


class NeedsConfirm(OrderError):
    """TRK-2: the order is already being made; the admin must confirm the change."""


# ---------- reading ----------

def get_order(conn: sqlite3.Connection, order_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_items(conn: sqlite3.Connection, order_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()


def to_model(conn: sqlite3.Connection, row: sqlite3.Row) -> Order:
    return Order(
        customer=row["customer_name"], phone=row["phone"],
        items=[OrderItem(name=i["name"], quantity=i["quantity"], unit=i["unit"]) for i in get_items(conn, row["id"])],
        delivery_date=row["delivery_date"], delivery_time=row["delivery_time"],
        address=row["address"], notes=row["notes"],
    )


def open_orders_for(conn: sqlite3.Connection, phone: str | None, name: str) -> list[tuple[int, Order]]:
    """INT-10: a sender's open orders, matched by phone, otherwise by exact name."""
    norm = auth.normalise_phone(phone)
    marks = ",".join("?" * len(OPEN))
    if norm:
        rows = conn.execute(f"SELECT * FROM orders WHERE phone = ? AND status IN ({marks}) ORDER BY id", (norm, *OPEN))
    else:
        rows = conn.execute(
            f"SELECT * FROM orders WHERE lower(customer_name) = lower(?) AND status IN ({marks}) ORDER BY id",
            (name.strip(), *OPEN),
        )
    return [(r["id"], to_model(conn, r)) for r in rows.fetchall()]


def all_open_orders(conn: sqlite3.Connection) -> list[tuple[int, Order]]:
    marks = ",".join("?" * len(OPEN))
    rows = conn.execute(f"SELECT * FROM orders WHERE status IN ({marks})", OPEN).fetchall()
    return [(r["id"], to_model(conn, r)) for r in rows]


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def order_tab(row: sqlite3.Row, today: date) -> str:
    if row["status"] in ("delivered", "cancelled"):
        return "past"
    d = parse_date(row["delivery_date"])
    if d is None:
        return "nodate"
    if d <= today:  # overdue open orders stay in Today so they don't get forgotten
        return "today"
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    return "upcoming"


def orders_in_tab(conn: sqlite3.Connection, tab: str, today: date | None = None) -> list[sqlite3.Row]:
    today = today or date.today()
    rows = conn.execute("SELECT * FROM orders ORDER BY delivery_date, delivery_time, id").fetchall()
    picked = [r for r in rows if order_tab(r, today) == tab]
    if tab == "past":
        picked.reverse()
    return picked


def prep_rows(conn: sqlite3.Connection, day: str) -> list[dict]:
    """TRK-9: total of each item for a day, cancelled orders excluded."""
    rows = conn.execute(
        "SELECT lower(trim(i.name)) AS item, lower(trim(i.unit)) AS unit, SUM(i.quantity) AS total "
        "FROM order_items i JOIN orders o ON o.id = i.order_id "
        "WHERE o.delivery_date = ? AND o.status != 'cancelled' GROUP BY 1, 2 ORDER BY 1, 2",
        (day,),
    ).fetchall()
    return [{"item": r["item"], "unit": r["unit"], "total": fmt_qty(r["total"])} for r in rows]


def customer_orders(conn: sqlite3.Connection, customer_id: int) -> list[sqlite3.Row]:
    """TRK-16 / AUTH-10: the customer filter lives here so a route can't forget it."""
    return conn.execute(
        "SELECT * FROM orders WHERE customer_id = ? ORDER BY delivery_date, delivery_time, id", (customer_id,)
    ).fetchall()


def customer_order(conn: sqlite3.Connection, customer_id: int, order_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM orders WHERE id = ? AND customer_id = ?", (order_id, customer_id)).fetchone()


def last_change_at(conn: sqlite3.Connection, order_id: int) -> str:
    row = conn.execute("SELECT MAX(at) AS at FROM status_history WHERE order_id = ?", (order_id,)).fetchone()
    return row["at"] or ""


def history(conn: sqlite3.Connection, order_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT h.*, u.name AS by_name, u.role AS by_role FROM status_history h "
        "LEFT JOIN users u ON u.id = h.changed_by WHERE order_id = ? ORDER BY h.id",
        (order_id,),
    ).fetchall()


def fmt_qty(q: float) -> str:
    return str(int(q)) if float(q).is_integer() else str(q)


def items_text(items) -> str:
    """'2 box brownies, 1 kg chocolate cake'. Accepts OrderItems or order_items rows."""
    parts = []
    for i in items:
        if not isinstance(i, OrderItem):
            i = OrderItem(name=i["name"], quantity=i["quantity"], unit=i["unit"])
        parts.append(" ".join(p for p in (fmt_qty(i.quantity), i.unit.strip(), i.name.strip()) if p))
    return ", ".join(parts)


# ---------- writing ----------

def _log(conn, order_id: int, status: str, prev: str | None, by: int | None, note: str = "") -> None:
    conn.execute(
        "INSERT INTO status_history (order_id, status, prev_status, note, changed_by, at) VALUES (?, ?, ?, ?, ?, ?)",
        (order_id, status, prev, note, by, now()),
    )


def _write_items(conn, order_id: int, items: list[OrderItem]) -> None:
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    conn.executemany(
        "INSERT INTO order_items (order_id, name, quantity, unit) VALUES (?, ?, ?, ?)",
        [(order_id, i.name.strip(), i.quantity, i.unit.strip()) for i in items],
    )


def create_order(conn, order: Order, customer_id: int | None, by: int | None) -> int:
    with transaction(conn):
        ts = now()
        cur = conn.execute(
            "INSERT INTO orders (customer_id, customer_name, phone, delivery_date, delivery_time, address, notes, "
            "status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'received', ?, ?)",
            (customer_id, order.customer.strip(), auth.normalise_phone(order.phone) or "",
             order.delivery_date.strip(), order.delivery_time.strip(), order.address.strip(), order.notes.strip(), ts, ts),
        )
        _write_items(conn, cur.lastrowid, order.items)
        _log(conn, cur.lastrowid, "received", None, by, "Order accepted")
        return cur.lastrowid


def update_details(conn, order_id: int, order: Order, by: int | None, note: str) -> None:
    """Change contents (not name/phone, not status). Logged in history (TRK-28)."""
    with transaction(conn):
        row = get_order(conn, order_id)
        conn.execute(
            "UPDATE orders SET delivery_date = ?, delivery_time = ?, address = ?, notes = ?, updated_at = ? WHERE id = ?",
            (order.delivery_date.strip(), order.delivery_time.strip(), order.address.strip(), order.notes.strip(),
             now(), order_id),
        )
        _write_items(conn, order_id, order.items)
        _log(conn, order_id, row["status"], None, by, note)


def admin_edit(conn, order_id: int, order: Order, admin_note: str, by: int) -> None:
    with transaction(conn):
        update_details(conn, order_id, order, by, "Edited by the shop")
        conn.execute("UPDATE orders SET customer_name = ?, admin_note = ? WHERE id = ?",
                     (order.customer.strip(), admin_note.strip(), order_id))


def next_status(status: str) -> str | None:
    if status in FLOW and status != FLOW[-1]:
        return FLOW[FLOW.index(status) + 1]
    return None


def can_cancel(status: str) -> bool:
    return status in OPEN


def _set_status(conn, order_id: int, new: str, by: int | None, note: str = "") -> None:
    row = get_order(conn, order_id)
    conn.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (new, now(), order_id))
    _log(conn, order_id, new, row["status"], by, note)


def advance(conn, order_id: int, by: int) -> str:
    """TRK-4: one step forward."""
    with transaction(conn, immediate=True):
        row = get_order(conn, order_id)
        if row is None:
            raise OrderError("That order doesn't exist.")
        nxt = next_status(row["status"])
        if nxt is None:
            raise OrderError("This order can't move any further.")
        _set_status(conn, order_id, nxt, by)
        return nxt


def cancel(conn, order_id: int, by: int | None, note: str = "") -> None:
    with transaction(conn, immediate=True):
        row = get_order(conn, order_id)
        if row is None or not can_cancel(row["status"]):
            raise OrderError("This order can't be cancelled.")
        _set_status(conn, order_id, "cancelled", by, note)


def undo_last(conn, order_id: int, by: int, at: datetime | None = None) -> str:
    """TRK-5: reverse the last status change if it was made in the last 5 minutes."""
    at = at or datetime.now()
    with transaction(conn, immediate=True):
        last = conn.execute(
            "SELECT * FROM status_history WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,)
        ).fetchone()
        if (last is None or last["prev_status"] is None or last["note"] == "Undone"
                or at - datetime.fromisoformat(last["at"]) > UNDO_WINDOW):
            raise OrderError("There's nothing to undo. Changes can only be undone for 5 minutes.")
        _set_status(conn, order_id, last["prev_status"], by, "Undone")
        return last["prev_status"]


def can_undo(conn, order_id: int, at: datetime | None = None) -> bool:
    at = at or datetime.now()
    last = conn.execute("SELECT * FROM status_history WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,)).fetchone()
    return bool(last and last["prev_status"] and last["note"] != "Undone"
                and at - datetime.fromisoformat(last["at"]) <= UNDO_WINDOW)


def link_phone(conn, order_id: int, phone: str) -> str | None:
    """AUTH-5: add a phone to an order later; links/creates the customer. Returns a new PIN if one was made."""
    norm = auth.normalise_phone(phone)
    if not norm:
        raise OrderError(auth.PHONE_RULE)
    with transaction(conn, immediate=True):
        row = get_order(conn, order_id)
        user, pin = auth.ensure_customer(conn, row["customer_name"], norm)
        conn.execute("UPDATE orders SET phone = ?, customer_id = ?, updated_at = ? WHERE id = ?",
                     (norm, user["id"], now(), order_id))
        return pin


# ---------- drafts ----------

@dataclass
class Accepted:
    order_id: int | None
    customer_name: str = ""
    phone: str = ""
    new_pin: str | None = None


def get_draft(conn, draft_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()


def draft_order(draft: sqlite3.Row) -> Order | None:
    data = json.loads(draft["payload_json"] or "{}")
    return Order.model_validate(data) if data else None


def save_draft(conn, *, source: str, action: str, order: Order | None, target_order_id: int | None = None,
               run_id: int | None = None, requested_by: int | None = None, sender: str = "",
               flags: list[str] | None = None, raw_text: str = "", state: str = "pending",
               before: Order | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO drafts (source, run_id, requested_by, sender, action, target_order_id, payload_json, before_json, "
        "flags_json, raw_text, state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source, run_id, requested_by, sender, action, target_order_id,
         order.model_dump_json() if order else "{}", before.model_dump_json() if before else None,
         json.dumps(flags or []), raw_text, state, now()),
    )
    return cur.lastrowid


def _finish_draft(conn, draft_id: int, state: str, reason: str = "") -> None:
    conn.execute("UPDATE drafts SET state = ?, decline_reason = ?, decided_at = ? WHERE id = ?",
                 (state, reason, now(), draft_id))


def apply_draft(conn, draft_id: int, by: int | None, force: bool = False, edited: Order | None = None,
                final_state: str = "accepted") -> Accepted:
    """TRK-1..3: turn a pending draft into a real change. The only code that changes order contents from a draft."""
    with transaction(conn, immediate=True):
        draft = get_draft(conn, draft_id)
        if draft is None or draft["state"] != "pending":
            raise OrderError("This has already been dealt with.")
        order = edited or draft_order(draft)
        action = draft["action"]

        if action == "question":
            _finish_draft(conn, draft_id, final_state)
            return Accepted(order_id=None)

        if action == "new":
            if order is None or not order.items:
                raise OrderError("An order needs at least one item.")
            user, pin = auth.ensure_customer(conn, order.customer, order.phone)
            oid = create_order(conn, order, user["id"] if user else None, by)
            _finish_draft(conn, draft_id, final_state)
            return Accepted(order_id=oid, customer_name=order.customer,
                            phone=auth.normalise_phone(order.phone) or "", new_pin=pin)

        target = get_order(conn, draft["target_order_id"]) if draft["target_order_id"] else None
        if target is None or target["status"] not in OPEN:
            raise OrderError("That order is already finished or cancelled, so it can't be changed.")
        if action == "cancel":
            cancel(conn, target["id"], by, _change_note(draft))
        else:
            if order is None or not order.items:
                raise OrderError("An order needs at least one item.")
            if target["status"] in ("preparing", "ready") and not force:
                raise NeedsConfirm("This order is already being made. Apply the change anyway?")
            update_details(conn, target["id"], order, by, _change_note(draft))
        _finish_draft(conn, draft_id, final_state)
        return Accepted(order_id=target["id"], customer_name=target["customer_name"], phone=target["phone"])


def _change_note(draft) -> str:
    verb = "Cancelled" if draft["action"] == "cancel" else "Changed"
    if draft["source"] == "customer":
        return f"{verb} by customer in the app"
    return f"{verb} by customer on WhatsApp ({draft['created_at'][:10]})"


def discard_draft(conn, draft_id: int) -> None:
    with transaction(conn):
        d = get_draft(conn, draft_id)
        if d is None or d["state"] != "pending" or d["source"] != "chat":
            raise OrderError("This has already been dealt with.")
        _finish_draft(conn, draft_id, "discarded")


def pending_chat_drafts(conn, run_id: int | None = None) -> list[sqlite3.Row]:
    if run_id is None:
        return conn.execute("SELECT * FROM drafts WHERE source = 'chat' AND state = 'pending' ORDER BY id").fetchall()
    return conn.execute(
        "SELECT * FROM drafts WHERE source = 'chat' AND state = 'pending' AND run_id = ? ORDER BY id", (run_id,)
    ).fetchall()


def conflict_flags(conn, draft: sqlite3.Row) -> list[str]:
    """TRK-27: computed at render time so it's always current."""
    if draft["state"] != "pending" or not draft["target_order_id"]:
        return []
    other = conn.execute(
        "SELECT 1 FROM drafts WHERE state = 'pending' AND target_order_id = ? AND id != ?",
        (draft["target_order_id"], draft["id"]),
    ).fetchone()
    return ["There's another change waiting for this order."] if other else []


# ---------- customer edits ----------

def validate_customer_order(order: Order, today: date | None = None) -> list[str]:
    """TRK-17 validation, plain English."""
    today = today or date.today()
    errors = []
    items = [i for i in order.items if i.name.strip()]
    if not items:
        errors.append("Please keep at least one item.")
    if any(i.quantity <= 0 for i in items):
        errors.append("Quantities need to be more than zero.")
    d = parse_date(order.delivery_date)
    if order.delivery_date.strip() and d is None:
        errors.append("Please pick a date from the calendar.")
    elif d is not None and d < today:
        errors.append("The date can't be in the past.")
    return errors


def customer_change(conn, order_id: int, customer_id: int, new: Order | None, today: date | None = None) -> str:
    """TRK-17..23. new=None means cancel. Returns 'applied' or 'requested'.
    The status is read inside a write lock, so a confirm that lands first wins (TRK-23)."""
    with transaction(conn, immediate=True):
        row = customer_order(conn, customer_id, order_id)
        if row is None:
            raise OrderError("We couldn't find that order.")
        if row["status"] not in OPEN:
            raise OrderError("This order is finished, so it can't be changed.")
        before = to_model(conn, row)
        if new is not None:
            new = new.model_copy(update={
                "customer": row["customer_name"], "phone": row["phone"],
                "items": [i for i in new.items if i.name.strip()],
            })
            errors = validate_customer_order(new, today)
            if errors:
                raise OrderError(" ".join(errors))
        action = "cancel" if new is None else "update"

        # TRK-21: at most one pending customer request per order
        conn.execute(
            "UPDATE drafts SET state = 'withdrawn', decided_at = ? "
            "WHERE source = 'customer' AND state = 'pending' AND target_order_id = ?",
            (now(), order_id),
        )
        draft_id = save_draft(conn, source="customer", action=action, order=new, target_order_id=order_id,
                              requested_by=customer_id, before=before, sender=row["customer_name"])
        if row["status"] == "received":
            apply_draft(conn, draft_id, customer_id, force=True, final_state="applied")
            conn.execute("UPDATE drafts SET seen_by_customer = 1 WHERE id = ?", (draft_id,))
            return "applied"
        return "requested"


def withdraw_request(conn, draft_id: int, customer_id: int) -> None:
    with transaction(conn):
        cur = conn.execute(
            "UPDATE drafts SET state = 'withdrawn', decided_at = ? "
            "WHERE id = ? AND requested_by = ? AND source = 'customer' AND state = 'pending'",
            (now(), draft_id, customer_id),
        )
        if cur.rowcount == 0:
            raise OrderError("That request has already been dealt with.")


def decide_request(conn, draft_id: int, admin_id: int, approve: bool, reason: str = "", force: bool = False) -> None:
    """TRK-22."""
    with transaction(conn, immediate=True):
        d = get_draft(conn, draft_id)
        if d is None or d["source"] != "customer" or d["state"] != "pending":
            raise OrderError("This request has already been dealt with.")
        if approve:
            apply_draft(conn, draft_id, admin_id, force=force)
        else:
            _finish_draft(conn, draft_id, "declined", reason.strip())
        conn.execute("UPDATE drafts SET seen_by_admin = 1 WHERE id = ?", (draft_id,))


def mark_seen(conn, draft_id: int) -> None:
    conn.execute("UPDATE drafts SET seen_by_admin = 1 WHERE id = ? AND source = 'customer'", (draft_id,))


def customer_changes(conn, at: datetime | None = None) -> list[sqlite3.Row]:
    """TRK-24: pending first, then directly-applied changes (unseen, or from the last 48 hours)."""
    since = ((at or datetime.now()) - timedelta(hours=48)).isoformat(timespec="seconds")
    return conn.execute(
        "SELECT * FROM drafts WHERE source = 'customer' AND (state = 'pending' "
        "OR (state = 'applied' AND (seen_by_admin = 0 OR created_at > ?))) "
        "ORDER BY state = 'pending' DESC, id DESC",
        (since,),
    ).fetchall()


def changes_badge(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM drafts WHERE source = 'customer' AND "
        "(state = 'pending' OR (state = 'applied' AND seen_by_admin = 0))"
    ).fetchone()[0]


def order_badges(conn, order_id: int) -> list[str]:
    """TRK-26."""
    badges = []
    if conn.execute("SELECT 1 FROM drafts WHERE source = 'customer' AND state = 'pending' AND target_order_id = ?",
                    (order_id,)).fetchone():
        badges.append("Change requested")
    if conn.execute("SELECT 1 FROM drafts WHERE source = 'customer' AND state = 'applied' AND seen_by_admin = 0 "
                    "AND target_order_id = ?", (order_id,)).fetchone():
        badges.append("Changed by customer")
    return badges


def latest_customer_request(conn, order_id: int, customer_id: int) -> sqlite3.Row | None:
    """What the customer should see about their latest request (TRK-20, TRK-22)."""
    row = conn.execute(
        "SELECT * FROM drafts WHERE source = 'customer' AND target_order_id = ? AND requested_by = ? "
        "ORDER BY id DESC LIMIT 1",
        (order_id, customer_id),
    ).fetchone()
    return row if row is not None and row["state"] in ("pending", "accepted", "declined") else None


# ---------- diff ----------

@dataclass
class FieldChange:
    label: str
    old: str
    new: str


def diff(before: Order | None, after: Order | None) -> list[FieldChange]:
    """TRK-25: only what changed; items line by line."""
    if before is None or after is None:
        return []
    changes = []
    for field, label in (("delivery_date", "Date"), ("delivery_time", "Time"), ("address", "Address"), ("notes", "Notes")):
        old, new = getattr(before, field).strip(), getattr(after, field).strip()
        if old != new:
            if field == "address":
                old, new = old or "Pickup", new or "Pickup"
            changes.append(FieldChange(label, old or "—", new or "—"))

    def key(i: OrderItem) -> str:
        return i.name.strip().lower()

    old_items = {key(i): i for i in before.items}
    new_items = {key(i): i for i in after.items}
    for k, i in old_items.items():
        if k not in new_items:
            changes.append(FieldChange("Item removed", items_text([i]), "—"))
        elif (i.quantity, i.unit.strip().lower()) != (new_items[k].quantity, new_items[k].unit.strip().lower()):
            changes.append(FieldChange("Item changed", items_text([i]), items_text([new_items[k]])))
    for k, i in new_items.items():
        if k not in old_items:
            changes.append(FieldChange("Item added", "—", items_text([i])))
    return changes
