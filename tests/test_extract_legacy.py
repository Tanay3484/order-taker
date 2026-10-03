"""The original single-call extraction, kept as the benchmark baseline (INT-20)."""

import json
from datetime import date

from order_taker import extract


class FakeResp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_extract_orders_parses_model_output(monkeypatch):
    model_json = {"orders": [{
        "customer": "Rahul", "items": [{"name": "brownies", "quantity": 3, "unit": "box"}],
        "delivery_date": "2026-10-03", "address": "14B Lakeview Apts, Indiranagar",
    }]}
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(json)
        return FakeResp({"message": {"content": __import__("json").dumps(model_json)}})

    monkeypatch.setattr(extract.httpx, "post", fake_post)
    orders = extract.extract_orders("…chat…", today=date(2026, 10, 2))

    assert orders[0].customer == "Rahul"
    assert orders[0].items[0].quantity == 3
    assert "2026-10-02" in sent["messages"][0]["content"]  # today's date reaches the prompt
    assert sent["format"]["title"] == "OrderBatch"         # schema-constrained output
