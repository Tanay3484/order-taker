"""005 Order tracking: lifecycle, admin board, customer view."""

from datetime import date, datetime, timedelta

import pytest

from order_taker import orders as om
from order_taker.models import Order, OrderItem

from .conftest import (admin_id, login_customer, make_customer, make_order, page_text, post, setup_admin,
                       visible_text)


def _draft(conn, action="new", target=None, order=None, sender="Priya"):
    order = order if order is not None or action == "cancel" else Order(
        customer=sender, phone="9845012345", items=[OrderItem(name="cake", quantity=1, unit="kg")],
        delivery_date="2099-01-05")
    return om.save_draft(conn, source="chat", action=action, order=order, target_order_id=target, sender=sender)


# ---------- lifecycle ----------

def test_trk1_accepting_new_draft_creates_received_order(conn, app):
    """TRK-1."""
    res = om.apply_draft(conn, _draft(conn), None)
    row = om.get_order(conn, res.order_id)
    assert row["status"] == "received" and row["customer_id"] is not None and res.new_pin


def test_trk2_update_keeps_status_and_logs(conn, app):
    """TRK-2."""
    oid = make_order(conn, make_customer(conn), status="confirmed")
    new = om.to_model(conn, om.get_order(conn, oid)).model_copy(update={"notes": "eggless"})
    om.apply_draft(conn, _draft(conn, "update", oid, new), None)
    row = om.get_order(conn, oid)
    assert row["status"] == "confirmed" and row["notes"] == "eggless"
    assert om.history(conn, oid)[-1]["note"].startswith("Changed by customer on WhatsApp")


def test_trk2_update_while_preparing_needs_confirmation(conn, app):
    oid = make_order(conn, make_customer(conn), status="preparing")
    new = om.to_model(conn, om.get_order(conn, oid)).model_copy(update={"notes": "eggless"})
    d = _draft(conn, "update", oid, new)
    with pytest.raises(om.NeedsConfirm, match="already being made"):
        om.apply_draft(conn, d, None)
    assert om.get_order(conn, oid)["notes"] == ""
    om.apply_draft(conn, d, None, force=True)
    assert om.get_order(conn, oid)["notes"] == "eggless"


def test_trk2_confirmation_page_in_web(client, conn):
    setup_admin(client)
    oid = make_order(conn, make_customer(conn), status="preparing")
    new = om.to_model(conn, om.get_order(conn, oid)).model_copy(update={"notes": "eggless"})
    d = _draft(conn, "update", oid, new)
    r = post(client, f"/admin/drafts/{d}/accept", page="/admin/intake")
    assert "This order is already being made. Apply the change anyway?" in page_text(r)
    post(client, f"/admin/drafts/{d}/accept?next=/admin/intake", {"force": "1"}, page="/admin/intake")
    assert om.get_order(conn, oid)["notes"] == "eggless"


def test_trk3_cancel_draft(conn, app):
    """TRK-3."""
    oid = make_order(conn, make_customer(conn))
    om.apply_draft(conn, _draft(conn, "cancel", oid), None)
    assert om.get_order(conn, oid)["status"] == "cancelled"


def test_trk4_forward_one_step_and_cancel_rules(conn, app):
    """TRK-4."""
    oid = make_order(conn)
    for expected in om.FLOW[1:]:
        assert om.advance(conn, oid, None) == expected
    with pytest.raises(om.OrderError):
        om.advance(conn, oid, None)
    with pytest.raises(om.OrderError):
        om.cancel(conn, oid, None)  # delivered can't be cancelled
    other = make_order(conn, status="ready")
    om.cancel(conn, other, None)
    assert om.get_order(conn, other)["status"] == "cancelled"
    with pytest.raises(om.OrderError):
        om.advance(conn, other, None)


def test_trk5_undo_within_five_minutes(conn, app):
    """TRK-5."""
    oid = make_order(conn)
    om.advance(conn, oid, None)
    assert om.undo_last(conn, oid, None) == "received"
    with pytest.raises(om.OrderError):
        om.undo_last(conn, oid, None)  # can't undo the undo
    om.advance(conn, oid, None)
    later = datetime.now() + timedelta(minutes=6)
    assert not om.can_undo(conn, oid, at=later)
    with pytest.raises(om.OrderError, match="5 minutes"):
        om.undo_last(conn, oid, None, at=later)


def test_trk6_history_records_who_and_when(client, conn):
    """TRK-6."""
    setup_admin(client)
    oid = make_order(conn, make_customer(conn))
    post(client, f"/admin/orders/{oid}/advance", page="/admin")
    h = om.history(conn, oid)
    assert [x["status"] for x in h] == ["received", "confirmed"]
    assert h[-1]["changed_by"] == admin_id(conn) and h[-1]["at"]


# ---------- admin board ----------

def test_trk7_tabs(conn, app):
    """TRK-7: Today / Tomorrow / Upcoming / No date / Past."""
    today = date.today()
    ids = {
        "today": make_order(conn, delivery_date=today.isoformat()),
        "tomorrow": make_order(conn, delivery_date=(today + timedelta(days=1)).isoformat()),
        "upcoming": make_order(conn, delivery_date=(today + timedelta(days=5)).isoformat()),
        "nodate": make_order(conn, delivery_date="Sunday"),
        "past": make_order(conn, delivery_date=today.isoformat(), status="delivered"),
    }
    overdue = make_order(conn, delivery_date=(today - timedelta(days=1)).isoformat())
    for tab, oid in ids.items():
        assert oid in [r["id"] for r in om.orders_in_tab(conn, tab)], tab
    assert overdue in [r["id"] for r in om.orders_in_tab(conn, "today")]


