"""005 Customer edits (TRK-17..28)."""

from datetime import date, timedelta

import pytest

from order_taker import orders as om
from order_taker.models import Order, OrderItem

from .conftest import (admin_id, get_csrf, login_admin, login_customer, make_customer, make_order, page_text, post,
                       setup_admin)

FUTURE = (date.today() + timedelta(days=3)).isoformat()


def form(items=(("chocolate cake", "2", "kg"),), date_=FUTURE, time_="5 pm", address="14B Lakeview", notes="",
         pickup=False, **extra):
    data = {"item_name": [i[0] for i in items], "item_qty": [i[1] for i in items], "item_unit": [i[2] for i in items],
            "delivery_date": date_, "delivery_time": time_, "address": address, "notes": notes}
    if pickup:
        data["pickup"] = "on"
    data.update(extra)
    return data


@pytest.fixture
def priya(client, conn):
    setup_admin(client)
    client.cookies.clear()
    p = make_customer(conn)
    login_customer(client)
    return p


def change(client, oid, data):
    data = dict(data, csrf=get_csrf(client, f"/my-orders/{oid}/change"))
    return client.post(f"/my-orders/{oid}/change", data=data, follow_redirects=False)


def cancel(client, oid):
    return post(client, f"/my-orders/{oid}/cancel", page=f"/my-orders/{oid}/cancel")


# ---------- editing ----------

def test_trk17_customer_can_edit_items_date_time_address_notes(client, conn, priya):
    """TRK-17, TRK-19: received orders change straight away."""
    oid = make_order(conn, priya)
    r = change(client, oid, form(items=(("chocolate cake", "2", "kg"), ("cupcakes", "6", "pcs")),
                                 notes="eggless", pickup=True))
    assert r.headers["location"] == "/my-orders?msg=applied"
    row = om.get_order(conn, oid)
    assert om.items_text(om.get_items(conn, oid)) == "2 kg chocolate cake, 6 pcs cupcakes"
    assert (row["delivery_date"], row["delivery_time"], row["address"], row["notes"]) == (FUTURE, "5 pm", "", "eggless")
    assert "Done, your order is updated." in page_text(client.get(r.headers["location"]))


def test_trk17_name_and_phone_cannot_be_changed(client, conn, priya):
    oid = make_order(conn, priya)
    change(client, oid, form(customer="Hacker", phone="9000000000"))
    row = om.get_order(conn, oid)
    assert row["customer_name"] == "Priya" and row["phone"] == "9845012345"


@pytest.mark.parametrize("data, message", [
    (form(items=(("", "", ""),)), "Please keep at least one item."),
    (form(items=(("cake", "0", "kg"),)), "Quantities need to be more than zero."),
    (form(date_=(date.today() - timedelta(days=1)).isoformat()), "The date can't be in the past."),
])
def test_trk17_validation_in_plain_english(client, conn, priya, data, message):
    oid = make_order(conn, priya)
    r = change(client, oid, data)
    assert r.status_code == 400 and message in page_text(r)
    assert om.items_text(om.get_items(conn, oid)) == "1 kg chocolate cake"


def test_trk18_cancel_with_confirmation_step(client, conn, priya):
    """TRK-18, TRK-19."""
    oid = make_order(conn, priya)
    assert "Cancel this order?" in page_text(client.get(f"/my-orders/{oid}/cancel"))
    r = cancel(client, oid)
    assert r.headers["location"] == "/my-orders?msg=cancel_applied"
    assert om.get_order(conn, oid)["status"] == "cancelled"


def test_trk19_history_says_changed_by_customer(client, conn, priya):
    """TRK-19, TRK-28."""
    oid = make_order(conn, priya)
    change(client, oid, form())
    last = om.history(conn, oid)[-1]
    assert last["note"] == "Changed by customer in the app" and last["changed_by"] == priya["id"]


# ---------- requests ----------

def test_trk20_confirmed_order_change_is_a_request(client, conn, priya):
    """TRK-20: order unchanged; customer sees it's waiting."""
    oid = make_order(conn, priya, status="confirmed")
    r = change(client, oid, form())
    assert r.headers["location"] == "/my-orders?msg=requested"
    assert om.items_text(om.get_items(conn, oid)) == "1 kg chocolate cake"
    page = page_text(client.get("/my-orders"))
    assert "Change requested. Waiting for Asha's Bakes to approve." in page


