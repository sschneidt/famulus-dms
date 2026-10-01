"""Zahlungsregeln (homedms/core/payments.py)."""
from datetime import date

import pytest

from homedms.core.payments import assumed_paid, is_payment


@pytest.mark.parametrize(
    ("note", "expected"),
    [("Zahlungsfrist", True), ("zahlbar bis", True), ("Fällig am", True), ("Überweisung bis", True),
     ("Kündigungsfrist", False), ("TÜV-Termin", False), ("", False), (None, False)],
)
def test_is_payment(note, expected):
    assert is_payment(note) is expected


def test_assumed_paid_mehr_als_drei_monate():
    today = date(2026, 9, 30)
    assert assumed_paid(date(2026, 6, 29), today)
    assert not assumed_paid(date(2026, 6, 30), today)  # genau 3 Monate: noch nicht
    assert not assumed_paid(date(2026, 9, 1), today)
    assert not assumed_paid(date(2026, 10, 15), today)
    # Monatsende: 31.05. minus... 3 Monate vor dem 31.08. ist der 31.05.
    assert assumed_paid(date(2026, 5, 30), date(2026, 8, 31))
    assert not assumed_paid(date(2026, 5, 31), date(2026, 8, 31))
