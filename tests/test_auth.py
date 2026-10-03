"""002 Accounts & login."""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from order_taker import auth
from order_taker import orders as om
from order_taker.models import Order, OrderItem
from order_taker.web import deps, routes_admin

from .conftest import (ADMIN_PASSWORD, get_csrf, login_customer, make_customer, make_order, page_text, post,
                       setup_admin)


def test_auth1_setup_once(client, conn):
    """AUTH-1: one-time setup creates the admin and shop details, then disappears."""
    assert client.get("/", follow_redirects=False).headers["location"] == "/setup"
    r = post(client, "/setup", {"name": "Asha", "username": "asha", "password": "short",
                                "shop_name": "", "shop_whatsapp": "1"}, page="/setup")
    assert r.status_code == 400 and "at least 8 characters" in r.text
    setup_admin(client)
    assert auth.admin_exists(conn)
    assert conn.execute("SELECT value FROM settings WHERE key = 'shop_name'").fetchone()[0] == "Asha's Bakes"
    assert client.get("/setup").status_code == 404


def test_auth2_login_page_has_both_tabs(client):
    """AUTH-2."""
    setup_admin(client)
    client.cookies.clear()
    page = page_text(client.get("/login"))
    assert "I'm a customer" in page and "Shop owner" in page
    assert "PIN" in page
    assert "Password" in client.get("/login?tab=admin").text


@pytest.mark.parametrize("raw", ["98450 12345", "+91-98450-12345", "098450 12345", "919845012345", "(98450) 12345"])
def test_auth3_phone_normalisation(raw):
    """AUTH-3: one customer, however the number is written."""
    assert auth.normalise_phone(raw) == "9845012345"


@pytest.mark.parametrize("raw", ["", "123", "98450 1234", "98450 123456", "1234567890123", "919845012",
                                 "19845012345", "abc", "+44 7700 900123"])
def test_auth3_anything_but_10_digits_is_rejected(raw):
    """AUTH-3: after removing +91 / 91 / 0, exactly 10 digits or it isn't a phone."""
    assert auth.normalise_phone(raw) is None


def test_auth15_login_with_bad_phone_explains_and_does_not_count(conn, app):
    """AUTH-15: plain message, not counted as a failed attempt, reveals nothing."""
    c = make_customer(conn)
    for _ in range(6):
        with pytest.raises(auth.LoginError, match="10 digits"):
            auth.login(conn, "customer", "98450 1234", "0000")
    assert auth.get_user(conn, c["id"])["failed_attempts"] == 0


def test_auth15_same_message_on_every_form(client, conn):
    """AUTH-15: setup, settings, add-phone, draft edit and order edit all reject a 9-digit number."""
    rule = auth.PHONE_RULE
    r = post(client, "/setup", {"name": "Asha", "username": "asha", "password": ADMIN_PASSWORD,
                                "shop_name": "S", "shop_whatsapp": "99000 1111"}, page="/setup")
    assert r.status_code == 400 and rule in page_text(r)
    setup_admin(client)
    r = post(client, "/admin/settings", {"shop_name": "S", "shop_whatsapp": "99000 111111"}, page="/admin/settings")
    assert rule in page_text(r)

    oid = make_order(conn, None)
    r = post(client, f"/admin/orders/{oid}/phone", {"phone": "98450 1234"}, page=f"/admin/orders/{oid}/edit")
    assert rule in page_text(r)

    from order_taker.models import Order, OrderItem
    d = om.save_draft(conn, source="chat", action="new", sender="Sneha",
                      order=Order(customer="Sneha", items=[OrderItem(name="cake", quantity=1)]))
    for url in (f"/admin/drafts/{d}/edit", f"/admin/orders/{oid}/edit"):
        r = post(client, url, {"customer": "Sneha", "phone": "98450 1234", "item_name": "cake", "item_qty": "1",
                               "item_unit": "kg"}, page=url)
        assert r.status_code == 400 and rule in page_text(r), url


