"""Zahlungen: Rechnungen als bezahlt markieren (Nutzerwunsch 01.10.2026).

- Eingescannte Rechnungen, deren Zahlungsfrist beim Einlesen schon mehr als 3 Monate zurueckliegt,
  sind so gut wie sicher bezahlt: Sie werden automatisch als "bezahlt (angenommen)" markiert, und
  statt eines Fristvorschlags entsteht nur ein bereits erledigter Termin (nachvollziehbar im Verlauf).
- Alle anderen: in der App "Als bezahlt markieren" mit Zahlungsdatum. Dabei werden die offenen
  Zahlungsfristen des Dokuments erledigt; wiederkehrende bekommen wie gewohnt ihren Folgetermin.

Ob ein Termin eine Zahlungsfrist ist, ergibt sich aus seiner Bezeichnung (die Extraktion
vereinheitlicht sie zu "Zahlungsfrist", siehe ai/extraction.py normalize_label).
"""
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.core.dates import add_months
from homedms.core.wiedervorlage import next_due
from homedms.models.document import Document
from homedms.models.wiedervorlage import Wiedervorlage

ASSUME_PAID_AFTER_MONTHS = 3
PAYMENT_STATUSES = ("offen", "bezahlt")
PAYMENT_PATTERN = "zahl|überweis|ueberweis|fällig|faellig|begleich"  # auch fuer SQL (~*)
_PAYMENT_WORDS = re.compile(PAYMENT_PATTERN, re.IGNORECASE)


def is_payment(note: str | None) -> bool:
    return bool(_PAYMENT_WORDS.search(note or ""))


def assumed_paid(due: date, today: date) -> bool:
    """Frist liegt mehr als 3 Monate zurueck -> mit hoher Wahrscheinlichkeit laengst bezahlt."""
    return due < add_months(today, -ASSUME_PAID_AFTER_MONTHS)


def complete(wv: Wiedervorlage, user_id: uuid.UUID | None, today: date) -> Wiedervorlage | None:
    """Termin erledigen; bei Wiederholung den Folgetermin zurueckgeben (Aufrufer fuegt ihn hinzu)."""
    wv.status = "erledigt"
    wv.completed_at = datetime.now(timezone.utc)
    wv.completed_by_user_id = user_id
    due = next_due(wv.due_date, wv.recurrence, wv.recurrence_interval_months, today)
    if due is None:
        return None
    return Wiedervorlage(
        tenant_id=wv.tenant_id, document_id=wv.document_id, due_date=due, note=wv.note, type=wv.type,
        source=wv.source, status="offen", confidence=wv.confidence, source_snippet=wv.source_snippet,
        recurrence=wv.recurrence, recurrence_interval_months=wv.recurrence_interval_months,
        assigned_user_id=wv.assigned_user_id, created_by_user_id=wv.created_by_user_id,
        reminder_lead_days=wv.reminder_lead_days,
    )


async def mark_paid(
    db: AsyncSession, document: Document, paid_on: date | None, *, today: date,
    user_id: uuid.UUID | None = None, assumed: bool = False,
) -> None:
    """Dokument als bezahlt markieren und seine offenen bzw. vorgeschlagenen Zahlungsfristen erledigen."""
    document.payment_status = "bezahlt"
    document.paid_on = paid_on
    document.paid_assumed = assumed
    pending = (await db.execute(
        select(Wiedervorlage).where(
            Wiedervorlage.document_id == document.id, Wiedervorlage.status.in_(("offen", "vorgeschlagen"))
        )
    )).scalars().all()
    for wv in pending:
        if not is_payment(wv.note):
            continue
        if wv.status == "offen":
            follow_up = complete(wv, user_id, today)
            if follow_up is not None:
                db.add(follow_up)
        else:  # nicht bestaetigter Vorschlag: erledigt sich mit der Zahlung, ohne Folgetermin
            wv.status = "erledigt"
            wv.completed_at = datetime.now(timezone.utc)
            wv.completed_by_user_id = user_id
