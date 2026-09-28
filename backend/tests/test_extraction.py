"""homedms/ai/extraction.py - Auswertung der Metadaten-/Fristenerkennung (Anforderungsdokument 4.4a)."""
from datetime import date
from decimal import Decimal

import pytest

from homedms.ai.extraction import (
    MAX_DEADLINES,
    add_months,
    build_prompt,
    parse_amount,
    parse_date,
    parse_extraction,
    quote_supported,
)

TODAY = date(2026, 9, 28)
DOC = """Stadtwerke Musterstadt GmbH
Stromrechnung vom 01.09.2026
Betrag: 1.234,56 EUR - zahlbar bis 15.10.2026.
Der Vertrag kann mit einer Frist von 3 Monaten zum Jahresende gekuendigt werden."""


def frist(**kw):
    base = {"datum": "2026-10-15", "bezeichnung": "Zahlungsfrist", "konfidenz": 0.9,
            "textstelle": "zahlbar bis 15.10.2026", "wiederholung": "keine"}
    base.update(kw)
    return base


def answer(*fristen, **kw):
    base = {"dokumentdatum": "2026-09-01", "absender": "Stadtwerke Musterstadt GmbH", "betrag": "1234.56",
            "fristen": list(fristen)}
    base.update(kw)
    return base


@pytest.mark.parametrize("raw,expected", [
    ("2026-09-01", date(2026, 9, 1)), ("2026-9-1", date(2026, 9, 1)), ("01.09.2026", date(2026, 9, 1)),
    ("2026-02-30", None), ("", None), (None, None), ("naechste Woche", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("42.00", Decimal("42.00")), ("42,00", Decimal("42.00")), ("1.234,56 EUR", Decimal("1234.56")),
    ("1,234.56", Decimal("1234.56")), ("€ 99", Decimal("99.00")), ("", None), ("keiner", None),
    ("-5", None), (42, Decimal("42.00")),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_metadata_is_taken_over():
    r = parse_extraction(answer(), DOC, TODAY)
    assert (r.document_date, r.issuer, r.amount) == (date(2026, 9, 1), "Stadtwerke Musterstadt GmbH", Decimal("1234.56"))


def test_empty_or_implausible_metadata_stays_empty():
    r = parse_extraction(answer(dokumentdatum="2031-01-01", absender="  ", betrag=""), DOC, TODAY)
    assert (r.document_date, r.issuer, r.amount) == (None, None, None)
    assert parse_extraction(answer(dokumentdatum="1899-01-01"), DOC, TODAY).document_date is None


def test_valid_deadline_becomes_proposal():
    r = parse_extraction(answer(frist()), DOC, TODAY)
    [d] = r.deadlines
    assert d.due_date == date(2026, 10, 15) and d.label == "Zahlungsfrist" and d.recurrence == "none"
    assert d.snippet == "zahlbar bis 15.10.2026"


def test_low_confidence_is_discarded():
    r = parse_extraction(answer(frist(konfidenz=0.49)), DOC, TODAY)
    assert r.deadlines == [] and "Konfidenz" in r.discarded[0]
    assert len(parse_extraction(answer(frist(konfidenz=50)), DOC, TODAY).deadlines) == 1  # Prozentangabe


def test_invented_quote_is_discarded():
    r = parse_extraction(answer(frist(textstelle="Die Mitgliedschaft endet automatisch nach zwei Jahren")), DOC, TODAY)
    assert r.deadlines == [] and "steht nicht im Dokument" in r.discarded[0]


def test_slightly_different_quote_is_accepted():
    assert quote_supported("Betrag zahlbar bis zum 15.10.2026", DOC)
    assert not quote_supported("", DOC) and not quote_supported("zahlbar", DOC)


def test_past_one_off_deadline_is_discarded():
    r = parse_extraction(answer(frist(datum="2026-08-01")), DOC, TODAY)
    assert r.deadlines == [] and "Vergangenheit" in r.discarded[0]


def test_past_recurring_deadline_rolls_forward():
    f = frist(datum="2025-09-30", bezeichnung="Kuendigungsfrist", wiederholung="jaehrlich",
              textstelle="mit einer Frist von 3 Monaten zum Jahresende gekuendigt werden")
    [d] = parse_extraction(answer(f), DOC, TODAY).deadlines
    assert d.due_date == date(2026, 9, 30) and (d.recurrence, d.interval_months) == ("yearly", 12)


def test_quarterly_recurrence_maps_to_custom_months():
    [d] = parse_extraction(answer(frist(wiederholung="vierteljaehrlich")), DOC, TODAY).deadlines
    assert (d.recurrence, d.interval_months) == ("custom_months", 3)


def test_invalid_entries_and_duplicates_are_skipped():
    r = parse_extraction(answer(frist(), frist(), frist(datum="bald"), "kein Objekt"), DOC, TODAY)
    assert len(r.deadlines) == 1
    assert parse_extraction({"fristen": "keine"}, DOC, TODAY).deadlines == []
    assert parse_extraction({}, DOC, TODAY).deadlines == []


def test_number_of_proposals_is_capped():
    many = [frist(datum=f"2026-11-{i:02d}", bezeichnung=f"Frist {i}", konfidenz=0.5 + i / 100) for i in range(1, 9)]
    r = parse_extraction(answer(*many), DOC, TODAY)
    assert len(r.deadlines) == MAX_DEADLINES
    assert min(d.confidence for d in r.deadlines) == pytest.approx(0.54)  # die sichersten bleiben
    assert [d.due_date for d in r.deadlines] == sorted(d.due_date for d in r.deadlines)


def test_add_months_handles_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_prompt_contains_today_and_text():
    system, user, schema = build_prompt("Rechnung " * 5000, TODAY, max_chars=200)
    assert "2026-09-28" in user and len(user) < 3000
    assert schema["properties"]["fristen"]["items"]["properties"]["wiederholung"]["enum"][0] == "keine"
