"""Checker agent: fixed rules, no model (INT-14). Flags never block acceptance (INT-15)."""

from __future__ import annotations

import re
from datetime import date

from ..auth import normalise_phone
from ..models import DraftAction, Order
from ..orders import parse_date

NO_DATE = "There's no delivery date yet."
UNCLEAR_DATE = "The delivery date isn't clear."
PAST_DATE = "The delivery date is in the past."
NO_ADDRESS = "Delivery or pickup? No address was given."
NO_PHONE = "There's no phone number, so the customer can't track this order."
BAD_PHONE = "The phone number doesn't look right. It needs 10 digits."
ZERO_QTY = "One of the items has a quantity of 0."
NO_ITEMS = "No items were found."
BAD_TARGET = "This points to an order that isn't open any more."
DUPLICATE = "Looks like a duplicate of another order."

_PICKUP = re.compile(r"\b(pick\s?-?up|collect|take ?away|self)\b", re.I)


def _signature(o: Order) -> tuple:
    who = normalise_phone(o.phone) or o.customer.strip().lower()
    items = tuple(sorted((i.name.strip().lower(), i.quantity, i.unit.strip().lower()) for i in o.items))
    return who, o.delivery_date.strip(), items


def check(action: DraftAction, sender_open: dict[int, Order], others: list[Order], today: date) -> list[str]:
    """sender_open: this sender's open orders by id. others: every other open order and draft to compare against."""
    flags: list[str] = []
    if action.action in ("update", "cancel") and action.target_order_id not in sender_open:
        flags.append(BAD_TARGET)
    o = action.order
    if action.action == "cancel" or o is None:
        return flags

    if not o.items:
        flags.append(NO_ITEMS)
    elif any(i.quantity <= 0 for i in o.items):
        flags.append(ZERO_QTY)
    if not o.delivery_date.strip():
        flags.append(NO_DATE)
    else:
        d = parse_date(o.delivery_date)
        if d is None:
            flags.append(UNCLEAR_DATE)
        elif d < today:
            flags.append(PAST_DATE)
    if not o.address.strip() and not _PICKUP.search(f"{o.notes} {o.delivery_time}"):
        flags.append(NO_ADDRESS)
    if not normalise_phone(o.phone):
        flags.append(BAD_PHONE if o.phone.strip() else NO_PHONE)
    if o.items and _signature(o) in {_signature(x) for x in others}:
        flags.append(DUPLICATE)
    return flags
