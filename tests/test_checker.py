"""003 INT-14, INT-15: Checker rules (plain code, no model)."""

from datetime import date

from order_taker.agents import checker
from order_taker.models import DraftAction, Order, OrderItem

TODAY = date(2026, 10, 2)


def order(**kw) -> Order:
    base = dict(customer="Priya", phone="9845012345", items=[OrderItem(name="cake", quantity=1, unit="kg")],
                delivery_date="2026-10-04", address="14B Lakeview")
    base.update(kw)
    return Order(**base)


def flags(o: Order | None = None, action="new", target=None, sender_open=None, others=()):
    return checker.check(DraftAction(action=action, target_order_id=target, order=o), sender_open or {}, list(others),
                         TODAY)


def test_clean_order_has_no_flags():
    assert flags(order()) == []


def test_no_date():
    assert checker.NO_DATE in flags(order(delivery_date=""))


def test_unclear_and_past_date():
    assert checker.UNCLEAR_DATE in flags(order(delivery_date="Sunday-ish"))
    assert checker.PAST_DATE in flags(order(delivery_date="2026-10-01"))


def test_no_address_unless_pickup_mentioned():
    assert checker.NO_ADDRESS in flags(order(address=""))
    assert checker.NO_ADDRESS not in flags(order(address="", notes="Self pickup at 4"))
    assert checker.NO_ADDRESS not in flags(order(address="", delivery_time="4pm pickup"))


def test_no_phone():
    assert checker.NO_PHONE in flags(order(phone=""))


def test_zero_quantity():
    assert checker.ZERO_QTY in flags(order(items=[OrderItem(name="cake", quantity=0)]))


def test_update_or_cancel_must_point_at_open_order():
    assert checker.BAD_TARGET in flags(order(), action="update", target=99, sender_open={})
    assert checker.BAD_TARGET in flags(None, action="cancel", target=99, sender_open={})
    assert flags(None, action="cancel", target=5, sender_open={5: order()}) == []


def test_duplicate_of_open_order_or_other_draft():
    assert checker.DUPLICATE in flags(order(), others=[order(phone="+91 98450 12345")])
    assert checker.DUPLICATE not in flags(order(), others=[order(delivery_date="2026-10-05")])


def test_int15_flags_are_fixed_plain_sentences():
    for name in ("NO_DATE", "UNCLEAR_DATE", "PAST_DATE", "NO_ADDRESS", "NO_PHONE", "ZERO_QTY", "NO_ITEMS",
                 "BAD_TARGET", "DUPLICATE"):
        text = getattr(checker, name)
        assert text[0].isupper() and text.rstrip().endswith((".", "?"))