def test_trk29_changing_phone_on_edit_relinks_customer(client, conn):
    """TRK-29: the phone on Edit order is saved and links the right customer."""
    setup_admin(client)
    oid = make_order(conn, None)
    url = f"/admin/orders/{oid}/edit"
    r = post(client, url, {"customer": "Walk-in", "phone": "+91 98450 77777", "item_name": "cake", "item_qty": "1",
                           "item_unit": "kg"}, page=url)
    assert r.status_code == 200 and "PIN" in r.text  # new customer -> starter PIN to send
    row = om.get_order(conn, oid)
    assert row["phone"] == "9845077777" and row["customer_id"] == auth.customer_by_phone(conn, "9845077777")["id"]


def _chat_draft(conn, phone="98450 12345", name="Sneha"):
    order = Order(customer=name, phone=phone, items=[OrderItem(name="cupcakes", quantity=12, unit="pcs")],
                  delivery_date="2099-01-05")
    return om.save_draft(conn, source="chat", action="new", order=order, sender=name)


def test_auth4_accepting_new_number_creates_customer_and_shows_pin(client, conn):
    """AUTH-4: account created, PIN shown once with a WhatsApp message."""
    setup_admin(client)
    draft = _chat_draft(conn)
    r = post(client, f"/admin/drafts/{draft}/accept", page="/admin/intake")
    assert r.status_code == 200
    user = auth.customer_by_phone(conn, "9845012345")
    assert user is not None and user["must_change_pin"] == 1
    assert "you can track your order at http://" in r.text and "Login: your phone number, PIN" in r.text
    assert "https://wa.me/919845012345?text=" in r.text


def test_auth4_existing_customer_gets_no_new_pin(client, conn):
    setup_admin(client)
    make_customer(conn, "Sneha", "9845012345")
    r = post(client, f"/admin/drafts/{_chat_draft(conn)}/accept", page="/admin/intake")
    assert r.status_code == 303


def test_auth5_order_without_phone_saved_and_linkable(client, conn):
    """AUTH-5: saved, marked, and a phone can be added later."""
    setup_admin(client)
    r = post(client, f"/admin/drafts/{_chat_draft(conn, phone='')}/accept", page="/admin/intake")
    assert "No phone – customer can't track this" in page_text(r)
    oid = conn.execute("SELECT id FROM orders").fetchone()[0]
    assert "No phone – customer can't track this" in page_text(client.get("/admin?tab=upcoming"))
    r = post(client, f"/admin/orders/{oid}/phone", {"phone": "98450 99999"}, page=f"/admin/orders/{oid}/edit")
    assert "PIN" in r.text
    row = om.get_order(conn, oid)
    assert row["phone"] == "9845099999" and row["customer_id"] is not None


def test_auth6_first_login_forces_pin_change(client, conn):
    """AUTH-6."""
    setup_admin(client)
    client.cookies.clear()
    user, pin = auth.ensure_customer(conn, "Priya", "9845012345")
    r = login_customer(client, "98450 12345", pin)
    assert r.headers["location"] == "/change-pin"
    assert client.get("/my-orders", follow_redirects=False).headers["location"] == "/change-pin"
    r = post(client, "/change-pin", {"pin": "4321", "pin2": "4321"}, page="/change-pin")
    assert r.status_code == 303
    assert client.get("/my-orders").status_code == 200


def test_auth7_lockout_after_five_wrong_tries(conn, app):
    """AUTH-7."""
    make_customer(conn, pin="1234")
    for _ in range(4):
        with pytest.raises(auth.LoginError, match="don't match"):
            auth.login(conn, "customer", "9845012345", "0000")
    with pytest.raises(auth.LoginError, match="Too many tries"):
        auth.login(conn, "customer", "9845012345", "0000")
    with pytest.raises(auth.LoginError, match="Too many tries"):
        auth.login(conn, "customer", "9845012345", "1234")  # even the right PIN
    later = datetime.now() + timedelta(minutes=16)
    assert auth.login(conn, "customer", "9845012345", "1234", at=later)["name"] == "Priya"


def test_auth8_admin_resets_pin(client, conn):
    """AUTH-8: new PIN shown once; customer must change it."""
    setup_admin(client)
    c = make_customer(conn)
    r = post(client, f"/admin/customers/{c['id']}/reset-pin", page="/admin/customers")
    assert r.status_code == 200 and "until they choose their own PIN" in r.text
    assert auth.get_user(conn, c["id"])["must_change_pin"] == 1
    with pytest.raises(auth.LoginError):
        auth.login(conn, "customer", c["phone"], "1234")


