"""Erinnerungsstufen und Text der Tageszusammenfassung (core/reminders.py)."""
from datetime import date

import pytest

from homedms.core.reminders import (
    LEAD, OVERDUE, TODAY, TOMORROW, WEEK, Digest, ReminderItem, should_remind, stage_for, when,
)

TODAY_DATE = date(2026, 10, 4)


@pytest.mark.parametrize(("days_left", "lead", "stage"), [
    (31, 30, 0), (30, 30, LEAD), (8, 30, LEAD), (7, 30, WEEK), (2, 30, WEEK), (1, 30, TOMORROW),
    (0, 30, TODAY), (-1, 30, OVERDUE), (-40, 30, OVERDUE),
    # kurzer Vorlauf: vorher nichts, dann direkt die passende Stufe
    (5, 3, 0), (3, 3, WEEK), (1, 0, 0), (0, 0, TODAY), (-2, 0, OVERDUE),
])
def test_stage_for(days_left, lead, stage):
    assert stage_for(days_left, lead) == stage


def test_each_stage_once():
    assert should_remind(LEAD, 0, None, TODAY_DATE)
    assert not should_remind(LEAD, LEAD, TODAY_DATE, TODAY_DATE)
    assert should_remind(WEEK, LEAD, date(2026, 9, 10), TODAY_DATE)
    assert not should_remind(0, 0, None, TODAY_DATE)
    # Server war aus: direkt "ueberfaellig" statt aller Zwischenstufen
    assert should_remind(OVERDUE, LEAD, date(2026, 9, 1), TODAY_DATE)


def test_overdue_repeats_weekly():
    assert not should_remind(OVERDUE, OVERDUE, date(2026, 9, 28), TODAY_DATE)
    assert should_remind(OVERDUE, OVERDUE, date(2026, 9, 27), TODAY_DATE)


def _item(days: int, note="Kündigungsfrist", title="Kfz-Versicherung") -> ReminderItem:
    due = date.fromordinal(TODAY_DATE.toordinal() + days)
    return ReminderItem("wv", "doc-1", title, note, due, days, stage_for(days, 30))


def test_when_texts():
    assert when(_item(0)) == "heute fällig (So, 04.10.2026)"
    assert when(_item(1)) == "morgen fällig (Mo, 05.10.2026)"
    assert when(_item(7)) == "in 7 Tagen fällig (So, 11.10.2026)"
    assert when(_item(-1)) == "seit gestern überfällig (Sa, 03.10.2026)"
    assert when(_item(-3)) == "seit 3 Tagen überfällig (Do, 01.10.2026)"


def test_empty_digest():
    assert Digest().is_empty
    assert not Digest(new_imports=1).is_empty


def test_digest_with_details():
    digest = Digest(items=[_item(7), _item(-2, "Zahlungsfrist", "Stromrechnung <Stadtwerke>"), _item(0)],
                    new_proposals=2, open_proposals=3, new_review=1, open_review=4)
    assert digest.subject() == "HomeDMS: 1 überfällig, 1 heute fällig, 1 demnächst"
    text = digest.text("https://nas:8443")
    assert text.index("Überfällig:") < text.index("Heute fällig:") < text.index("Demnächst:")
    assert "Zahlungsfrist – Stromrechnung <Stadtwerke>: seit 2 Tagen überfällig" in text
    assert "https://nas:8443/dokumente/doc-1" in text
    assert "2 neue Fristen erkannt" in text and "insgesamt 3 offen" in text
    assert "1 neues Dokument: Kategorie bitte prüfen (insgesamt 4)" in text
    html = digest.html("https://nas:8443")
    assert "Stromrechnung &lt;Stadtwerke&gt;" in html and "<Stadtwerke>" not in html
    assert 'href="https://nas:8443/pruefen"' in html


def test_digest_without_app_url_has_no_links():
    text = Digest(items=[_item(1)]).text("")
    assert "http" not in text and "„Konto & Sicherheit“" in text


def test_push_summary():
    digest = Digest(items=[_item(d) for d in (1, 2, 3, 4, 5)], new_review=2, open_review=2)
    push = digest.push()
    assert push["title"] == "HomeDMS: 5 demnächst, 2 zu prüfen"
    lines = push["body"].split("\n")
    assert lines[0] == "Kündigungsfrist – Kfz-Versicherung: morgen fällig (Mo, 05.10.2026)"
    assert "und 2 weitere Termine" in lines
    assert push["url"] == "/termine"
    assert Digest(new_review=1, open_review=1).push()["url"] == "/pruefen"
