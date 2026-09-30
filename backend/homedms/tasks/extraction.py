"""Hintergrund-Job: Metadaten (Datum, Absender, Betrag) und Fristen per Sprachmodell erkennen
(Anforderungsdokument 4.3 "Klarstellung", 4.4a "KI-Fristenerkennung im Detail").

Laeuft einmal je Dokument, direkt nach der Texterkennung und unabhaengig von der Klassifikation.
Bewusst ein eigener, fokussierter Modell-Aufruf statt kombiniert mit Stufe 2 der Klassifikation:
Kleine lokale Modelle antworten mit einer Aufgabe je Aufruf deutlich zuverlaessiger, und ein
Fehler hier blockiert nicht die Kategorie. Bei < 50 Dokumenten/Monat ist der Zusatzaufruf
unerheblich.

- Metadaten fuellen nur leere Felder - was der Nutzer schon eingetragen hat, bleibt.
- Fristen werden Wiedervorlagen mit Status "vorgeschlagen" und muessen immer bestaetigt werden.
  Hat das Dokument bereits eine offene oder vorgeschlagene KI-Wiedervorlage, schlaegt der Job
  keine weiteren vor (keine Doppel-Vorschlaege).
"""
import logging
import uuid
from datetime import date

from sqlalchemy import select

from homedms.ai import ollama
from homedms.ai.extraction import build_prompt, parse_extraction
from homedms.ai.ollama import OllamaError
from homedms.core.retention import sync_retention
from homedms.jobs import app
from homedms.models.classification import AIModelConfig
from homedms.models.document import Document, ExtractionStatus
from homedms.models.wiedervorlage import Wiedervorlage

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

        existing_ai = await db.scalar(
            select(Wiedervorlage.id).where(
                Wiedervorlage.document_id == document.id,
                Wiedervorlage.source == "ai_suggested",
                Wiedervorlage.status.in_(("vorgeschlagen", "offen")),
            ).limit(1)
        )
        if existing_ai is None:
            for d in result.deadlines:
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
