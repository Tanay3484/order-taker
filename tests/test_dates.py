"""003 INT-21: delivery days resolved in code."""

from datetime import date

import pytest

from order_taker.agents.dates import resolve_date

FRI = date(2026, 10, 2)  # a Friday


@pytest.mark.parametrize("written, expected", [
    ("2026-10-09", "2026-10-09"),
    ("today", "2026-10-02"),
    ("aaj shaam", "2026-10-02"),
    ("tomorrow", "2026-10-03"),
    ("kal subah", "2026-10-03"),
    ("naale", "2026-10-03"),
    ("day after tomorrow", "2026-10-04"),
    ("parso", "2026-10-04"),
    ("Sunday", "2026-10-04"),
    ("sunday evening", "2026-10-04"),
    ("Sat", "2026-10-03"),
    ("Friday", "2026-10-02"),
    ("next Friday", "2026-10-09"),
    ("this Monday", "2026-10-05"),
    ("5th Oct", "2026-10-05"),
    ("October 12", "2026-10-12"),
    ("12/10", "2026-10-12"),
    ("5th Jan", "2027-01-05"),
])
def test_int21_resolves(written, expected):
    assert resolve_date(written, FRI) == expected


@pytest.mark.parametrize("written", ["whenever", "after Diwali", "31/02"])
def test_int21_unclear_stays_as_written(written):
    assert resolve_date(written, FRI) == written


def test_int21_empty():
    assert resolve_date("", FRI) == ""