def test_trk8_card_has_next_step_and_menu(client, conn):
    """TRK-8."""
    setup_admin(client)
    make_order(conn, make_customer(conn), delivery_date=date.today().isoformat())
    page = page_text(client.get("/admin"))
    assert "Confirm order" in page and "Cancel order" in page and "Edit" in page
    assert "1 kg chocolate cake" in page and "14B Lakeview" in page


def test_trk9_prep_list_excludes_cancelled(client, conn):
    """TRK-9."""
    setup_admin(client)
    make_order(conn, items=(("brownies", 2, "box"),), delivery_date="2099-01-05")
    make_order(conn, items=(("Brownies ", 1, "box"),), delivery_date="2099-01-05")
    make_order(conn, items=(("brownies", 5, "box"),), delivery_date="2099-01-05", status="cancelled")
    assert om.prep_rows(conn, "2099-01-05") == [{"item": "brownies", "unit": "box", "total": "3"}]
    assert "brownies" in client.get("/admin/prep?day=2099-01-05").text


def test_trk10_customer_list(client, conn):
    """TRK-10."""
    setup_admin(client)
    c = make_customer(conn)
    make_order(conn, c)
    page = page_text(client.get("/admin/customers"))
    assert "Priya" in page and "9845012345" in page and "1 order" in page and "Reset PIN" in page


def test_trk11_shop_settings(client, conn):
    """TRK-11: set at setup, editable later."""
    setup_admin(client)
    r = post(client, "/admin/settings", {"shop_name": "Asha's Cakes", "shop_whatsapp": "+91 99000 22222"},
             page="/admin/settings")
    assert r.status_code == 200
    assert "Asha's Cakes" in page_text(client.get("/admin"))


# ---------- customer view ----------

@pytest.fixture
def priya_logged_in(client, conn):
    setup_admin(client)
    client.cookies.clear()
    priya = make_customer(conn)
    login_customer(client)
    return priya


def test_trk12_trk13_active_first_past_collapsed(client, conn, priya_logged_in):
    """TRK-12, TRK-13."""
    make_order(conn, priya_logged_in, items=(("cupcakes", 12, "pcs"),), status="preparing")
    make_order(conn, priya_logged_in, items=(("ladoo", 24, ""),), status="delivered")
    page = page_text(client.get("/my-orders"))
    active, past = page.split("Past orders (1)")
    assert "12 pcs cupcakes" in active and "Being made" in active and 'aria-current="step"' in active
    assert "24 ladoo" in past


def test_trk14_change_button_and_whatsapp_link(client, conn, priya_logged_in):
    """TRK-14."""
    make_order(conn, priya_logged_in)
    page = client.get("/my-orders").text
    assert "Change order" in page and "https://wa.me/919900011111?text=" in page


def test_trk15_updated_time_and_json_refresh(client, conn, priya_logged_in):
    """TRK-15."""
    make_order(conn, priya_logged_in)
    assert "data-ago=" in client.get("/my-orders").text
    data = client.get("/my-orders.json").json()
    assert data["orders"][0]["updated_at"]


def test_trk16_customers_only_see_their_own(client, conn, priya_logged_in):
    """TRK-16 / AUTH-10: no other customer's orders, no admin notes, no phone, no history."""
    mine = make_order(conn, priya_logged_in)
    conn.execute("UPDATE orders SET admin_note = 'SECRET NOTE' WHERE id = ?", (mine,))
    other = make_order(conn, make_customer(conn, "Rahul", "9900011122"), items=(("rahul's brownies", 1, "box"),))
    page = page_text(client.get("/my-orders"))
    assert "rahul's brownies" not in page and "SECRET NOTE" not in page
    data = client.get("/my-orders.json").json()
    assert [o["id"] for o in data["orders"]] == [mine]
    assert not {"admin_note", "phone", "history", "customer_id"} & set(data["orders"][0])
    assert client.get(f"/my-orders/{other}/change").status_code == 404
    assert client.get(f"/my-orders/{other}/cancel").status_code == 404


def test_trk8_card_shows_unused_starter_pin_with_send_buttons(client, conn):
    """TRK-8 / AUTH-13: the starter PIN shows on the order card with Copy and WhatsApp."""
    from order_taker import auth
    setup_admin(client)
    user, pin = auth.ensure_customer(conn, "Sneha", "9845012345")
    make_order(conn, auth.get_user(conn, user["id"]), delivery_date=date.today().isoformat())
    page = page_text(client.get("/admin"))
    assert f"Login PIN {pin} (not used yet)" in visible_text(page)
    assert "Copy message" in page and "https://wa.me/919845012345?text=" in page
    assert f"PIN {pin}" in page  # inside the ready-to-send message


def test_trk10_customer_list_shows_starter_pin(client, conn):
    """TRK-10."""
    from order_taker import auth
    setup_admin(client)
    _, pin = auth.ensure_customer(conn, "Sneha", "9845012345")
    make_customer(conn, "Priya", "9900011122")
    page = visible_text(page_text(client.get("/admin/customers")))
    assert f"Login PIN {pin} (not used yet)" in page and "Has their own PIN" in page
