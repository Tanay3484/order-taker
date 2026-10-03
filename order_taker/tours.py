"""Guided tours for first-time visitors (007). The words live here so they can be
tested for plain English (TOUR-6); the browser only positions them (static/tour.js)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

VERSION = 1  # bump to show a changed tour again to people who've seen it


@dataclass(frozen=True)
class Step:
    target: str  # matches data-tour="..." in the templates
    title: str
    text: str
    demo_only: bool = False
    optional: bool = False  # may be missing from the page (no orders yet, no changes…)


TOURS: dict[str, list[Step]] = {
    "login-customer": [
        Step("phone", "Your phone number",
             "Log in with the mobile number you placed your order with."),
        Step("pin", "Your PIN",
             "A PIN is needed. Ask the shop you ordered from for your PIN; they'll send it to you on WhatsApp."),
        Step("demo-login", "Trying the demo?",
             "Use this phone number and PIN to see what a customer sees.", demo_only=True),
        Step("tab-admin", "Run the shop?",
             "Shop owners log in here instead, with a username and password."),
    ],
    "login-admin": [
        Step("demo-login", "Try the shop owner's side",
             "Use this username and password to see how orders are taken and tracked.", demo_only=True),
        Step("tab-customer", "Ordered something?",
             "Customers log in on this tab with their phone number and PIN."),
    ],
    "board": [
        Step("nav-add", "Start here",
             "Paste your WhatsApp chat here. Little helpers read it and turn the messages into orders for you to check."),
        Step("tabs", "Orders by day",
             "Orders are grouped by delivery day. Today also shows anything that's late, so nothing gets forgotten."),
        Step("next-step", "One tap to move it along", "Each order goes Received → Confirmed → Preparing → Ready → "
             "Delivered. Tap here for the next step. Tapped by mistake? Undo appears right next to it.",
             optional=True),
        Step("login-row", "Your customer's login",
             "Send them their PIN on WhatsApp so they can follow their order from their phone.", optional=True),
        Step("changes", "Changes from customers",
             "When a customer changes or cancels an order in the app, you'll see exactly what changed here. "
             "You approve anything you've already confirmed.", optional=True),
        Step("nav-prep", "What to bake",
             "See the total of every item you need to make on any day."),
    ],
    "intake": [
        Step("chat-box", "Paste the chat",
             "Copy the messages from WhatsApp and paste them here, or upload an exported chat. "
             "You can paste the whole chat every time: messages already read are skipped."),
        Step("sample-chat", "No chat handy?",
             "Fill in an example chat with a few customers to see how it works.", demo_only=True),
        Step("read-button", "Let the helpers read it",
             "Press this and watch what's happening step by step. Each order shows up as soon as it's ready, "
             "so you can start checking straight away."),
        Step("progress", "What's happening",
             "A running commentary of what the helpers are doing, in everyday words.", optional=True),
    ],
    "my-orders": [
        Step("steps", "Where your order is",
             "Follow your order from 'We've got your order' all the way to 'Delivered'.", optional=True),
        Step("change-order", "Need to change something?",
             "Change or cancel your order here. If the shop has already confirmed it, they'll approve your change.",
             optional=True),
        Step("nav-pin", "Your PIN",
             "You can change your PIN any time."),
    ],
}

TEMPLATES = {"admin_board.html": "board", "admin_intake.html": "intake", "my_orders.html": "my-orders"}


def tour_id(template: str, ctx: dict) -> str | None:
    if template == "login.html":
        return "login-admin" if ctx.get("tab") == "admin" else "login-customer"
    return TEMPLATES.get(template)


def for_page(template: str, ctx: dict, demo: bool) -> dict | None:
    """The tour for this page as plain data for the browser, demo-only steps removed outside demo mode (TOUR-5)."""
    tid = tour_id(template, ctx)
    if tid is None:
        return None
    steps = [asdict(s) for s in TOURS[tid] if demo or not s.demo_only]
    return {"id": tid, "version": VERSION, "steps": steps} if steps else None
