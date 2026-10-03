"""Admin pages: board, intake + drafts, customer changes, customers, settings (003, 004, 005)."""

from __future__ import annotations

import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse

from .. import auth, db
from .. import orders as om
from ..agents import master
from ..models import Order, OrderItem
from .deps import check_csrf, get_conn, render, require_admin

router = APIRouter(prefix="/admin")

TABS = [("today", "Today"), ("tomorrow", "Tomorrow"), ("upcoming", "Upcoming"), ("nodate", "No date"), ("past", "Past")]
HELPER_DOWN = "The AI helper isn't running. Open the Ollama app and try again."  # PLT-6


# ---------- helpers ----------

def order_from_form(form, base: Order | None = None) -> Order:
    """Build an Order from the shared order form (admin and customer)."""
    names, qtys, units = form.getlist("item_name"), form.getlist("item_qty"), form.getlist("item_unit")
    items = []
    for n, q, u in zip(names, qtys, units):
        if not str(n).strip():
            continue
        try:
            qty = float(str(q).strip() or "1")
        except ValueError:
            qty = 0
        items.append(OrderItem(name=str(n).strip(), quantity=qty, unit=str(u).strip()))
    pickup = form.get("pickup") == "on"
    return Order(
        customer=str(form.get("customer", base.customer if base else "")).strip(),
        phone=str(form.get("phone", base.phone if base else "")).strip(),
        items=items,
        delivery_date=str(form.get("delivery_date", "")).strip(),
        delivery_time=str(form.get("delivery_time", "")).strip(),
        address="" if pickup else str(form.get("address", "")).strip(),
        notes=str(form.get("notes", "")).strip(),
    )


def login_message(name: str, url: str, pin: str) -> str:
    return f"Hi {name}, you can track your order at {url}. Login: your phone number, PIN {pin}"


def order_view(conn, row, public_url: str = "") -> dict:
    customer = auth.get_user(conn, row["customer_id"]) if row["customer_id"] else None
    starter = customer["starter_pin"] if customer is not None else None
    return {
        "row": row,
        "customer": customer,
        "login_msg": login_message(customer["name"] or row["customer_name"], public_url, starter) if starter else "",
        "items": om.get_items(conn, row["id"]),
        "badges": om.order_badges(conn, row["id"]),
        "can_undo": om.can_undo(conn, row["id"]),
        "next": om.NEXT_ACTION.get(row["status"]),
        "can_cancel": om.can_cancel(row["status"]),
    }


def draft_view(conn, d) -> dict:
    order = om.draft_order(d)
    target = om.get_order(conn, d["target_order_id"]) if d["target_order_id"] else None
    current = om.to_model(conn, target) if target else None
    return {
        "d": d,
        "order": order,
        "target": target,
        "current": current,
        "changes": om.diff(current, order) if d["action"] == "update" else [],
        "flags": json.loads(d["flags_json"] or "[]") + om.conflict_flags(conn, d),
    }


def change_view(conn, d) -> dict:
    """TRK-25: pending requests diff against the current order; applied ones against the snapshot."""
    v = draft_view(conn, d)
    before = Order.model_validate_json(d["before_json"]) if d["before_json"] else None
    if d["state"] == "applied":
        v["changes"] = om.diff(before, v["order"]) if d["action"] == "update" else []
    return v


def _back(request: Request, default: str) -> str:
    nxt = request.query_params.get("next", "")
    return nxt if nxt.startswith("/admin") else default


def _error(request, conn, user, message: str, back: str):
    return render(request, conn, "message.html", status_code=400, user=user, title="That didn't work",
                  message=message, back=back)


# ---------- board (TRK-7, TRK-8, TRK-24) ----------

@router.get("")
def board(request: Request, tab: str = "today", conn=Depends(get_conn), user=Depends(require_admin)):
    tab = tab if tab in dict(TABS) else "today"
    rows = om.orders_in_tab(conn, tab)
    changes = [change_view(conn, d) for d in om.customer_changes(conn)]
    return render(request, conn, "admin_board.html", user=user, tab=tab, tabs=TABS,
                  orders=[order_view(conn, r, request.app.state.public_url) for r in rows], changes=changes,
                  pending_drafts=len(om.pending_chat_drafts(conn)))


