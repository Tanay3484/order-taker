"""006 Hosted demo."""

import dataclasses
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from order_taker import auth, bootstrap
from order_taker import orders as om
from order_taker.agents.chat_parser import group_by_sender, parse_chat
from order_taker.config import Settings
from order_taker.web.main import create_app

from .conftest import get_csrf, page_text, post
from .test_chat_parser import SAMPLES


@pytest.fixture
def demo_settings(settings):
    return dataclasses.replace(settings, admin_username="demo", admin_password="bake-the-demo",
                               shop_name="Demo Bakes", shop_whatsapp="99000 11111", demo=True,
                               secure_cookies=True, cookie_samesite="none")


@pytest.fixture
def demo_client(demo_settings, fake):
    with TestClient(create_app(demo_settings, fake), base_url="https://testserver") as c:
        yield c


def test_host1_admin_from_env_and_setup_locked(demo_client, demo_settings):
    """HOST-1: admin created from env; /setup is gone; nobody can claim the shop."""
    assert demo_client.get("/setup").status_code == 404
    assert demo_client.get("/", follow_redirects=False).headers["location"] == "/login"
    r = post(demo_client, "/login", {"kind": "admin", "ident": "demo", "secret": "bake-the-demo"})
    assert r.headers["location"] == "/admin"
    assert "Demo Bakes" in page_text(demo_client.get("/admin"))


def test_host1_password_follows_env_on_restart(demo_settings, fake):
    create_app(demo_settings, fake)
    changed = dataclasses.replace(demo_settings, admin_password="a-new-secret")
    create_app(changed, fake)
    from order_taker import db
    conn = db.connect(changed.db_path)
    assert conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] == 1
    assert auth.login(conn, "admin", "demo", "a-new-secret")


def test_host1_off_by_default(client):
    """Laptop installs are unchanged: /setup still works when no env admin is set."""
    assert client.get("/setup").status_code == 200


def test_host2_secure_cookie_flags(demo_client):
    """HOST-2."""
    r = post(demo_client, "/login", {"kind": "admin", "ident": "demo", "secret": "bake-the-demo"})
    cookie = r.headers["set-cookie"].lower()
    assert "secure" in cookie and "samesite=none" in cookie and "httponly" in cookie


def test_host2_samesite_none_needs_secure():
    assert Settings(cookie_samesite="none", secure_cookies=False).samesite == "lax"
    assert Settings(cookie_samesite="none", secure_cookies=True).samesite == "none"
    assert Settings(cookie_samesite="bogus").samesite == "lax"


def test_host3_healthz(client, fake):
    """HOST-3: no login needed; 200 even while the AI helper is down."""
    assert client.get("/healthz").json() == {"ok": True, "ai_ready": True}
    fake.up = False
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["ai_ready"] is False


def test_host4_banner_only_in_demo(demo_client, client):
    """HOST-4."""
    banner = "This is a demo. Please don't enter real names, phone numbers or addresses."
    assert banner in page_text(demo_client.get("/login"))
    client.get("/setup")
    assert banner not in page_text(client.get("/setup"))


def test_host5_seed_data(demo_client, demo_settings):
    """HOST-5: orders in several stages, a demo customer who can log in."""
    from order_taker import db
    conn = db.connect(demo_settings.db_path)
    statuses = {r[0] for r in conn.execute("SELECT status FROM orders")}
    assert {"received", "preparing", "ready", "confirmed", "delivered"} <= statuses
    k = bootstrap.DEMO_CUSTOMER
    assert auth.login(conn, "customer", k["phone"], k["pin"])["name"] == "Kavya"
    arjun = auth.customer_by_phone(conn, "9900044455")
    assert arjun["starter_pin"]  # shows the PIN-on-card feature


def test_host5_seed_does_not_overlap_sample_chat(demo_settings):
    seeded = {"Kavya", "Arjun", "Divya", "Farhan"}
    senders = {g.sender for g in group_by_sender(parse_chat((SAMPLES / "sample_chat.txt").read_text("utf-8")))}
    assert not seeded & senders


