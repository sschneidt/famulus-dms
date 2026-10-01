"""homedms/ai/extraction.py - Auswertung der Metadaten-/Fristenerkennung (Anforderungsdokument 4.4a)."""
from datetime import date
from decimal import Decimal

import pytest

from homedms.ai.extraction import (
    date_in_text,
    dates_in,
    explicit_deadline,
    relative_deadline,
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


def test_past_one_off_payment_deadline_is_no_proposal_but_kept_for_payment_status():
    """Keine neue Frist vorschlagen - aber fuer den Zahlungsstatus merken (core/payments.py)."""
    mahnung = "Mahnung\nBitte zahlbar bis 01.08.2026 begleichen."
    r = parse_extraction(answer(frist(datum="2026-08-01", textstelle="zahlbar bis 01.08.2026")), mahnung, TODAY)
    assert r.deadlines == []
    assert [d.due_date for d in r.past_payments] == [date(2026, 8, 1)]


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


# --- Nachtraege nach dem ersten Test mit dem echten Modell (llama3.2:3b) ----------------------

def test_invented_document_date_is_discarded():
    # Brief ohne Datum - das Modell setzte das heutige Datum ein
    brief = "Versicherung Muster AG\nVertragsnummer HOMEDMS-0815\nKuendigungsfrist: 3 Monate zum Jahresende"
    r = parse_extraction(answer(dokumentdatum="2026-09-28"), brief, TODAY)
    assert r.document_date is None and "steht nicht im Text" in r.discarded[0]


@pytest.mark.parametrize("schreibweise", [
    "01.09.2026", "1.9.2026", "01.09.26", "2026-09-01", "01/09/2026",
    "1. September 2026", "01. Sept. 2026", "1 September 2026", "1.  september   2026",
])
def test_document_date_is_found_in_common_notations(schreibweise):
    text = f"Stadtwerke\nMusterstadt, den {schreibweise}\nRechnung"
    assert date_in_text(date(2026, 9, 1), text)


def test_document_date_is_not_confused_with_similar_numbers():
    assert not date_in_text(date(2026, 9, 1), "Rechnung vom 11.09.2026")
    assert not date_in_text(date(2026, 9, 1), "Kundennummer 101.09.20265")


def test_prompt_forbids_todays_date_and_contains_no_example_dates():
    _, user, _ = build_prompt("Text", TODAY)
    assert "Niemals das heutige Datum" in user and "LETZTE Tag" in user
    # Beispieldaten im Prompt hat das Modell abgeschrieben - deshalb keine mehr ausser "heute"
    assert [d for _, d in dates_in(user.split("Dokumenttext")[0])] == [TODAY]


def test_model_date_is_replaced_by_date_in_quote():
    # Befund echtes Modell: "zahlbar bis 15.10.2026" wurde als 30.09. vorgeschlagen
    r = parse_extraction(answer(frist(datum="2026-09-30")), DOC, TODAY)
    [d] = r.deadlines
    assert d.due_date == date(2026, 10, 15)
    assert r.corrected == ["Zahlungsfrist: 2026-09-30 -> 2026-10-15 (Datum aus der Textstelle)"]


def test_notice_period_to_year_end_is_computed():
    # Befund echtes Modell: "3 Monate zum Jahresende" wurde als 31.12. vorgeschlagen
    brief = "Versicherung Muster AG\nKuendigungsfrist: 3 Monate zum Jahresende"
    f = frist(datum="2026-12-31", bezeichnung="Kuendigungsfrist", textstelle="Kuendigungsfrist: 3 Monate zum Jahresende")
    [d] = parse_extraction(answer(f), brief, TODAY).deadlines
    assert d.due_date == date(2026, 9, 30)
    assert (d.recurrence, d.interval_months) == ("yearly", 12)  # gilt jedes Jahr wieder
    [d] = parse_extraction(answer(f), brief, date(2026, 10, 1)).deadlines
    assert d.due_date == date(2027, 9, 30)  # dieses Jahr verpasst -> naechstes Jahr


@pytest.mark.parametrize("snippet,today_,expected,period", [
    ("Der Vertrag kann mit einer Frist von 3 Monaten zum Jahresende gekuendigt werden", date(2026, 3, 1), date(2026, 9, 30), 12),
    ("3 Monate zum Ende des Kalenderjahres", date(2026, 3, 1), date(2026, 9, 30), 12),
    ("Kuendigung mit sechs Wochen Frist zum Quartalsende", date(2026, 9, 30), date(2026, 11, 19), 3),
    ("kuendbar mit einem Monat zum Monatsende", date(2026, 9, 30), date(2026, 9, 30), 1),
    ("kuendbar mit einem Monat zum Monatsende", date(2026, 10, 1), date(2026, 10, 31), 1),
    ("12 Monate zum Jahresende", date(2026, 3, 1), date(2026, 12, 31), 12),
])
def test_relative_deadline(snippet, today_, expected, period):
    assert relative_deadline(snippet, today_) == (expected, period)


def test_relative_deadline_ignores_unrelated_text():
    assert relative_deadline("Die Laufzeit betraegt 24 Monate.", TODAY) is None
    assert relative_deadline("zahlbar innerhalb von 14 Tagen", TODAY) is None


@pytest.mark.parametrize("snippet,expected", [
    ("zahlbar bis 15.10.2026", date(2026, 10, 15)),
    ("Rechnung vom 01.09.2026, zahlbar bis 15.10.2026", date(2026, 10, 15)),
    ("Rechnung vom 01.09.2026, zahlbar bis spätestens 15.10.26", date(2026, 10, 15)),
    ("faellig am 1. Oktober 2026", date(2026, 10, 1)),
    ("Termin 2026-11-02", date(2026, 11, 2)),
    ("zwischen 01.10.2026 und 15.10.2026", None),  # mehrdeutig -> Modell entscheidet
    ("innerhalb von 14 Tagen", None),
])
def test_explicit_deadline(snippet, expected):
    assert explicit_deadline(snippet) == expected



# --- Betreff (Grundlage fuer Titel und Dateiname) ---------------------------------------------
from homedms.ai.extraction import subject_supported  # noqa: E402

WASSER = "Sanitär Müller GmbH\nRechnung vom 12.09.2026\nReparatur des Wasserschadens im Bad"


def test_betreff_muss_zum_text_passen():
    assert subject_supported("Rechnung Wasserschaden-Reparatur", WASSER)  # Wortstamm reicht
    assert not subject_supported("Kündigungsbestätigung Mobilfunk", WASSER)  # abgeschrieben/erfunden
    assert not subject_supported("", WASSER)
    assert not subject_supported("12 34", WASSER)


def test_parse_extraction_betreff_und_adresse():
    from datetime import date as _date

    answer = {
        "dokumentdatum": "2026-09-12", "absender": "Sanitär Müller GmbH", "betreff": '"Rechnung Wasserschaden"',
        "betrag": "", "fristen": [], "objektadresse": {"strasse": "", "plz": "", "ort": ""},
    }
    result = parse_extraction(answer, WASSER, _date(2026, 9, 30))
    assert result.subject == "Rechnung Wasserschaden"
    assert result.address is None
    result = parse_extraction({**answer, "betreff": "Vertrag Fitnessstudio"}, WASSER, _date(2026, 9, 30))
    assert result.subject is None
    assert any("Betreff" in d for d in result.discarded)


def test_verstrichene_zahlungsfrist_wird_fuer_den_zahlungsstatus_gemerkt():
    from datetime import date as _date

    text = "Stadtwerke\nStromrechnung\nBetrag 42 EUR zahlbar bis 15.03.2026. Kündigung bis 01.01.2026 möglich."
    answer = {
        "dokumentdatum": "", "absender": "Stadtwerke", "betreff": "", "betrag": "",
        "objektadresse": {"strasse": "", "plz": "", "ort": ""},
        "fristen": [
            {"datum": "2026-03-15", "bezeichnung": "zahlbar bis", "konfidenz": 0.9,
             "textstelle": "Betrag 42 EUR zahlbar bis 15.03.2026", "wiederholung": "keine"},
            {"datum": "2026-01-01", "bezeichnung": "Kündigung", "konfidenz": 0.9,
             "textstelle": "Kündigung bis 01.01.2026 möglich", "wiederholung": "keine"},
        ],
    }
    result = parse_extraction(answer, text, _date(2026, 9, 30))
    assert result.deadlines == []
    assert [(d.label, d.due_date) for d in result.past_payments] == [("Zahlungsfrist", _date(2026, 3, 15))]
    assert any("Vergangenheit" in d for d in result.discarded)  # die Kündigungsfrist bleibt verworfen