@router.post("/orders/{order_id}/advance", dependencies=[Depends(check_csrf)])
def advance(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    try:
        om.advance(conn, order_id, user["id"])
    except om.OrderError as e:
        return _error(request, conn, user, str(e), "/admin")
    return RedirectResponse(_back(request, "/admin"), 303)


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(check_csrf)])
def cancel(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    try:
        om.cancel(conn, order_id, user["id"], "Cancelled by the shop")
    except om.OrderError as e:
        return _error(request, conn, user, str(e), "/admin")
    return RedirectResponse(_back(request, "/admin"), 303)


@router.post("/orders/{order_id}/undo", dependencies=[Depends(check_csrf)])
def undo(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    try:
        om.undo_last(conn, order_id, user["id"])
    except om.OrderError as e:
        return _error(request, conn, user, str(e), "/admin")
    return RedirectResponse(_back(request, "/admin"), 303)


@router.get("/orders/{order_id}/edit")
def edit_order_page(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    row = om.get_order(conn, order_id)
    if row is None:
        raise HTTPException(404)
    return render(request, conn, "admin_order_edit.html", user=user, row=row, order=om.to_model(conn, row),
                  history=om.history(conn, order_id), errors=[])


@router.post("/orders/{order_id}/edit", dependencies=[Depends(check_csrf)])
async def edit_order_submit(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    row = om.get_order(conn, order_id)
    if row is None:
        raise HTTPException(404)
    form = await request.form()
    order = order_from_form(form, om.to_model(conn, row))
    errors = [] if order.items else ["An order needs at least one item."]
    if errors:
        return render(request, conn, "admin_order_edit.html", status_code=400, user=user, row=row, order=order,
                      history=om.history(conn, order_id), errors=errors)
    om.admin_edit(conn, order_id, order, str(form.get("admin_note", "")), user["id"])
    return RedirectResponse("/admin", 303)


@router.post("/orders/{order_id}/phone", dependencies=[Depends(check_csrf)])
def add_phone(request: Request, order_id: int, phone: str = Form(""), conn=Depends(get_conn),
              user=Depends(require_admin)):
    """AUTH-5: add a phone later."""
    try:
        pin = om.link_phone(conn, order_id, phone)
    except om.OrderError as e:
        return _error(request, conn, user, str(e), f"/admin/orders/{order_id}/edit")
    row = om.get_order(conn, order_id)
    if pin:
        return _pin_page(request, conn, user, row["customer_name"], row["phone"], pin)
    return RedirectResponse(f"/admin/orders/{order_id}/edit", 303)


def _pin_page(request, conn, user, name: str, phone: str, pin: str, back: str = "/admin"):
    """AUTH-4: show the PIN once, with a ready-to-send WhatsApp message."""
    message = login_message(name, request.app.state.public_url, pin)
    return render(request, conn, "pin_reveal.html", user=user, name=name, phone=phone, pin=pin,
                  message=message, back=back)


# ---------- intake (003, 004) ----------

@router.get("/intake")
async def intake_page(request: Request, run: int | None = None, conn=Depends(get_conn), user=Depends(require_admin)):
    healthy = await request.app.state.ollama.healthy()
    active = master.active_run()
    run_id = run or (active.id if active else None)
    last = None
    if run_id is None:
        last = conn.execute("SELECT * FROM intake_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    drafts = [draft_view(conn, d) for d in om.pending_chat_drafts(conn)]
    return render(request, conn, "admin_intake.html", user=user, helper_error="" if healthy else HELPER_DOWN,
                  run_id=run_id, running=active is not None, last=last, drafts=drafts,
                  sample_chat=request.app.state.sample_chat)


@router.post("/intake", dependencies=[Depends(check_csrf)])
async def intake_start(request: Request, text: str = Form(""), file: UploadFile | None = File(None),
                       conn=Depends(get_conn), user=Depends(require_admin)):
    if file is not None and file.filename:
        text = (await file.read()).decode("utf-8", errors="ignore")
    if not text.strip():
        return _error(request, conn, user, "Paste some messages or upload an exported chat first.", "/admin/intake")
    if len(text) > request.app.state.settings.max_chat_chars:  # HOST-7
        return _error(request, conn, user, "That's a very long chat. Please paste just the recent messages.",
                      "/admin/intake")
    client = request.app.state.ollama
    if not await client.healthy():  # PLT-6
        return _error(request, conn, user, HELPER_DOWN, "/admin/intake")
    s = request.app.state.settings
    run = master.start_run(s.db_path, client, s.model, s.sorter_model, text, user["id"])
    return RedirectResponse(f"/admin/intake?run={run.id}", 303)


@router.get("/intake/{run_id}/events")
async def intake_events(request: Request, run_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    """PRG-8: SSE with replay from Last-Event-ID. Admin only (PRG-10)."""
    try:
        after = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        after = 0
    run = master.RUNS.get(run_id)
    saved = conn.execute("SELECT summary FROM intake_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None and saved is None:
        raise HTTPException(404)

    async def stream():
        if run is None:  # server restarted since: show the saved summary
            data = json.dumps({"seq": 1, "kind": "summary", "text": saved["summary"], "finished": True,
                               "done_count": 0, "total_count": 0})
            yield f"id: 1\nevent: progress\ndata: {data}\n\n"
        else:
            async for ev in run.feed.stream(after):
                yield f"id: {ev.seq}\nevent: progress\ndata: {ev.model_dump_json()}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/drafts/{draft_id}/card")
def draft_card(request: Request, draft_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    d = om.get_draft(conn, draft_id)
    if d is None or d["source"] != "chat":
        raise HTTPException(404)
    if d["state"] != "pending":
        return Response("")
    return render(request, conn, "_draft_card.html", user=user, v=draft_view(conn, d))


def _accept(request, conn, user, draft_id: int, force: bool, edited: Order | None, back: str):
    try:
        result = om.apply_draft(conn, draft_id, user["id"], force=force, edited=edited)
    except om.NeedsConfirm as e:
        return render(request, conn, "confirm.html", user=user, message=str(e),
                      action=f"/admin/drafts/{draft_id}/accept?next={back}", back=back)
    except om.OrderError as e:
        return _error(request, conn, user, str(e), back)
    if result.new_pin:
        return _pin_page(request, conn, user, result.customer_name, result.phone, result.new_pin, back)
    if result.order_id and not result.phone:
        return render(request, conn, "message.html", user=user, title="Order saved",
                      message="No phone – customer can't track this. You can add their number from the order's Edit page.",
                      back=back, link=f"/admin/orders/{result.order_id}/edit", link_text="Add their phone number")
    return RedirectResponse(back, 303)


@router.post("/drafts/{draft_id}/accept", dependencies=[Depends(check_csrf)])
def accept_draft(request: Request, draft_id: int, force: str = Form(""), conn=Depends(get_conn),
                 user=Depends(require_admin)):
    return _accept(request, conn, user, draft_id, force == "1", None, _back(request, "/admin/intake"))


@router.get("/drafts/{draft_id}/edit")
def edit_draft_page(request: Request, draft_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    d = om.get_draft(conn, draft_id)
    if d is None or d["state"] != "pending" or d["action"] not in ("new", "update"):
        raise HTTPException(404)
    v = draft_view(conn, d)
    order = v["order"] or v["current"] or Order(customer=d["sender"], items=[])
    return render(request, conn, "admin_draft_edit.html", user=user, v=v, order=order, errors=[])


@router.post("/drafts/{draft_id}/edit", dependencies=[Depends(check_csrf)])
async def edit_draft_submit(request: Request, draft_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    d = om.get_draft(conn, draft_id)
    if d is None or d["state"] != "pending":
        raise HTTPException(404)
    form = await request.form()
    order = order_from_form(form)
    v = draft_view(conn, d)
    if not order.items:
        return render(request, conn, "admin_draft_edit.html", status_code=400, user=user, v=v, order=order,
                      errors=["An order needs at least one item."])
    force = form.get("force") == "1"
    if v["target"] is not None and v["target"]["status"] in ("preparing", "ready") and not force:
        # TRK-2: ask on this form so the edits aren't lost
        return render(request, conn, "admin_draft_edit.html", user=user, v=v, order=order, errors=[],
                      confirm="This order is already being made. Apply the change anyway?")
    return _accept(request, conn, user, draft_id, force, order, "/admin/intake")


@router.post("/drafts/{draft_id}/discard", dependencies=[Depends(check_csrf)])
def discard_draft(request: Request, draft_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    try:
        om.discard_draft(conn, draft_id)
    except om.OrderError as e:
        return _error(request, conn, user, str(e), "/admin/intake")
    return RedirectResponse("/admin/intake", 303)


# ---------- customer changes (TRK-22, TRK-24, TRK-25) ----------

@router.get("/changes")
def changes_page(request: Request, conn=Depends(get_conn), user=Depends(require_admin)):
    changes = [change_view(conn, d) for d in om.customer_changes(conn)]
    return render(request, conn, "admin_changes.html", user=user, changes=changes)


@router.post("/changes/{draft_id}/approve", dependencies=[Depends(check_csrf)])
def approve_change(request: Request, draft_id: int, force: str = Form(""), conn=Depends(get_conn),
                   user=Depends(require_admin)):
    back = _back(request, "/admin")
    try:
        om.decide_request(conn, draft_id, user["id"], approve=True, force=force == "1")
    except om.NeedsConfirm as e:
        return render(request, conn, "confirm.html", user=user, message=str(e),
                      action=f"/admin/changes/{draft_id}/approve?next={back}", back=back)
    except om.OrderError as e:
        return _error(request, conn, user, str(e), back)
    return RedirectResponse(back, 303)


@router.post("/changes/{draft_id}/decline", dependencies=[Depends(check_csrf)])
def decline_change(request: Request, draft_id: int, reason: str = Form(""), conn=Depends(get_conn),
                   user=Depends(require_admin)):
    back = _back(request, "/admin")
    try:
        om.decide_request(conn, draft_id, user["id"], approve=False, reason=reason)
    except om.OrderError as e:
        return _error(request, conn, user, str(e), back)
    return RedirectResponse(back, 303)


@router.post("/changes/{draft_id}/seen", dependencies=[Depends(check_csrf)])
def seen_change(request: Request, draft_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    om.mark_seen(conn, draft_id)
    return RedirectResponse(_back(request, "/admin"), 303)


# ---------- prep + CSV (TRK-9) ----------

@router.get("/prep")
def prep(request: Request, day: str = "", conn=Depends(get_conn), user=Depends(require_admin)):
    day = day if om.parse_date(day) else date.today().isoformat()
    return render(request, conn, "admin_prep.html", user=user, day=day, rows=om.prep_rows(conn, day))


@router.get("/orders.csv")
def orders_csv(tab: str = "today", conn=Depends(get_conn), user=Depends(require_admin)):
    tab = tab if tab in dict(TABS) else "today"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order", "customer", "phone", "items", "date", "time", "address", "notes", "status"])
    for r in om.orders_in_tab(conn, tab):
        w.writerow([r["id"], r["customer_name"], r["phone"], om.items_text(om.get_items(conn, r["id"])),
                    r["delivery_date"], r["delivery_time"], r["address"] or "Pickup", r["notes"],
                    om.ADMIN_LABEL[r["status"]]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="orders-{tab}-{date.today()}.csv"'})


# ---------- customers + settings (TRK-10, TRK-11, AUTH-8) ----------

@router.get("/customers")
def customers(request: Request, conn=Depends(get_conn), user=Depends(require_admin)):
    rows = conn.execute(
        "SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.customer_id = u.id) AS order_count "
        "FROM users u WHERE role = 'customer' ORDER BY name"
    ).fetchall()
    return render(request, conn, "admin_customers.html", user=user, customers=rows)


@router.post("/customers/{customer_id}/reset-pin", dependencies=[Depends(check_csrf)])
def reset_pin(request: Request, customer_id: int, conn=Depends(get_conn), user=Depends(require_admin)):
    c = auth.get_user(conn, customer_id)
    if c is None or c["role"] != "customer":
        raise HTTPException(404)
    pin = auth.reset_pin(conn, customer_id)  # AUTH-8, AUTH-14
    return _pin_page(request, conn, user, c["name"], c["phone"], pin, _back(request, "/admin/customers"))


@router.get("/settings")
def settings_page(request: Request, conn=Depends(get_conn), user=Depends(require_admin)):
    return render(request, conn, "admin_settings.html", user=user, errors=[], saved=False,
                  shop_whatsapp=db.get_setting(conn, "shop_whatsapp"))


@router.post("/settings", dependencies=[Depends(check_csrf)])
def settings_submit(request: Request, shop_name: str = Form(""), shop_whatsapp: str = Form(""),
                    conn=Depends(get_conn), user=Depends(require_admin)):
    errors = []
    if not shop_name.strip():
        errors.append("Please enter your shop's name.")
    if not auth.normalise_phone(shop_whatsapp):
        errors.append("Please enter the shop's WhatsApp number.")
    if not errors:
        db.set_setting(conn, "shop_name", shop_name.strip())
        db.set_setting(conn, "shop_whatsapp", auth.normalise_phone(shop_whatsapp))
    return render(request, conn, "admin_settings.html", status_code=400 if errors else 200, user=user,
                  errors=errors, saved=not errors, shop_whatsapp=shop_whatsapp)
