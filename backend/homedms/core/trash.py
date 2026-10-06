"""Papierkorb leeren: Dokumente, die laenger als TRASH_RETENTION_DAYS (Standard 30) im Papierkorb
liegen, werden endgueltig geloescht (Anforderungsdokument 4.4 "Loeschen (Soft-Delete)").

Reihenfolge mit Absicht: erst Datenbank (Dokument samt Seiten, Terminen, Lernbeispielen - per
CASCADE), danach die Dateien. Bricht es dazwischen ab, bleibt hoechstens eine verwaiste Datei
liegen, nie ein Dokument ohne Datei. Dateien ausserhalb des Dokumente-Ordners werden nie angefasst.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.config import get_settings
from homedms.core.filing import _prune_empty_dirs, documents_root
from homedms.models.chat import ChatSession
from homedms.models.document import Document

logger = logging.getLogger("homedms.core.trash")


def _remove_file(path: Path, root: Path) -> None:
    resolved = path.resolve()
    if root.resolve() not in resolved.parents:
        logger.warning("Datei liegt ausserhalb des Dokumente-Ordners, nicht geloescht: %s", path)
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Datei konnte nicht geloescht werden: %s (%s)", path, exc)
        return
    _prune_empty_dirs(path.parent, root)


async def purge_expired(db: AsyncSession, now: datetime | None = None, days: int | None = None) -> list:
    """Loescht alle abgelaufenen Papierkorb-Dokumente endgueltig und liefert deren IDs
    (der Aufrufer nimmt sie aus dem Suchindex)."""
    days = get_settings().trash_retention_days if days is None else days
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    documents = (
        await db.execute(
            select(Document).where(Document.deleted_at.isnot(None), Document.deleted_at < cutoff)
        )
    ).scalars().all()
    if not documents:
        return []

    ids = [d.id for d in documents]
    paths = [Path(f.file_path) for d in documents for f in d.files]
    # ChatSession.scope_document_id hat keine ON DELETE-Regel und wuerde das Loeschen blockieren
    await db.execute(update(ChatSession).where(ChatSession.scope_document_id.in_(ids)).values(scope_document_id=None))
    for document in documents:
        await db.delete(document)
    await db.commit()

    root = documents_root()
    for path in paths:
        _remove_file(path, root)
    logger.info("Papierkorb: %d Dokument(e) endgueltig geloescht", len(ids))
    return ids
