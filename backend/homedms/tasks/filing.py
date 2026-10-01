"""Hintergrund-Job: Dateien eines Dokuments nach Kategorie/Jahr ablegen und sprechend benennen
(Logik: homedms/core/filing.py).

Wird nach jeder relevanten Aenderung eingereiht (Texterkennung fertig, Klassifikation,
Metadaten, Bearbeitung, Papierkorb). Pro Dokument laeuft immer nur ein Ablage-Job gleichzeitig
(lock), und solange einer noch wartet, wird kein zweiter eingereiht (queueing_lock) - der
wartende Job liest beim Start ohnehin den aktuellen Stand.
"""
import logging
import uuid

from procrastinate.exceptions import AlreadyEnqueued

from homedms.core.filing import refile
from homedms.jobs import app
from homedms.models.document import Document, OcrStatus

logger = logging.getLogger("homedms.tasks.filing")


async def defer_filing(document_id: uuid.UUID | str) -> None:
    """Ablage einreihen. Die Procrastinate-App muss offen sein (im Worker immer; in der API ueber
    request_filing)."""
    key = f"file-document-{document_id}"
    try:
        await app.configure_task("file_document", lock=key, queueing_lock=key).defer_async(
            document_id=str(document_id)
        )
    except AlreadyEnqueued:
        pass


async def request_filing(document_id: uuid.UUID | str) -> None:
    """Variante fuer die API-Endpunkte (oeffnet die Verbindung zur Job-Queue kurz)."""
    async with app.open_async():
        await defer_filing(document_id)


@app.task(name="file_document")
async def file_document(document_id: str) -> None:
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        document = await db.get(Document, uuid.UUID(document_id))
        if document is None:
            return
        if document.ocr_status == OcrStatus.pending:
            return  # Texterkennung liest die Datei gerade - sie reiht die Ablage danach selbst ein
        await refile(db, document)
