"""Hintergrund-Job: Scan-Ordner abholen (Regeln und Ablauf: homedms/core/scanfolder.py).

Laeuft jede Minute (Procrastinate-Periodik) und auf Knopfdruck (POST /import-sources/{id}/scan-now).
queueing_lock: nie zwei Durchlaeufe gleichzeitig - sonst koennte dieselbe Datei doppelt importiert werden.
"""
import hashlib
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.i18n import N_
from homedms.config import get_settings
from homedms.core.scanfolder import (
    DONE_DIR,
    ERROR_DIR,
    MAX_FILE_BYTES,
    MAX_FILES_PER_RUN,
    candidates,
    destination,
    is_settled,
    is_supported,
    looks_complete,
    migrate_legacy_dirs,
    title_from_filename,
)
from homedms.core.storage import document_file_path, save_upload
from homedms.jobs import app
from homedms.models.document import Document, DocumentFile, DocumentSource, OriginalPresent
from homedms.models.ops import ImportSource
from homedms.models.tenant import Tenant

logger = logging.getLogger("homedms.tasks.scanfolder")

LOCK = "scan-folders"
MAX_RECENT = 30
STILL_WRITING_SECONDS = 600  # unvollstaendige Datei so lange liegen lassen, danach -> _failed


def scan_root() -> Path:
    return Path(get_settings().scan_path)


def source_folder(source: ImportSource) -> Path:
    return scan_root() / (source.config or {}).get("path", "")


async def request_scan() -> bool:
    """Durchlauf sofort einreihen (False, wenn schon einer wartet)."""
    try:
        await app.configure_task("scan_folders", queueing_lock=LOCK).defer_async(timestamp=int(time.time()))
        return True
    except AlreadyEnqueued:
        return False


@app.periodic(cron=get_settings().scan_interval_cron)
@app.task(name="scan_folders", queue="default", queueing_lock=LOCK, pass_context=False)
async def scan_folders(timestamp: int) -> None:
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        await ensure_default_source(db)
        sources = (await db.execute(
            select(ImportSource).where(ImportSource.type == "nas_watch_folder", ImportSource.is_active.is_(True))
        )).scalars().all()
        for source in sources:
            await scan_source(db, source)


async def ensure_default_source(db: AsyncSession) -> None:
    """Gibt es genau einen Haushalt und noch gar keine Import-Quelle, gehoert ihm der ganze
    Scan-Ordner - ohne dass jemand etwas einrichten muss."""
    if await db.scalar(select(func.count()).select_from(ImportSource)):
        return
    tenants = (await db.execute(select(Tenant.id))).scalars().all()
    if len(tenants) != 1:
        return
    db.add(ImportSource(tenant_id=tenants[0], type="nas_watch_folder", config={"path": ""}, is_active=True, recent=[]))
    await db.commit()


def _log(entries: list[dict], file: Path, root: Path, status: str, message: str = "", document_id=None,
         **params) -> None:
    """message: deutscher Text mit {Platzhaltern} - gespeichert wird er fertig (Deutsch) plus Vorlage und
    Werte, damit die App ihn in der Sprache der Person anzeigen kann (api/routes/import_sources.py)."""
    entries.append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file": file.relative_to(root).as_posix() if file.is_relative_to(root) else file.name,
        "status": status,  # importiert | duplikat | fehler
        "message": message.format(**params) if params else message,
        "key": message,
        "params": {k: str(v) for k, v in params.items()},
        "document_id": str(document_id) if document_id else None,
    })


def _move(file: Path, root: Path, folder: str) -> Path:
    target_dir = root / folder / datetime.now().strftime("%Y-%m")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = destination(target_dir, file.name)
    shutil.move(str(file), str(target))
    return target


