"""007 Guided tour."""

import dataclasses
import json
import re

import pytest
from fastapi.testclient import TestClient

from order_taker import bootstrap, tours
from order_taker.web.main import create_app

from .conftest import post, setup_admin
from .test_progress import BANNED


@pytest.fixture
def demo(settings, fake):
    s = dataclasses.replace(settings, admin_username="demo", admin_password="try-the-demo", demo=True)
    with TestClient(create_app(s, fake)) as c:
        yield c


def tour_on(html: str) -> dict | None:
    m = re.search(r'<script type="application/json" id="tour-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def login_admin(c):
    post(c, "/login", {"kind": "admin", "ident": "demo", "secret": "try-the-demo"})


def login_customer(c):
    k = bootstrap.DEMO_CUSTOMER
    post(c, "/login", {"kind": "customer", "ident": k["phone"], "secret": k["pin"]})


def pages(c):
    """(tour id, html) for every page that has a tour, with demo data loaded."""
    out = [("login-customer", c.get("/login").text), ("login-admin", c.get("/login?tab=admin").text)]
    login_admin(c)
    out += [("board", c.get("/admin").text), ("intake", c.get("/admin/intake").text)]
    c.cookies.clear()
    login_customer(c)
    out.append(("my-orders", c.get("/my-orders").text))
    return out


def test_tour1_each_page_has_its_tour_and_targets(demo):
    """TOUR-1, TOUR-5: the right tour is on each page and every required part of the page exists."""
    for tid, html in pages(demo):
        data = tour_on(html)
        assert data and data["id"] == tid, tid
        assert "data-tour-start" in html and "/static/tour.js" in html
        for step in tours.TOURS[tid]:
            if not step.optional:
                assert f'data-tour="{step.target}"' in html, f"{tid}: missing {step.target}"


def test_tour1_optional_targets_show_up_with_demo_data(demo):
    """With the demo's example orders, the board shows the next-step button and a login PIN row."""
    html = dict(pages(demo))["board"]
    assert 'data-tour="next-step"' in html and 'data-tour="login-row"' in html


def test_tour1_no_tour_elsewhere(demo):
    login_admin(demo)
    for url in ("/admin/customers", "/admin/settings", "/admin/prep"):
        html = demo.get(url).text
        assert tour_on(html) is None and "data-tour-start" not in html, url


def test_tour1_customers_never_get_an_admin_tour(demo):
    login_customer(demo)
    assert tour_on(demo.get("/my-orders").text)["id"] == "my-orders"


def test_tour3_customer_pin_step(demo):
    """TOUR-3."""
    steps = tour_on(demo.get("/login").text)["steps"]
    pin = next(s for s in steps if s["target"] == "pin")
    assert pin["text"] == ("A PIN is needed. Ask the shop you ordered from for your PIN; "
                           "they'll send it to you on WhatsApp.")


def test_tour5_demo_only_steps_need_demo_mode(client):
    """TOUR-5: outside demo mode there's no demo-login or sample-chat step."""
    setup_admin(client)
    client.cookies.clear()
    targets = [s["target"] for s in tour_on(client.get("/login").text)["steps"]]
    assert "pin" in targets and "demo-login" not in targets
    assert tours.for_page("login.html", {"tab": "admin"}, demo=False)["steps"]  # still has the tab step
    intake = [s["target"] for s in tours.for_page("admin_intake.html", {}, demo=False)["steps"]]
    assert "sample-chat" not in intake


def test_tour6_plain_english():
    """TOUR-6: same banned words as the progress feed (PRG-4)."""
    for tid, steps in tours.TOURS.items():
        for s in steps:
            text = f"{s.title} {s.text}".lower()
            words = re.findall(r"[a-z]+", text)
            for bad in BANNED:
                assert (bad not in text) if " " in bad else (bad not in words), f"{tid}/{s.target}: {bad}"


def test_tour8_no_external_requests():
    """TOUR-8: the tour script loads nothing from outside and only uses localStorage."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "order_taker" / "web" / "static" / "tour.js").read_text("utf-8")
    assert "http" not in js and "fetch(" not in js and "XMLHttpRequest" not in js
    assert "localStorage" in js and "try {" in js


def test_hidden_attribute_always_wins_in_css():
    """Found during the tour check: .btn/label display rules beat [hidden], so the tour's Back button on
    step 1 and the address box behind 'Pickup instead of delivery' never actually hid."""
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "order_taker" / "web" / "static" / "app.css").read_text("utf-8")
    assert "[hidden] { display: none !important; }" in css
