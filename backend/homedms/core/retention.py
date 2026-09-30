"""Aufbewahrungsregeln -> Wiedervorlagen (Anforderungsdokument 4.4a: "aus einer Aufbewahrungsregel
automatisch erzeugt, sobald Kategorie/Dokumentdatum bekannt sind").

sync_retention() wird ueberall aufgerufen, wo sich Kategorie oder Dokumentdatum aendern koennen
(Klassifikation, manuelle Zuordnung, Metadaten-Erkennung, PATCH /documents) sowie fuer alle
Dokumente einer Kategorie, wenn deren Regel angelegt, geaendert oder geloescht wird. Die Funktion
committet nicht selbst - das macht der Aufrufer zusammen mit seiner eigentlichen Aenderung.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.core.wiedervorlage import retention_due, retention_note
from homedms.models.document import Category, Document
from homedms.models.wiedervorlage import RetentionRule, Wiedervorlage


async def sync_retention(db: AsyncSession, document: Document) -> None:
    if document.deleted_at is not None:
        return  # im Papierkorb: nichts veraendern (bei Wiederherstellung soll alles noch da sein)

    existing = (
        await db.execute(
            select(Wiedervorlage).where(
                Wiedervorlage.document_id == document.id, Wiedervorlage.source == "retention_rule"
            )
        )
    ).scalars().all()
    open_ones = [w for w in existing if w.status == "offen"]

    rule = None
    if document.category_id is not None and document.document_date is not None:
        rule = await db.scalar(
            select(RetentionRule).where(
                RetentionRule.tenant_id == document.tenant_id,
                RetentionRule.category_id == document.category_id,
                RetentionRule.retention_period_months.isnot(None),
            ).limit(1)
        )

    if rule is None:  # keine (passende) Regel mehr: offene Aufbewahrungs-Termine entfernen
        for w in open_ones:
            await db.delete(w)
        return

    category = await db.get(Category, document.category_id)
    due = retention_due(document.document_date, rule.retention_period_months)
    note = retention_note(category.name if category else "Kategorie", rule.retention_period_months, rule.requires_original)

    if open_ones:
        current, *duplicates = open_ones
        current.due_date, current.note, current.reminder_lead_days = due, note, rule.notify_before_days
        for w in duplicates:
            await db.delete(w)
    elif any(w.status == "erledigt" for w in existing):
        return  # bereits erledigt - nicht erneut anlegen
    else:
        db.add(Wiedervorlage(
            tenant_id=document.tenant_id, document_id=document.id, due_date=due, note=note,
            type="retention", source="retention_rule", status="offen", recurrence="none",
            assigned_user_id=document.owner_user_id, reminder_lead_days=rule.notify_before_days,
        ))


async def sync_category(db: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID | None) -> None:
    """Alle Dokumente einer Kategorie abgleichen - nach Aenderung ihrer Aufbewahrungsregel."""
    if category_id is None:
        return
    documents = (
        await db.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.category_id == category_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for document in documents:
        await sync_retention(db, document)
