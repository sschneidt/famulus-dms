"""homedms/core/wiedervorlage.py und Bezeichnungen aus homedms/ai/extraction.py."""
from datetime import date

import pytest

from homedms.ai.extraction import normalize_label
from homedms.core.wiedervorlage import interval_months, next_due, retention_due, retention_note

TODAY = date(2026, 9, 30)


@pytest.mark.parametrize("recurrence,custom,expected", [
    ("none", None, None), ("monthly", None, 1), ("yearly", None, 12), ("custom_months", 3, 3), ("custom_months", None, None),
])
def test_interval_months(recurrence, custom, expected):
    assert interval_months(recurrence, custom) == expected


def test_one_off_has_no_next_due():
    assert next_due(date(2026, 10, 15), "none", None, TODAY) is None


def test_completed_on_time_gives_next_period():
    assert next_due(date(2026, 9, 30), "yearly", None, TODAY) == date(2027, 9, 30)
    assert next_due(date(2026, 10, 15), "monthly", None, TODAY) == date(2026, 11, 15)
    assert next_due(date(2026, 10, 1), "custom_months", 3, TODAY) == date(2027, 1, 1)


def test_completed_late_skips_missed_periods():
    # Monatlicher Termin seit Juni offen, am 30.09. erledigt -> naechster ist der 15.10., nicht 15.07.
    assert next_due(date(2026, 6, 15), "monthly", None, TODAY) == date(2026, 10, 15)
    assert next_due(date(2024, 9, 30), "yearly", None, TODAY) == date(2027, 9, 30)


def test_month_end_does_not_drift():
    # 31.01. monatlich: Februar hat 28 Tage, danach geht es trotzdem mit dem 31. weiter
    assert next_due(date(2026, 1, 31), "monthly", None, date(2026, 1, 31)) == date(2026, 2, 28)
    assert next_due(date(2026, 1, 31), "monthly", None, date(2026, 3, 1)) == date(2026, 3, 31)


def test_retention():
    assert retention_due(date(2026, 9, 1), 120) == date(2036, 9, 1)
    assert retention_note("Steuern", 120, True) == (
        "Aufbewahrungsfrist (Steuern, 10 Jahre) endet - Dokument kann danach vernichtet werden. "
        "Das Papier-Original muss bis dahin aufbewahrt werden.")
    assert "(Rechnungen, 2 Jahre 6 Monate)" in retention_note("Rechnungen", 30, False)
    assert "(Garantie, 1 Jahr)" in retention_note("Garantie", 12, False)


@pytest.mark.parametrize("label,snippet,expected", [
    ("zahlbar bis", "zahlbar bis 15.10.2026", "Zahlungsfrist"),  # Befund echtes Modell
    ("Zahlungsfrist", "zahlbar bis 15.10.2026", "Zahlungsfrist"),
    ("Kuendigungsfrist", "3 Monate zum Jahresende", "Kündigungsfrist"),
    ("frist", "kann mit 3 Monaten gekündigt werden", "Kündigungsfrist"),  # Fragment -> Textstelle zaehlt
    ("Vertragsende", "Kuendigung bis 30.09. moeglich", "Vertragsende"),  # eindeutige Bezeichnung bleibt
    ("Einspruch gegen den Bescheid", "", "Widerspruchsfrist"),
    ("Grillfest", "am 01.08.2026", "Grillfest"),
    ("jahresgespraech", "", "Jahresgespraech"),
])
def test_normalize_label(label, snippet, expected):
    assert normalize_label(label, snippet) == expected
