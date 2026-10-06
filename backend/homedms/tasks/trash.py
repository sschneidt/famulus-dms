"""Hintergrund-Job: Papierkorb leeren (Logik: homedms/core/trash.py).

Einmal pro Nacht werden Dokumente, die laenger als TRASH_RETENTION_DAYS im Papierkorb liegen,
endgueltig geloescht - samt Dateien und Suchindex-Eintrag.
"""
import logging

from homedms.jobs import app

logger = logging.getLogger("homedms.tasks.trash")


@app.periodic(cron="30 3 * * *")
@app.task(name="purge_trash", queue="default", queueing_lock="purge-trash", pass_context=False)
async def purge_trash(timestamp: int) -> None:
    from homedms.core import trash
    from homedms.core.meili import index_document
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        purged = await trash.purge_expired(db)
        for document_id in purged:
            await index_document(db, document_id)  # Dokument existiert nicht mehr -> aus dem Suchindex
