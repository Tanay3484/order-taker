"""Setup, login, logout, change PIN (002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import auth, db
from .deps import check_csrf, current_user, get_conn, render, require_customer_any, sign_in

router = APIRouter()


def _home_for(user) -> str:
    if user is None:
        return "/login"
    return "/admin" if user["role"] == "admin" else "/my-orders"


@router.get("/")
def home(request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    if not auth.admin_exists(conn) and not _setup_locked(request):
        return RedirectResponse("/setup", 303)
    return RedirectResponse(_home_for(user), 303)


# ---- AUTH-1: one-time setup ----

def _setup_locked(request: Request) -> bool:
    """HOST-1: when the admin comes from env vars, nobody can claim the shop through /setup."""
    return request.app.state.settings.env_admin


@router.get("/setup")
def setup_page(request: Request, conn=Depends(get_conn)):
    if auth.admin_exists(conn) or _setup_locked(request):
        raise HTTPException(404)
    return render(request, conn, "setup.html", errors=[], form={})


@router.post("/setup", dependencies=[Depends(check_csrf)])
def setup_submit(request: Request, conn=Depends(get_conn), name: str = Form(""), username: str = Form(""),
                 password: str = Form(""), shop_name: str = Form(""), shop_whatsapp: str = Form("")):
    if auth.admin_exists(conn) or _setup_locked(request):
        raise HTTPException(404)
    errors = []
    if not name.strip():
        errors.append("Please enter your name.")
    if len(username.strip()) < 3:
        errors.append("Pick a username with at least 3 letters.")
    if len(password) < 8:
        errors.append("The password needs at least 8 characters.")
    if not shop_name.strip():
        errors.append("Please enter your shop's name.")
    if not auth.normalise_phone(shop_whatsapp):
        errors.append("The shop's WhatsApp number: " + auth.PHONE_RULE)
    if errors:
        form = dict(name=name, username=username, shop_name=shop_name, shop_whatsapp=shop_whatsapp)
        return render(request, conn, "setup.html", status_code=400, errors=errors, form=form)
    with db.transaction(conn, immediate=True):
        if auth.admin_exists(conn):  # two tabs racing the setup page
            raise HTTPException(404)
        uid = auth.create_admin(conn, name, username, password)
        db.set_setting(conn, "shop_name", shop_name.strip())
        db.set_setting(conn, "shop_whatsapp", auth.normalise_phone(shop_whatsapp))
    sign_in(request, auth.get_user(conn, uid))
    return RedirectResponse("/admin", 303)


# ---- AUTH-2: login ----

@router.get("/login")
def login_page(request: Request, conn=Depends(get_conn), user=Depends(current_user), tab: str = "customer"):
    if not auth.admin_exists(conn) and not _setup_locked(request):
        return RedirectResponse("/setup", 303)
    if user is not None:
        return RedirectResponse(_home_for(user), 303)
    return render(request, conn, "login.html", tab="admin" if tab == "admin" else "customer", error="", ident="")


@router.post("/login", dependencies=[Depends(check_csrf)])
def login_submit(request: Request, conn=Depends(get_conn), kind: str = Form("customer"),
                 ident: str = Form(""), secret: str = Form("")):
    kind = "admin" if kind == "admin" else "customer"
    try:
        user = auth.login(conn, kind, ident, secret)
    except auth.LoginError as e:
        return render(request, conn, "login.html", status_code=400, tab=kind, error=str(e), ident=ident)
    sign_in(request, user)
    if user["role"] == "customer" and user["must_change_pin"]:
        return RedirectResponse("/change-pin", 303)
    return RedirectResponse(_home_for(user), 303)


@router.post("/logout", dependencies=[Depends(check_csrf)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 303)


# ---- AUTH-6: change PIN ----

@router.get("/change-pin")
def change_pin_page(request: Request, conn=Depends(get_conn), user=Depends(require_customer_any)):
    return render(request, conn, "change_pin.html", user=user, error="", forced=bool(user["must_change_pin"]))


@router.post("/change-pin", dependencies=[Depends(check_csrf)])
def change_pin_submit(request: Request, conn=Depends(get_conn), user=Depends(require_customer_any),
                      pin: str = Form(""), pin2: str = Form("")):
    error = ""
    if not auth.valid_new_pin(pin):
        error = "Your PIN needs to be 4 to 6 numbers."
    elif pin != pin2:
        error = "The two PINs don't match."
    if error:
        return render(request, conn, "change_pin.html", status_code=400, user=user, error=error,
                      forced=bool(user["must_change_pin"]))
    auth.change_pin(conn, user["id"], pin)
    return RedirectResponse("/my-orders?msg=pin", 303)
