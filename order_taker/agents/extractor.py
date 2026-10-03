"""Extractor agent: one per sender, main model, small focused prompt (INT-10, INT-11, INT-13).
Dates and phone numbers are finished off in code afterwards (INT-21, INT-22)."""

from __future__ import annotations

import re
from datetime import date

from ..auth import normalise_phone
from ..models import ExtractResult, Order
from ..orders import items_text
from .chat_parser import SenderGroup
from .dates import resolve_date

PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")

SYSTEM = """You extract food/business orders from one customer's WhatsApp messages for a small home business.
Rules:
- Ignore greetings, thanks, and chit-chat.
- If a later message changes an earlier one in these messages, keep only the final version.
- delivery_date: copy the day exactly as the customer wrote it ("Sunday", "kal", "tomorrow", "5th Oct").
  Do NOT work out a calendar date yourself. Put the time of day ("4pm", "evening", "subah") in delivery_time.
- If the customer will collect the order themselves, leave address empty and write "pickup" in notes.
- Never invent details. Leave a field empty if it isn't in the messages.
- Messages may mix English, Hindi, Kannada or Tamil written in English letters. Translate item names to plain English.
- customer: use the Customer name given with the messages, unless they give another name for the order.

kind: what the messages are mostly about: new_order, change, cancel, question (asks something without
ordering) or chit_chat (greetings, thanks, nothing to act on).

Each entry in "actions" is one of:
- "new": a new order. target_order_id null. "order" has the full details.
- "update": changes one of the customer's EARLIER OPEN ORDERS. target_order_id is that order's number.
  "order" has the full details after the change (copy unchanged details from the earlier order).
- "cancel": cancels one of the EARLIER OPEN ORDERS. target_order_id is its number. "order" null.
Only use update/cancel with a number from the EARLIER OPEN ORDERS list. If it says (none), only use "new".
If there is no order at all, return an empty actions list.
Return JSON only."""


def describe_open_orders(open_orders: list[tuple[int, Order]]) -> str:
    if not open_orders:
        return "(none)"
    lines = []
    for oid, o in open_orders:
        bits = [items_text(o.items), o.delivery_date, o.delivery_time, o.address or "pickup", o.notes]
        lines.append(f"#{oid}: " + "; ".join(b for b in bits if b))
    return "\n".join(lines)


def build_user_message(group: SenderGroup, open_orders: list[tuple[int, Order]]) -> str:
    """Everything that differs per sender goes here, so the system prompt stays identical
    across calls and Ollama can reuse its cached work on it."""
    return (f"Customer: {group.sender}\n\nEARLIER OPEN ORDERS:\n{describe_open_orders(open_orders)}\n\n"
            f"Messages:\n{group.as_text()}")


def reference_date(group: SenderGroup, today: date) -> date:
    """Relative days count from when the customer last wrote, not from when the chat is pasted."""
    stamps = [m.sent_at for m in group.messages if m.sent_at]
    return max(stamps).date() if stamps else today


def phone_in_messages(group: SenderGroup) -> str:
    for m in group.messages:
        found = PHONE_RE.search(m.text)
        if found:
            return normalise_phone(found.group(0)) or ""
    return group.phone or ""


async def extract_group(client, model: str, group: SenderGroup, open_orders: list[tuple[int, Order]],
                        today: date) -> ExtractResult:
    result = await client.structured(model, SYSTEM, build_user_message(group, open_orders), ExtractResult)
    ref = reference_date(group, today)
    phone = phone_in_messages(group)
    open_ids = {oid for oid, _ in open_orders}
    for a in result.actions:
        if a.action == "update" and a.target_order_id not in open_ids and a.order is not None:
            # An "update" of an order that doesn't exist is really a new order
            a.action, a.target_order_id = "new", None
        o = a.order
        if o is None:
            continue
        if not o.customer.strip():
            o.customer = group.sender
        if not normalise_phone(o.phone) and phone:  # INT-22
            o.phone = phone
        o.delivery_date = resolve_date(o.delivery_date, ref)  # INT-21
    return result
