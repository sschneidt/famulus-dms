"""Hintergrund-Job: Metadaten (Datum, Absender, Betrag) und Fristen per Sprachmodell erkennen
(Anforderungsdokument 4.3 "Klarstellung", 4.4a "KI-Fristenerkennung im Detail").

Laeuft einmal je Dokument, direkt nach der Texterkennung und unabhaengig von der Klassifikation.
Bewusst ein eigener, fokussierter Modell-Aufruf statt kombiniert mit Stufe 2 der Klassifikation:
Kleine lokale Modelle antworten mit einer Aufgabe je Aufruf deutlich zuverlaessiger, und ein
Fehler hier blockiert nicht die Kategorie. Bei < 50 Dokumenten/Monat ist der Zusatzaufruf
unerheblich.

- Metadaten fuellen nur leere Felder - was der Nutzer schon eingetragen hat, bleibt.
- Titel wird zu "Betreff – Absender", ausser der Nutzer hat ihn selbst vergeben (title_locked);
  danach wird die Datei passend benannt und abgelegt (tasks/filing.py).
- Fristen werden Wiedervorlagen mit Status "vorgeschlagen" und muessen immer bestaetigt werden.
  Hat das Dokument bereits eine offene oder vorgeschlagene KI-Wiedervorlage, schlaegt der Job
  keine weiteren vor (keine Doppel-Vorschlaege).
"""
import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from homedms.ai import ollama
from homedms.ai.extraction import build_prompt, parse_extraction
from homedms.ai.ollama import OllamaError
from homedms.core.naming import refresh_title
from homedms.core.payments import assumed_paid, is_payment, mark_paid
from homedms.core.properties import property_for
from homedms.core.retention import sync_retention
from homedms.jobs import app
from homedms.models.classification import AIModelConfig
from homedms.models.document import Document, ExtractionStatus
from homedms.models.wiedervorlage import Wiedervorlage
from homedms.tasks.filing import defer_filing

logger = logging.getLogger("homedms.tasks.extraction")


def today() -> date:
    """Eigene Funktion, damit Tests ein festes Datum setzen koennen."""
    return date.today()


@app.task(name="extract_metadata")
async def extract_metadata(document_id: str) -> None:
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        document = await db.get(Document, uuid.UUID(document_id))
        if document is None or document.deleted_at is not None:
            return
        if document.extraction_status == ExtractionStatus.done:
            return  # laeuft nur einmal je Dokument

        text = (document.ocr_text or "").strip()
        if not text:
            document.extraction_status = ExtractionStatus.failed
            await db.commit()
            return

        config = await db.scalar(select(AIModelConfig).where(AIModelConfig.tenant_id == document.tenant_id))
        system, user, schema = build_prompt(text, today())
        try:
            raw = await ollama.client_for(config).chat_json(system, user, schema)
        except OllamaError as exc:
            logger.warning("Extraktion fehlgeschlagen fuer %s: %s", document_id, exc)
            document.extraction_status = ExtractionStatus.failed
            await db.commit()
            return

        result = parse_extraction(raw, text, today())
        for discarded in result.discarded:
            logger.info("Dokument %s - Frist verworfen: %s", document_id, discarded)
        for corrected in result.corrected:
            logger.info("Dokument %s - Frist korrigiert: %s", document_id, corrected)

        if document.document_date is None:
            document.document_date = result.document_date
        if not document.issuer:
            document.issuer = result.issuer
        if document.amount is None:
            document.amount = result.amount
        if not document.subject:
            document.subject = result.subject
        if document.property_id is None and result.address is not None:
            document.property_id = (await property_for(db, document.tenant_id, result.address)).id
        refresh_title(document)  # "Betreff – Absender", ausser der Nutzer hat selbst einen Titel vergeben

        existing_ai = await db.scalar(
            select(Wiedervorlage.id).where(
                Wiedervorlage.document_id == document.id,
                Wiedervorlage.source == "ai_suggested",
                Wiedervorlage.status.in_(("vorgeschlagen", "offen")),
            ).limit(1)
        )
        if existing_ai is None:
            for d in result.past_payments:
                if assumed_paid(d.due_date, today()):
                    # Eingescannte, laengst faellige Rechnung: als bezahlt annehmen, Frist nur dokumentieren
                    if document.payment_status is None:
                        await mark_paid(db, document, None, today=today(), assumed=True)
                    status, completed_at = "erledigt", datetime.now(timezone.utc)
                else:
                    # Kuerzlich verstrichen: als ueberfaelliger Vorschlag zeigen - "schon bezahlt?"
                    if document.payment_status is None:
                        document.payment_status = "offen"
                    status, completed_at = "vorgeschlagen", None
                db.add(Wiedervorlage(
                    tenant_id=document.tenant_id, document_id=document.id, due_date=d.due_date,
                    note=d.label, type="custom", source="ai_suggested", status=status, completed_at=completed_at,
                    confidence=d.confidence, source_snippet=d.snippet, recurrence="none",
                    assigned_user_id=document.owner_user_id,
                ))
            for d in result.deadlines:
                if is_payment(d.label) and document.payment_status is None:
                    document.payment_status = "offen"
                db.add(Wiedervorlage(
                    tenant_id=document.tenant_id, document_id=document.id,
                    due_date=d.due_date, note=d.label, type="custom", source="ai_suggested",
                    status="vorgeschlagen", confidence=d.confidence, source_snippet=d.snippet,
                    recurrence=d.recurrence,
                    recurrence_interval_months=d.interval_months if d.recurrence == "custom_months" else None,
                    assigned_user_id=document.owner_user_id,  # Anforderungsdokument 4.4a: Default Owner
                ))

        await sync_retention(db, document)
        document.extraction_status = ExtractionStatus.done
        await db.commit()
        await defer_filing(document.id)  # Dateiname aus Datum/Absender/Betreff