def test_trk20_cancel_of_confirmed_order_is_a_request(client, conn, priya):
    oid = make_order(conn, priya, status="ready")
    assert cancel(client, oid).headers["location"] == "/my-orders?msg=cancel_requested"
    assert om.get_order(conn, oid)["status"] == "ready"


def test_trk21_one_pending_request_replace_and_withdraw(client, conn, priya):
    """TRK-21."""
    oid = make_order(conn, priya, status="confirmed")
    change(client, oid, form(notes="first"))
    change(client, oid, form(notes="second"))
    pending = conn.execute("SELECT * FROM drafts WHERE state = 'pending'").fetchall()
    assert len(pending) == 1 and om.draft_order(pending[0]).notes == "second"
    assert "second" in client.get(f"/my-orders/{oid}/change").text  # editing again starts from the request
    post(client, f"/my-orders/requests/{pending[0]['id']}/withdraw", page="/my-orders")
    assert om.get_draft(conn, pending[0]["id"])["state"] == "withdrawn"
    assert "Waiting for" not in page_text(client.get("/my-orders"))


def test_trk22_approve_applies_and_customer_sees_it(client, conn, priya):
    """TRK-22: approve."""
    oid = make_order(conn, priya, status="confirmed")
    change(client, oid, form(notes="eggless"))
    d = conn.execute("SELECT id FROM drafts WHERE state = 'pending'").fetchone()[0]
    om.decide_request(conn, d, admin_id(conn), approve=True)
    assert om.get_order(conn, oid)["notes"] == "eggless"
    assert "Your change was approved." in page_text(client.get("/my-orders"))


def test_trk22_decline_with_reason(client, conn, priya):
    """TRK-22: decline, with the reason shown to the customer."""
    oid = make_order(conn, priya, status="confirmed")
    change(client, oid, form(notes="eggless"))
    d = conn.execute("SELECT id FROM drafts WHERE state = 'pending'").fetchone()[0]
    om.decide_request(conn, d, admin_id(conn), approve=False, reason="Already baked, sorry!")
    assert om.get_order(conn, oid)["notes"] == ""
    page = page_text(client.get("/my-orders"))
    assert "Your change wasn't approved." in page and "Already baked, sorry!" in page


def test_trk23_status_checked_when_saving_not_when_opening(client, conn, priya):
    """TRK-23: form opened while 'received', admin confirms, save becomes a request."""
    oid = make_order(conn, priya)
    token = get_csrf(client, f"/my-orders/{oid}/change")
    assert "saved straight away" in client.get(f"/my-orders/{oid}/change").text
    om.advance(conn, oid, admin_id(conn))
    r = client.post(f"/my-orders/{oid}/change", data=dict(form(notes="late"), csrf=token), follow_redirects=False)
    assert r.headers["location"] == "/my-orders?msg=requested"
    assert om.get_order(conn, oid)["notes"] == ""


def test_trk23_finished_orders_cannot_be_changed(client, conn, priya):
    oid = make_order(conn, priya, status="delivered")
    assert "Change order" not in client.get("/my-orders").text
    r = change(client, oid, form())
    assert r.status_code == 400 and "finished" in page_text(r)


# ---------- admin side ----------

def _as_admin(client):
    client.cookies.clear()
    login_admin(client)


def test_trk24_trk25_changes_section_badge_and_diff(client, conn, priya):
    """TRK-24, TRK-25: pending first, old -> new line by line, count in the nav."""
    applied_oid = make_order(conn, priya)
    change(client, applied_oid, form(items=(("chocolate cake", "1", "kg"), ("cupcakes", "6", "pcs"))))
    req_oid = make_order(conn, priya, status="confirmed")
    change(client, req_oid, form(items=(("chocolate cake", "2", "kg"),), date_=FUTURE))
    _as_admin(client)
    page = " ".join(page_text(client.get("/admin")).split())
    assert "Customer changes" in page and 'aria-label="2 customer changes"' in page
    assert page.index("asks to change") < page.index("changed order")  # pending first
    assert "Item added" in page and "6 pcs cupcakes" in page
    assert "Item changed" in page and "1 kg chocolate cake" in page and "2 kg chocolate cake" in page
    assert "Approve" in page and "Decline" in page and "Got it" in page


def test_trk25_got_it_marks_seen(client, conn, priya):
    oid = make_order(conn, priya)
    change(client, oid, form())
    d = conn.execute("SELECT id FROM drafts").fetchone()[0]
    _as_admin(client)
    post(client, f"/admin/changes/{d}/seen?next=/admin", page="/admin")
    assert om.changes_badge(conn) == 0