def test_host5_seed_only_once(demo_settings, fake):
    create_app(demo_settings, fake)
    create_app(demo_settings, fake)
    from order_taker import db
    conn = db.connect(demo_settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 5


def test_host6_demo_logins_and_sample_button(demo_client):
    """HOST-6."""
    page = page_text(demo_client.get("/login"))
    assert "9811122233" in page and "2468" in page
    admin_tab = page_text(demo_client.get("/login?tab=admin"))
    assert "bake-the-demo" in admin_tab
    post(demo_client, "/login", {"kind": "admin", "ident": "demo", "secret": "bake-the-demo"})
    intake = demo_client.get("/admin/intake").text
    assert "Use the sample chat" in intake and "Rahul Bhaiya" in intake


def test_host6_demo_customer_sees_orders(demo_client):
    k = bootstrap.DEMO_CUSTOMER
    post(demo_client, "/login", {"kind": "customer", "ident": k["phone"], "secret": k["pin"]})
    page = page_text(demo_client.get("/my-orders"))
    assert "pineapple cake" in page and "Ready for delivery" in page


def test_host7_long_chat_refused(client, app):
    """HOST-7."""
    from .conftest import setup_admin
    setup_admin(client)
    r = post(client, "/admin/intake", {"text": "x" * (app.state.settings.max_chat_chars + 1)}, page="/admin/intake")
    assert "That's a very long chat. Please paste just the recent messages." in page_text(r)


def test_host8_port_and_public_url(monkeypatch, settings, fake):
    """HOST-8."""
    monkeypatch.setenv("ORDER_PORT", "7860")
    monkeypatch.setenv("ORDER_PUBLIC_URL", "https://tanay3484-order-taker.hf.space/")
    assert Settings().port == 7860
    app = create_app(settings, fake)
    assert app.state.public_url == "https://tanay3484-order-taker.hf.space"


def test_host5_seeded_dates_follow_today(tmp_path):
    """The demo always looks current: seeded dates are relative to the day it starts."""
    from order_taker import db
    conn = db.connect(str(tmp_path / "seed.db"))
    db.migrate(conn)
    day = date(2026, 10, 4)
    bootstrap.seed_demo(conn, today=day)
    for tab in ("today", "tomorrow", "upcoming", "past"):
        assert om.orders_in_tab(conn, tab, today=day), tab


def test_host2_demo_cookie_works_inside_the_hugging_face_frame(settings, fake):
    """HOST-2 (amended): a secure demo defaults to SameSite=None + Partitioned; laptops stay on Lax."""
    s = dataclasses.replace(settings, admin_username="demo", admin_password="try-the-demo", demo=True,
                            secure_cookies=True)
    assert s.samesite == "none" and s.partitioned
    with TestClient(create_app(s, fake), base_url="https://testserver") as c:
        cookie = c.get("/login").headers["set-cookie"].lower()
        assert "samesite=none" in cookie and "secure" in cookie and "partitioned" in cookie
    assert Settings().samesite == "lax" and not Settings().partitioned
    assert Settings(demo=True).samesite == "lax"  # no HTTPS, no SameSite=None


def test_host10_missing_cookie_is_explained(demo_client):
    """HOST-10: what happened inside the Hugging Face page: the form arrives without our cookie."""
    token = get_csrf(demo_client, "/login")
    demo_client.cookies.clear()
    r = demo_client.post("/login", data={"csrf": token, "kind": "admin", "ident": "demo", "secret": "x"})
    text = page_text(r)
    assert r.status_code == 400 and "open it in its own tab" in text and "expired" not in text


def test_host9_open_in_tab_link(demo_client, client):
    """HOST-9: the link is on demo pages (shown by app.js only when framed)."""
    html = demo_client.get("/login").text
    assert re.search(r'<a class="open-tab" href="http[^"]*" target="_blank"[^>]*hidden data-open-tab>', html)
    assert "data-open-tab" not in client.get("/setup").text


def test_host11_demo_logins_are_prefilled(demo_client):
    """HOST-11: visitors only need to tap Log in."""
    customer = demo_client.get("/login").text
    k = bootstrap.DEMO_CUSTOMER
    assert f'value="{k["phone"]}"' in customer and f'value="{k["pin"]}"' in customer
    admin = demo_client.get("/login?tab=admin").text
    assert 'value="demo"' in admin and 'value="bake-the-demo"' in admin


def test_host11_not_prefilled_outside_demo(client):
    from .conftest import setup_admin
    setup_admin(client)
    client.cookies.clear()
    html = client.get("/login?tab=admin").text
    password_input = re.search(r'<input name="secret"[^>]*>', html).group(0)
    assert "value=" not in password_input