def test_auth9_secrets_are_hashed(conn, app):
    """AUTH-9."""
    c = make_customer(conn, pin="5678")
    assert c["pin_hash"].startswith("scrypt$") and "5678" not in c["pin_hash"]
    assert auth.verify_secret("5678", c["pin_hash"]) and not auth.verify_secret("5679", c["pin_hash"])


def test_auth10_customer_gets_403_on_every_admin_route(client, conn, app):
    """AUTH-10: checked on the server for every /admin route."""
    setup_admin(client)
    client.cookies.clear()
    make_customer(conn)
    login_customer(client)
    token = get_csrf(client, "/my-orders")
    checked = 0
    for route in routes_admin.router.routes:
        path = route.path
        url = path.replace("{order_id}", "1").replace("{draft_id}", "1").replace("{run_id}", "1") \
                  .replace("{customer_id}", "1")
        for method in route.methods:
            r = client.request(method, url, data={"csrf": token} if method == "POST" else None,
                               follow_redirects=False)
            assert r.status_code == 403, f"{method} {url} -> {r.status_code}"
            checked += 1
    assert checked > 20


def test_auth10_logged_out_is_sent_to_login(client):
    setup_admin(client)
    client.cookies.clear()
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/my-orders", follow_redirects=False).headers["location"] == "/login"


def test_auth11_secret_key_and_admin_session_expiry(client, settings, monkeypatch):
    """AUTH-11: secret kept in data/; admin sessions end after 12 hours."""
    assert (Path(settings.data_dir) / "secret.key").exists()
    setup_admin(client)
    assert client.get("/admin", follow_redirects=False).status_code == 200
    real = time.time
    monkeypatch.setattr(deps.time, "time", lambda: real() + 13 * 3600)
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/login"


def test_auth11_cookie_is_httponly(client):
    r = post(client, "/setup", {"name": "Asha", "username": "asha", "password": ADMIN_PASSWORD,
                                "shop_name": "S", "shop_whatsapp": "9900011111"}, page="/setup")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_auth12_errors_do_not_reveal_accounts(client, conn):
    """AUTH-12: same message for unknown phone and wrong PIN."""
    setup_admin(client)
    client.cookies.clear()
    make_customer(conn)
    unknown = page_text(login_customer(client, "9000000000", "1234"))
    wrong = page_text(login_customer(client, "9845012345", "9999"))
    assert "That phone number and PIN don't match." in unknown
    assert "That phone number and PIN don't match." in wrong


def test_csrf_required_on_posts(client):
    setup_admin(client)
    r = client.post("/admin/settings", data={"shop_name": "X", "shop_whatsapp": "9900011111"})
    assert r.status_code == 400 and "expired" in r.text


def test_auth13_starter_pin_readable_until_customer_chooses_their_own(conn, app):
    """AUTH-13: the shop-issued PIN is kept readable; the customer's own PIN never is."""
    user, pin = auth.ensure_customer(conn, "Priya", "9845012345")
    assert auth.get_user(conn, user["id"])["starter_pin"] == pin
    auth.change_pin(conn, user["id"], "2468")
    row = auth.get_user(conn, user["id"])
    assert row["starter_pin"] is None
    assert not any("2468" in str(v) for v in tuple(row))  # only the hash is stored
    new = auth.reset_pin(conn, user["id"])
    assert auth.get_user(conn, user["id"])["starter_pin"] == new
    assert auth.login(conn, "customer", "9845012345", new)["id"] == user["id"]


def test_auth14_send_new_login_from_order_card(client, conn):
    """AUTH-14: one tap from the order card gives a new starter PIN and goes back to the board."""
    setup_admin(client)
    c = make_customer(conn)  # has chosen their own PIN
    make_order(conn, c, delivery_date="2099-01-05")
    page = page_text(client.get("/admin?tab=upcoming"))
    assert "Has their own PIN" in page and "Send new login" in page
    r = post(client, f"/admin/customers/{c['id']}/reset-pin?next=/admin?tab=upcoming", page="/admin")
    assert r.status_code == 200 and 'href="/admin?tab=upcoming"' in r.text
    pin = auth.get_user(conn, c["id"])["starter_pin"]
    assert pin and pin in r.text
