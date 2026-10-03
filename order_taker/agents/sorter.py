"""Sorter agent: a small model decides what a sender's messages are about (INT-7)."""

from __future__ import annotations

from ..models import SortResult
from .chat_parser import SenderGroup

SYSTEM = """You sort WhatsApp messages sent to a small home food business.
Read one customer's messages and pick exactly one kind:
- new_order: they want to order something (even if they also tweak it in a later message)
- change: they change an order they placed earlier
- cancel: they cancel an order they placed earlier
- question: they ask something (price, availability, timing) without ordering
- chit_chat: greetings, thanks, good night, emojis, nothing to act on
If they have earlier orders listed and talk about changing them, that's "change".
Examples:
"2 box brownies tomorrow" -> new_order
"Good night aunty 😊" -> chit_chat
"Can you make the Sunday cake eggless instead?" -> change
"Sorry, please cancel my cupcakes" -> cancel
"How much for 1 kg cheesecake?" -> question
Reply with JSON only. reason: at most 12 words."""


async def sort_group(client, model: str, group: SenderGroup, has_open_orders: bool) -> SortResult:
    context = "This customer has earlier open orders." if has_open_orders else "This customer has no earlier orders."
    user = f"Customer: {group.sender}\n{context}\n\nMessages:\n{group.as_text()}"
    return await client.structured(model, SYSTEM, user, SortResult, num_predict=64)