def test_trk22_admin_approve_and_decline_buttons(client, conn, priya):
    a = make_order(conn, priya, status="confirmed")
    b = make_order(conn, priya, status="confirmed", items=(("ladoo", 24, ""),))
    change(client, a, form(notes="approve me"))
    change(client, b, form(items=(("ladoo", "30", ""),), notes="decline me"))
    da, db_ = [r[0] for r in conn.execute("SELECT id FROM drafts ORDER BY id")]
    _as_admin(client)
    post(client, f"/admin/changes/{da}/approve?next=/admin", page="/admin")
    post(client, f"/admin/changes/{db_}/decline?next=/admin", {"reason": "Too late"}, page="/admin")
    assert om.get_order(conn, a)["notes"] == "approve me"
    assert om.get_order(conn, b)["notes"] == ""
    assert om.get_draft(conn, db_)["decline_reason"] == "Too late"


def test_trk22_approving_change_to_preparing_order_asks_first(client, conn, priya):
    oid = make_order(conn, priya, status="preparing")
    change(client, oid, form(notes="eggless"))
    d = conn.execute("SELECT id FROM drafts").fetchone()[0]
    _as_admin(client)
    r = post(client, f"/admin/changes/{d}/approve?next=/admin", page="/admin")
    assert "already being made" in page_text(r)
    post(client, f"/admin/changes/{d}/approve?next=/admin", {"force": "1"}, page="/admin")
    assert om.get_order(conn, oid)["notes"] == "eggless"


def test_trk26_board_badges(client, conn, priya):
    """TRK-26."""
    changed = make_order(conn, priya, delivery_date=date.today().isoformat())
    change(client, changed, form(date_=date.today().isoformat()))
    requested = make_order(conn, priya, status="confirmed", delivery_date=date.today().isoformat())
    change(client, requested, form(date_=date.today().isoformat(), notes="x"))
    assert om.order_badges(conn, changed) == ["Changed by customer"]
    assert om.order_badges(conn, requested) == ["Change requested"]
    _as_admin(client)
    page = client.get("/admin").text
    assert "Changed by customer" in page and "Change requested" in page


def test_trk27_conflict_between_chat_and_app_change(client, conn, priya):
    """TRK-27."""
    oid = make_order(conn, priya, status="confirmed")
    change(client, oid, form(notes="from the app"))
    current = om.to_model(conn, om.get_order(conn, oid))
    chat = om.save_draft(conn, source="chat", action="update", target_order_id=oid, sender="Priya",
                         order=current.model_copy(update={"notes": "from WhatsApp"}))
    app_req = conn.execute("SELECT * FROM drafts WHERE source = 'customer'").fetchone()
    flag = "There's another change waiting for this order."
    assert flag in om.conflict_flags(conn, om.get_draft(conn, chat))
    assert flag in om.conflict_flags(conn, app_req)
    _as_admin(client)
    assert flag in page_text(client.get("/admin")) and flag in page_text(client.get("/admin/intake"))


def test_trk28_requests_logged_in_history(client, conn, priya):
    """TRK-28."""
    oid = make_order(conn, priya, status="confirmed")
    cancel(client, oid)
    d = conn.execute("SELECT id FROM drafts").fetchone()[0]
    om.decide_request(conn, d, admin_id(conn), approve=True)
    last = om.history(conn, oid)[-1]
    assert last["status"] == "cancelled" and last["note"] == "Cancelled by customer in the app"


def test_diff_lists_only_what_changed():
    before = Order(customer="P", items=[OrderItem(name="cake", quantity=1, unit="kg"),
                                        OrderItem(name="ladoo", quantity=12)], delivery_date="2099-01-01",
                   address="14B")
    after = Order(customer="P", items=[OrderItem(name="Cake", quantity=2, unit="kg"),
                                       OrderItem(name="cupcakes", quantity=6, unit="pcs")],
                  delivery_date="2099-01-01", address="")
    labels = [(c.label, c.old, c.new) for c in om.diff(before, after)]
    assert ("Address", "14B", "Pickup") in labels
    assert ("Item changed", "1 kg cake", "2 kg Cake") in labels
    assert ("Item removed", "12 ladoo", "—") in labels
    assert ("Item added", "—", "6 pcs cupcakes") in labels
    assert not any(label == "Date" for label, _, _ in labels)