async def scan_source(db: AsyncSession, source: ImportSource) -> None:
    root = source_folder(source)
    entries: list[dict] = []
    status: dict = {"waiting": 0, "error": None}

    if not root.is_dir():
        status["error"] = N_("Scan-Ordner nicht gefunden - ist SCAN_FOLDER_PATH in der .env richtig gesetzt?")
    else:
        for renamed in migrate_legacy_dirs(root):
            logger.info("Scan-Ordner: Ordner umbenannt (%s)", renamed)
        files = candidates(root)
        imported = 0
        for file in files:
            if imported >= MAX_FILES_PER_RUN:
                status["waiting"] += 1
                continue
            try:
                result = await _handle_file(db, source, root, file, entries)
            except Exception as exc:  # noqa: BLE001 - eine kaputte Datei darf den Lauf nicht stoppen
                await db.rollback()
                logger.exception("Scan-Ordner: %s konnte nicht importiert werden", file)
                _log(entries, file, root, "fehler", N_("wird erneut versucht: {error}"),
                     error=f"{exc.__class__.__name__}: {exc}"[:280])
                result = "skip"
            if result == "imported":
                imported += 1
            elif result == "waiting":
                status["waiting"] += 1

    source.last_scanned_at = datetime.now(timezone.utc)
    source.config = {**(source.config or {}), "status": status}
    if entries:
        source.recent = (list(reversed(entries)) + list(source.recent or []))[:MAX_RECENT]
    await db.commit()


async def _handle_file(db: AsyncSession, source: ImportSource, root: Path, file: Path, entries: list[dict]) -> str:
    if not is_supported(file):
        _move(file, root, ERROR_DIR)
        _log(entries, file, root, "fehler", N_("Dateityp {suffix} wird nicht unterstuetzt"), suffix=file.suffix or "–")
        return "error"
    if not is_settled(file):
        return "waiting"  # Scanner schreibt evtl. noch - naechster Durchlauf
    size = file.stat().st_size
    if size > MAX_FILE_BYTES:
        _move(file, root, ERROR_DIR)
        _log(entries, file, root, "fehler", N_("Datei zu gross ({size} MB)"), size=size // (1024 * 1024))
        return "error"

    content = file.read_bytes()
    problem = looks_complete(file, content)
    if problem:
        if "unvollstaendig" in problem and time.time() - file.stat().st_mtime < STILL_WRITING_SECONDS:
            return "waiting"
        _move(file, root, ERROR_DIR)
        _log(entries, file, root, "fehler", problem)
        return "error"

    checksum = hashlib.sha256(content).hexdigest()
    duplicate = (await db.execute(
        select(Document.id, Document.title)
        .join(DocumentFile, DocumentFile.document_id == Document.id)
        .where(Document.tenant_id == source.tenant_id, Document.deleted_at.is_(None), DocumentFile.checksum == checksum)
        .limit(1)
    )).first()
    if duplicate:
        _move(file, root, DONE_DIR)
        _log(entries, file, root, "duplikat", N_("schon vorhanden als „{title}“"), duplicate.id, title=duplicate.title)
        return "duplicate"

    document = Document(
        tenant_id=source.tenant_id, owner_user_id=None, title=title_from_filename(file.name), title_locked=False,
        source=DocumentSource.nas_scan_folder, original_present=OriginalPresent.unbekannt,
    )
    db.add(document)
    await db.flush()
    path = document_file_path(source.tenant_id, document.id, page_number=1, original_filename=file.name)
    save_upload(path, content)
    db.add(DocumentFile(
        document_id=document.id, file_path=str(path), page_number=1,
        mime_type=_mime(file), checksum=checksum,
    ))
    await db.commit()
    await app.configure_task("ocr_document", queue="default").defer_async(document_id=str(document.id))

    _move(file, root, DONE_DIR)
    _log(entries, file, root, "importiert", "", document.id)
    logger.info("Scan-Ordner: %s importiert als Dokument %s", file, document.id)
    return "imported"


def _mime(file: Path) -> str:
    import mimetypes

    guessed, _ = mimetypes.guess_type(file.name)
    if guessed:
        return guessed
    return {".heic": "image/heic", ".heif": "image/heif", ".eml": "message/rfc822"}.get(file.suffix.lower(),
                                                                                    "application/octet-stream")

