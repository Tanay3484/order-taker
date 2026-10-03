"""Shared fixtures. Tests never need Ollama or the network: FakeOllama replaces
only the raw HTTP call, so the real retry and concurrency code still runs."""

from __future__ import annotations

import asyncio
import html
import json
import re
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from order_taker import auth, db
from order_taker import orders as om
from order_taker.agents import master
from order_taker.agents.ollama import HelperDown, OllamaClient
from order_taker.config import Settings
from order_taker.models import Order, OrderItem
from order_taker.web.main import create_app

ADMIN_PASSWORD = "bake-it-good"


class FakeOllama(OllamaClient):
    def __init__(self, parallel: int = 3, delay: float = 0.0):
        super().__init__("http://fake-ollama", parallel)
        self.delay = delay
        self.delays: dict[str, float] = {}       # per-sender delay override
        self.sorts: dict[str, str] = {}           # sender -> kind (default new_order)
        self.extracts: dict[str, dict] = {}       # sender -> ExtractResult JSON
        self.bad: dict[str, int] = {}             # sender -> how many extract calls return junk
        self.models = {"qwen2.5:7b", "qwen2.5:3b"}
        self.up = True
        self.calls: list[dict] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def healthy(self) -> bool:
        return self.up

    async def has_model(self, name: str) -> bool:
        if not self.up:
            raise HelperDown()
        return name in self.models

    async def _chat(self, payload: dict) -> str:
        if not self.up:
            raise httpx.ConnectError("down")
        user = payload["messages"][1]["content"]
        sender = user.split("\n", 1)[0].removeprefix("Customer: ")
        is_sort = payload["format"].get("title") == "SortResult"
        self.calls.append({"model": payload["model"], "sender": sender, "sort": is_sort,
                           "system": payload["messages"][0]["content"], "user": user})
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delays.get(sender, self.delay))
        finally:
            self.in_flight -= 1
        if is_sort:
            return json.dumps({"kind": self.sorts.get(sender, "new_order"), "reason": "test"})
        if self.bad.get(sender, 0) > 0:
            self.bad[sender] -= 1
            return "this is not json"
        answer = {"kind": self.sorts.get(sender, "new_order"), "actions": []}
        answer.update(self.extracts.get(sender, {}))
        return json.dumps(answer)

    def extract_calls(self, sender: str | None = None) -> list[dict]:
        return [c for c in self.calls if not c["sort"] and (sender is None or c["sender"] == sender)]


def new_action(customer: str, items: list[tuple[str, float, str]], **fields) -> dict:
    order = {"customer": customer, "items": [{"name": n, "quantity": q, "unit": u} for n, q, u in items]}
    order.update(fields)
    return {"action": "new", "target_order_id": None, "order": order}


@pytest.fixture(autouse=True)
def _reset_master():
    master.RUNS.clear()
    master._active = None
    yield
    master.RUNS.clear()
    master._active = None


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=str(tmp_path / "data" / "test.db"), model="qwen2.5:7b", sorter_model="qwen2.5:3b",
                    ollama_url="http://fake-ollama", parallel=3, port=8000)


@pytest.fixture
def fake() -> FakeOllama:
    return FakeOllama()


@pytest.fixture
def app(settings, fake):
    return create_app(settings, fake)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def conn(app, settings):
    c = db.connect(settings.db_path)
    yield c
    c.close()


# ---------- helpers ----------

def visible_text(page: str) -> str:
    """Page text without tags, whitespace collapsed: what a reader sees."""
    return " ".join(re.sub(r"<[^>]+>", " ", page).split())


def page_text(response) -> str:
    """Response HTML with entities decoded, so plain-English messages can be matched as written."""
    return html.unescape(response.text)


def csrf_from(html: str) -> str:
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, "page has no CSRF token"
    return m.group(1)


def get_csrf(client: TestClient, url: str = "/login") -> str:
    return csrf_from(client.get(url).text)


def post(client: TestClient, url: str, data: dict | None = None, page: str = "/login", **kw):
    data = dict(data or {})
    data.setdefault("csrf", get_csrf(client, page))
    return client.post(url, data=data, follow_redirects=kw.pop("follow_redirects", False), **kw)


def setup_admin(client: TestClient) -> None:
    r = post(client, "/setup", {"name": "Asha", "username": "asha", "password": ADMIN_PASSWORD,
                                "shop_name": "Asha's Bakes", "shop_whatsapp": "99000 11111"}, page="/setup")
    assert r.status_code == 303, r.text


def login_admin(client: TestClient) -> None:
    r = post(client, "/login", {"kind": "admin", "ident": "asha", "secret": ADMIN_PASSWORD})
    assert r.status_code == 303, r.text


def make_customer(conn, name: str = "Priya", phone: str = "9845012345", pin: str = "1234"):
    user, _ = auth.ensure_customer(conn, name, phone)
    auth.change_pin(conn, user["id"], pin)
    return auth.get_user(conn, user["id"])


def login_customer(client: TestClient, phone: str = "9845012345", pin: str = "1234"):
    return post(client, "/login", {"kind": "customer", "ident": phone, "secret": pin})


def make_order(conn, customer=None, items=(("chocolate cake", 1, "kg"),), status: str = "received",
               delivery_date: str = "2099-01-05", address: str = "14B Lakeview", admin_id: int | None = None) -> int:
    order = Order(customer=customer["name"] if customer else "Walk-in", phone=customer["phone"] if customer else "",
                  items=[OrderItem(name=n, quantity=q, unit=u) for n, q, u in items],
                  delivery_date=delivery_date, address=address)
    oid = om.create_order(conn, order, customer["id"] if customer else None, admin_id)
    if status == "cancelled":
        om.cancel(conn, oid, admin_id)
    else:
        for s in om.FLOW[1: om.FLOW.index(status) + 1]:
            om.advance(conn, oid, admin_id)
    return oid


def admin_id(conn) -> int:
    return conn.execute("SELECT id FROM users WHERE role = 'admin'").fetchone()["id"]


def wait_for_run(run_id: int, timeout: float = 5.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        run = master.RUNS.get(run_id)
        if run is not None and run.feed.finished:
            return
        time.sleep(0.02)
    raise AssertionError("intake run did not finish")
