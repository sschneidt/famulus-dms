"""Nicht (vollstaendig) analysierte Dokumente finden und neu anstossen.

Nutzerwunsch (03.10.2026): Wenn die KI nicht erreichbar war (z. B. Ollama laeuft unter Windows erst
nach der Anmeldung) oder ein Job verloren ging (Stromausfall), sollen alle betroffenen Dokumente
gesammelt sichtbar sein und mit einem Knopf neu analysiert werden ("Pruefen > Nicht analysiert").

Ein Dokument gilt als nicht analysiert, wenn
- die Texterkennung fehlgeschlagen ist,
- die Einordnung wegen eines KI-Ausfalls nicht lief (classification_error),
- Betreff/Absender/Fristen fehlen, weil die KI nicht erreichbar war (extraction failed, Text vorhanden),
- oder ein Schritt seit mindestens STUCK_AFTER "laeuft", ohne dass dafuer ein Auftrag in der
  Warteschlange steht (Auftrag verloren - z. B. Absturz oder Stromausfall).

Neu angestossen wird nur, was fehlt: Bereits erkannte oder vom Nutzer gesetzte Angaben bleiben
(anders als "Erneut analysieren" auf der Detailseite, das alles neu ermittelt).
"""
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import ColumnElement

from homedms.models.document import ClassificationStatus, Document, ExtractionStatus, OcrStatus

STUCK_AFTER = timedelta(minutes=10)

_jobs = sa.table(
    "procrastinate_jobs",
    sa.column("status", sa.String),
    sa.column("args", JSONB),
)


def _queued() -> ColumnElement[bool]:
    """Steht fuer dieses Dokument noch ein Auftrag in der Warteschlange (oder laeuft gerade)?"""
    return exists(
        select(sa.literal(1)).select_from(_jobs).where(
            sa.cast(_jobs.c.status, sa.Text).in_(("todo", "doing")),  # Spalte ist ein Procrastinate-Enum
            _jobs.c.args["document_id"].astext == sa.cast(Document.id, sa.String),
        )
    )


def _has_text() -> ColumnElement[bool]:
    return func.length(func.trim(func.coalesce(Document.ocr_text, ""))) > 0


def unanalyzed_expr(now: datetime | None = None) -> ColumnElement[bool]:
    stale = Document.updated_at < (now or datetime.now(timezone.utc)) - STUCK_AFTER
    stuck = and_(stale, ~_queued())
    return or_(
        Document.ocr_status == OcrStatus.failed,
        and_(Document.ocr_status == OcrStatus.pending, stuck),
        and_(
            Document.ocr_status == OcrStatus.done,
            Document.classification_status != ClassificationStatus.confirmed,
            or_(
                Document.classification_error.is_not(None),
                and_(Document.classification_status == ClassificationStatus.pending, stuck),
            ),
        ),
        and_(
            Document.ocr_status == OcrStatus.done,
            _has_text(),
            or_(
                Document.extraction_status == ExtractionStatus.failed,
                and_(Document.extraction_status == ExtractionStatus.pending, stuck),
            ),
        ),
    )


def reasons(document: Document) -> list[str]:
    """Was fehlt - fuer die Anzeige (die Auswahl selbst trifft unanalyzed_expr)."""
    if document.ocr_status == OcrStatus.failed:
        return ["Texterkennung fehlgeschlagen"]
    if document.ocr_status == OcrStatus.pending:
        return ["Texterkennung wurde unterbrochen"]
    result = []
    if document.classification_status != ClassificationStatus.confirmed:
        if document.classification_error:
            result.append("Kategorie: KI war nicht erreichbar")
        elif document.classification_status == ClassificationStatus.pending:
            result.append("Kategorie: Einordnung wurde unterbrochen")
    if (document.ocr_text or "").strip():
        if document.extraction_status == ExtractionStatus.failed:
            result.append("Betreff, Absender, Fristen: KI war nicht erreichbar")
        elif document.extraction_status == ExtractionStatus.pending:
            result.append("Betreff, Absender, Fristen: Erkennung wurde unterbrochen")
    return result


def plan(document: Document) -> list[str]:
    """Welche Auftraege neu angestossen werden - und Status passend setzen (ohne Commit).

    Texterkennung neu -> stoesst Einordnung und Angaben danach selbst an (tasks/ocr.py)."""
    if document.ocr_status in (OcrStatus.failed, OcrStatus.pending):
        document.ocr_status = OcrStatus.pending
        if document.classification_status != ClassificationStatus.confirmed:
            document.classification_status = ClassificationStatus.pending
        if document.extraction_status != ExtractionStatus.done:
            document.extraction_status = ExtractionStatus.pending
        return ["ocr_document"]
    tasks = []
    if document.classification_status != ClassificationStatus.confirmed and (
        document.classification_error or document.classification_status == ClassificationStatus.pending
    ):
        document.classification_status = ClassificationStatus.pending
        tasks.append("classify_document")
    if (document.ocr_text or "").strip() and document.extraction_status in (
        ExtractionStatus.failed, ExtractionStatus.pending,
    ):
        document.extraction_status = ExtractionStatus.pending
        tasks.append("extract_metadata")
    return tasks


QUEUES = {"ocr_document": "default", "classify_document": "ai", "extract_metadata": "ai"}
