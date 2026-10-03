"""Customer pages: my orders, change / cancel, requests (005 TRK-12..23).
Every query goes through orders.customer_order(s), which filters by the logged-in customer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .. import db
from .. import orders as om
from .deps import check_csrf, get_conn, render, require_customer
from .routes_admin import order_from_form

router = APIRouter()

FLASH = {
    "applied": "Done, your order is updated.",
    "requested": "Change requested. Waiting for {shop} to approve.",
    "cancel_applied": "Your order is cancelled. {shop} has been told.",
    "cancel_requested": "Cancellation requested. Waiting for {shop} to approve.",
    "withdrawn": "Your request has been withdrawn.",
    "pin": "Your new PIN is saved.",
}


class CustomerOrderView(BaseModel):
    """TRK-16: what a customer may see. No admin note, no phone, no history."""
    id: int
    items: str
    delivery_date: str
    delivery_time: str
    address: str
    notes: str
    status: str
    status_label: str
    step: int
    updated_at: str
    request_state: str
    request_action: str
    request_reason: str
    request_id: int | None
    can_change: bool


def _view(conn, row, customer_id: int) -> CustomerOrderView:
    req = om.latest_customer_request(conn, row["id"], customer_id)
    return CustomerOrderView(
        id=row["id"], items=om.items_text(om.get_items(conn, row["id"])),
        delivery_date=row["delivery_date"], delivery_time=row["delivery_time"],
        address=row["address"], notes=row["notes"], status=row["status"],
        status_label=om.customer_label(row["status"], bool(row["address"])),
        step=om.FLOW.index(row["status"]) if row["status"] in om.FLOW else -1,
        updated_at=om.last_change_at(conn, row["id"]) or row["updated_at"],
        request_state=req["state"] if req else "", request_action=req["action"] if req else "",
        request_reason=req["decline_reason"] if req else "", request_id=req["id"] if req else None,
        can_change=row["status"] in om.OPEN,
    )


def _views(conn, customer_id: int) -> tuple[list[CustomerOrderView], list[CustomerOrderView]]:
    views = [_view(conn, r, customer_id) for r in om.customer_orders(conn, customer_id)]
    active = [v for v in views if v.status in om.OPEN]
    past = sorted((v for v in views if v.status not in om.OPEN), key=lambda v: v.delivery_date, reverse=True)
    return active, past


def _order(conn, user, order_id: int):
    row = om.customer_order(conn, user["id"], order_id)
    if row is None:
        raise HTTPException(404)
    return row


@router.get("/my-orders")
def my_orders(request: Request, msg: str = "", conn=Depends(get_conn), user=Depends(require_customer)):
    active, past = _views(conn, user["id"])
    shop = db.get_setting(conn, "shop_name", "the shop")
    flash = FLASH.get(msg, "").format(shop=shop)
    return render(request, conn, "my_orders.html", user=user, active=active, past=past, flash=flash,
                  shop_whatsapp=db.get_setting(conn, "shop_whatsapp"))


@router.get("/my-orders.json")
def my_orders_json(conn=Depends(get_conn), user=Depends(require_customer)):
    active, past = _views(conn, user["id"])
    return {"orders": [v.model_dump() for v in active + past]}


@router.get("/my-orders/{order_id}/change")
def change_page(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_customer)):
    row = _order(conn, user, order_id)
    if row["status"] not in om.OPEN:
        return RedirectResponse("/my-orders", 303)
    order = om.to_model(conn, row)
    req = om.latest_customer_request(conn, order_id, user["id"])
    if req is not None and req["state"] == "pending" and req["action"] == "update":
        order = om.draft_order(req)  # TRK-21: editing again starts from the pending request
    return render(request, conn, "my_order_change.html", user=user, row=row, order=order, errors=[],
                  immediate=row["status"] == "received")


@router.post("/my-orders/{order_id}/change", dependencies=[Depends(check_csrf)])
async def change_submit(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_customer)):
    row = _order(conn, user, order_id)
    form = await request.form()
    order = order_from_form(form, om.to_model(conn, row))
    try:
        outcome = om.customer_change(conn, order_id, user["id"], order)
    except om.OrderError as e:
        return render(request, conn, "my_order_change.html", status_code=400, user=user, row=row, order=order,
                      errors=[str(e)], immediate=row["status"] == "received")
    return RedirectResponse(f"/my-orders?msg={outcome}", 303)


@router.get("/my-orders/{order_id}/cancel")
def cancel_page(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_customer)):
    row = _order(conn, user, order_id)
    if row["status"] not in om.OPEN:
        return RedirectResponse("/my-orders", 303)
    return render(request, conn, "my_order_cancel.html", user=user, row=row,
                  items=om.items_text(om.get_items(conn, order_id)), immediate=row["status"] == "received")


@router.post("/my-orders/{order_id}/cancel", dependencies=[Depends(check_csrf)])
def cancel_submit(request: Request, order_id: int, conn=Depends(get_conn), user=Depends(require_customer)):
    _order(conn, user, order_id)
    try:
        outcome = om.customer_change(conn, order_id, user["id"], None)
    except om.OrderError as e:
        return render(request, conn, "message.html", status_code=400, user=user, title="That didn't work",
                      message=str(e), back="/my-orders")
    return RedirectResponse(f"/my-orders?msg=cancel_{outcome}", 303)


@router.post("/my-orders/requests/{draft_id}/withdraw", dependencies=[Depends(check_csrf)])
def withdraw(request: Request, draft_id: int, conn=Depends(get_conn), user=Depends(require_customer)):
    try:
        om.withdraw_request(conn, draft_id, user["id"])
    except om.OrderError as e:
        return render(request, conn, "message.html", status_code=400, user=user, title="That didn't work",
                      message=str(e), back="/my-orders")
    return RedirectResponse("/my-orders?msg=withdrawn", 303)
