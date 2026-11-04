"""Diagnose (nur Admin): Zustand aller Bausteine und einfache Reparatur-Aktionen.

Pruefungen: homedms/core/diagnostics.py. Die Aktionen sind bewusst harmlos und wiederholbar:
Worker neu starten (beendet sich selbst, Docker/Starter startet ihn neu), haengende Auftraege neu
starten, fehlende KI-Modelle laden, KI-Arbeitsspeicher freigeben, Suchindex neu aufbauen.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms import __version__
from homedms.api.deps import require_admin
from homedms.config import get_settings
from homedms.core import backup, diagnostics, updates
from homedms.db import get_db
from homedms.jobs import app as jobs_app
from homedms.models.document import Document
from homedms.models.tenant import User
from homedms.schemas.system import ActionResult, BackupsResponse, DiagnosticsResponse, UpdateStatus
from homedms.i18n import _, _n

logger = logging.getLogger("homedms.api.system")
router = APIRouter(prefix="/system", tags=["system"])


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def get_diagnostics(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> DiagnosticsResponse:
    components = await diagnostics.collect(user.tenant_id)
    states = {c.status for c in components}
    overall = "error" if "error" in states else "warning" if "warning" in states else "ok"
    return DiagnosticsResponse(
        version=__version__,
        checked_at=datetime.now(timezone.utc),
        overall=overall,
        components=[{
            "key": c.key, "name": c.name, "status": c.status, "summary": c.summary, "hint": c.hint,
            "details": [{"label": k, "value": v} for k, v in c.details],
            "actions": [{"id": a.id, "label": a.label, "confirm": a.confirm} for a in c.actions],
        } for c in components],
        recent_failures=await diagnostics.recent_failures(db, user.tenant_id),
    )


@router.post("/actions/{action}", response_model=ActionResult)
async def run_action(action: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> ActionResult:
    logger.info("Diagnose-Aktion %s von %s", action, user.email)
    if action == "restart-worker":
        async with jobs_app.open_async():
            await jobs_app.configure_task("restart_worker").defer_async()
        return ActionResult(message=_("Der Worker startet in wenigen Sekunden neu."))

    if action == "retry-stalled":
        async with jobs_app.open_async():
            stalled = list(await jobs_app.job_manager.get_stalled_jobs(seconds_since_heartbeat=60))
            for job in stalled:
                await jobs_app.job_manager.retry_job(job)
        return ActionResult(message=_n("{count} hängender Auftrag neu eingereiht.", "{count} hängende Aufträge neu eingereiht.", len(stalled)))

    if action == "pull-models":
        from homedms.ai import ollama
        from homedms.models.classification import AIModelConfig

        config = await db.scalar(select(AIModelConfig).where(AIModelConfig.tenant_id == user.tenant_id))
        client = ollama.client_for(config)
        async with jobs_app.open_async():
            for model in dict.fromkeys((client.chat_model, client.embedding_model)):
                try:
                    await jobs_app.configure_task("pull_model", queueing_lock=f"pull-{model}").defer_async(model=model)
                except AlreadyEnqueued:
                    pass  # Download laeuft schon
        return ActionResult(message=_("Download gestartet - je nach Leitung einige Minuten. Die Seite zeigt es an, sobald es fertig ist."))

    if action == "unload-models":
        from homedms.tasks.system import unload_models

        try:
            count = await unload_models()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, _("KI nicht erreichbar: {error}", error=exc)) from exc
        return ActionResult(message=_n("{count} Modell aus dem Arbeitsspeicher entfernt.", "{count} Modelle aus dem Arbeitsspeicher entfernt.", count))

    if action == "reindex-search":
        from homedms.core import meili
        from homedms.tasks.filing import defer_filing

        try:
            search = meili.client()
            search._settings_applied = False  # noqa: SLF001 - Index-Einstellungen sicher neu setzen
            await search.ensure_settings()
        except meili.SearchUnavailable as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        ids = (await db.execute(select(Document.id).where(Document.tenant_id == user.tenant_id))).scalars().all()
        async with jobs_app.open_async():
            for document_id in ids:
                await defer_filing(document_id)  # Ablage-Auftrag aktualisiert auch den Suchindex
        return ActionResult(message=_n("{count} Dokument wird neu in den Suchindex geschrieben.", "{count} Dokumente werden neu in den Suchindex geschrieben.", len(ids)))

    if action == "install-ocr-languages":
        from homedms.core import ocr_languages

        queued = await ocr_languages.request_installs(db, await ocr_languages.missing(db, user.tenant_id))
        if not queued:
            return ActionResult(message=_("Alle benötigten Sprachpakete sind installiert."))
        return ActionResult(message=_("Download gestartet: {codes}", codes=", ".join(queued)))

    raise HTTPException(status.HTTP_404_NOT_FOUND, _("Unbekannte Aktion"))


# --- Updates -----------------------------------------------------------------------------------------


@router.post("/updates/check", response_model=UpdateStatus)
async def check_updates(user: User = Depends(require_admin)) -> UpdateStatus:
    """Fragt (nur auf Knopfdruck) nach dem neuesten Release. Aktualisiert wird nicht von hier aus."""
    try:
        info = await updates.check(force=True)
    except updates.UpdateCheckError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    logger.info("Update-Prüfung von %s: installiert %s, neueste %s", user.email, info.current, info.latest)
    return UpdateStatus(**info.__dict__)


# --- Datenbanksicherung ------------------------------------------------------------------------------


def _backups_response() -> BackupsResponse:
    settings = get_settings()
    return BackupsResponse(
        available=backup.available(),
        folder=settings.backup_host_path or str(backup.backup_dir()),
        keep=max(1, settings.backup_keep),
        items=[{"name": b.name, "size": b.size, "created": b.created} for b in backup.list_backups()],
    )


@router.get("/backups", response_model=BackupsResponse)
async def list_backups(user: User = Depends(require_admin)) -> BackupsResponse:
    return _backups_response()


@router.post("/backups", response_model=BackupsResponse, status_code=status.HTTP_201_CREATED)
async def create_backup(user: User = Depends(require_admin)) -> BackupsResponse:
    logger.info("Datenbanksicherung von %s gestartet", user.email)
    try:
        await backup.create()
    except backup.BackupError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return _backups_response()


@router.get("/backups/{name}")
async def download_backup(name: str, user: User = Depends(require_admin)) -> FileResponse:
    try:
        path = backup.path_of(name)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Sicherung nicht gefunden")) from None
    return FileResponse(path, media_type="application/octet-stream", filename=name)


@router.delete("/backups/{name}", response_model=BackupsResponse)
async def delete_backup(name: str, user: User = Depends(require_admin)) -> BackupsResponse:
    try:
        backup.delete(name)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Sicherung nicht gefunden")) from None
    logger.info("Sicherung %s von %s gelöscht", name, user.email)
    return _backups_response()