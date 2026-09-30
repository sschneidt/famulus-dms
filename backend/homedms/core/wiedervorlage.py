"""Regeln fuer Wiedervorlagen (Anforderungsdokument 4.4a) - reine Funktionen, getestet in
tests/test_wiedervorlage_rules.py."""
from datetime import date

from homedms.core.dates import add_months

RECURRENCES = ("none", "monthly", "yearly", "custom_months")
EDITABLE_STATUSES = ("vorgeschlagen", "offen")


def interval_months(recurrence: str, custom_months: int | None) -> int | None:
    """Wiederholungsabstand in Monaten; None = einmaliger Termin."""
    if recurrence == "monthly":
        return 1
    if recurrence == "yearly":
        return 12
    if recurrence == "custom_months":
        return custom_months
    return None


def next_due(due: date, recurrence: str, custom_months: int | None, today: date) -> date | None:
    """Naechster Termin nach dem Erledigen einer wiederkehrenden Wiedervorlage.

    Regulaer der Termin + Abstand. Wurde zu spaet erledigt, wird bis zum naechsten Termin in der
    Zukunft weitergerueckt - statt eine Reihe bereits verstrichener Termine anzulegen."""
    months = interval_months(recurrence, custom_months)
    if not months:
        return None
    step = 1
    candidate = add_months(due, months)
    while candidate <= today:
        step += 1
        candidate = add_months(due, months * step)  # immer vom Ursprung aus: kein Monatsende-Drift
    return candidate


def retention_due(document_date: date, retention_months: int) -> date:
    """Ende der Aufbewahrungsfrist - danach darf das Dokument vernichtet werden."""
    return add_months(document_date, retention_months)


def retention_note(category_name: str, retention_months: int, requires_original: bool) -> str:
    years, months = divmod(retention_months, 12)
    dauer = " ".join(p for p in (
        f"{years} Jahr{'e' if years != 1 else ''}" if years else "",
        f"{months} Monat{'e' if months != 1 else ''}" if months else "",
    ) if p)
    original = " Das Papier-Original muss bis dahin aufbewahrt werden." if requires_original else ""
    return f"Aufbewahrungsfrist ({category_name}, {dauer}) endet - Dokument kann danach vernichtet werden.{original}"
