"""Seiten eines Dokuments - docs/API-Design.md 5 ("Mehrseiten-Scan"), Logik in homedms/core/pages.py.

Jede Aenderung schreibt die PDF neu (atomar: erst neue Datei, dann umbenennen) und stoesst die
Auswertung erneut an: Texterkennung ueber alle Seiten, danach Kategorie (ausser vom Nutzer
bestaetigt), Metadaten fuer noch leere Felder, Ablage.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user
from homedms.api.routes.documents import _get_editable_document, _get_visible_document
from homedms.core import pages
from homedms.core.storage import replace_with_pdf
from homedms.db import get_db
from homedms.jobs import app as jobs_app
from homedms.models.document import (
    ClassificationStatus,
    Document,
    DocumentFile,
    ExtractionStatus,
    OcrStatus,
)
from homedms.models.tenant import User
from homedms.i18n import _

router = APIRouter(prefix="/documents", tags=["documents"])


class PageOrder(BaseModel):
    order: list[int]  # neue Reihenfolge, 1-basierte Seitennummern


class PagesResponse(BaseModel):
    page_count: int


def _current(document: Document) -> tuple[DocumentFile, pages.Part]:
    if not document.files:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Keine Datei zu diesem Dokument vorhanden"))
    file = document.files[0]
    try:
        content = Path(file.file_path).read_bytes()
    except OSError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Datei nicht gefunden")) from exc
    return file, pages.Part(content, Path(file.file_path).name, file.mime_type)


async def _editable(db: AsyncSession, user: User, document_id: uuid.UUID) -> Document:
    document = await _get_editable_document(db, user, document_id)
    if document.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Dokument liegt im Papierkorb - erst wiederherstellen"))
    if document.ocr_status == OcrStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Das Dokument wird gerade verarbeitet - bitte kurz warten"))
    return document


async def _save(db: AsyncSession, document: Document, file: DocumentFile, content: bytes) -> PagesResponse:
    replace_with_pdf(file, content)  # atomar, siehe core/storage.py

    # Neu auswerten: Text aller Seiten -> Kategorie (ausser bestaetigt) -> leere Metadaten -> Ablage
    document.ocr_status = OcrStatus.pending
    if document.classification_status != ClassificationStatus.confirmed:
        document.classification_status = ClassificationStatus.pending
    document.extraction_status = ExtractionStatus.pending
    await db.commit()
    async with jobs_app.open_async():
        await jobs_app.configure_task("ocr_document", queue="default").defer_async(document_id=str(document.id))
    return PagesResponse(page_count=pages.page_count(content))


def _apply(fn, *args):
    try:
        return fn(*args)
    except pages.PageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/{document_id}/pages", response_model=PagesResponse)
async def add_pages(
    document_id: uuid.UUID,
    file: list[UploadFile] = File(..., description="Neue Seiten (PDF oder Bilder) in dieser Reihenfolge"),
    position: int | None = Form(None, description="Vor dieser Seite einfuegen (1-basiert); leer = ans Ende"),
    auto_crop: list[bool] = Form([], description="Je Datei: Foto zuschneiden + gerade richten (Standard ja)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PagesResponse:
    document = await _editable(db, user, document_id)
    current_file, current = _current(document)
    parts = [
        pages.Part(await f.read(), f.filename or "", f.content_type or "", auto_crop=auto_crop[i] if i < len(auto_crop) else True)
        for i, f in enumerate(file)
    ]
    pdf = _apply(pages.as_pdf, current)
    # Fotos werden dabei zugeschnitten - Rechenarbeit im Thread, nicht im Event-Loop
    content = await run_in_threadpool(_apply, pages.insert_pages, pdf, parts, position)
    return await _save(db, document, current_file, content)


@router.delete("/{document_id}/pages/{page}", response_model=PagesResponse)
async def delete_page(
    document_id: uuid.UUID, page: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PagesResponse:
    document = await _editable(db, user, document_id)
    current_file, current = _current(document)
    pdf = _apply(pages.as_pdf, current)
    return await _save(db, document, current_file, _apply(pages.delete_page, pdf, page))


@router.put("/{document_id}/pages/order", response_model=PagesResponse)
async def reorder_pages(
    document_id: uuid.UUID, payload: PageOrder,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> PagesResponse:
    document = await _editable(db, user, document_id)
    current_file, current = _current(document)
    pdf = _apply(pages.as_pdf, current)
    return await _save(db, document, current_file, _apply(pages.reorder, pdf, payload.order))


@router.post("/{document_id}/pages/{page}/rectify", response_model=PagesResponse)
async def rectify_page(
    document_id: uuid.UUID, page: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PagesResponse:
    """Eine Foto-/Scan-Seite nachtraeglich zuschneiden und gerade richten (z. B. vor der Funktion
    hochgeladene Fotos). 422, wenn weder Blattrand noch Schraeglage zu erkennen ist."""
    document = await _editable(db, user, document_id)
    current_file, current = _current(document)
    pdf = _apply(pages.as_pdf, current)
    content = await run_in_threadpool(_apply, pages.rectify_page, pdf, page)
    return await _save(db, document, current_file, content)


@router.get("/{document_id}/pages/{page}/thumbnail")
async def page_thumbnail(
    document_id: uuid.UUID, page: int, width: int = Query(240, ge=60, le=1200),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> Response:
    document = await _get_visible_document(db, user, document_id)
    current_file, current = _current(document)
    png = _apply(pages.thumbnail, current, page, width)
    # Inhalt aendert sich mit jeder Seitenaenderung -> Pruefsumme als Cache-Schluessel
    return Response(png, media_type="image/png", headers={
        "Cache-Control": "private, max-age=3600", "ETag": f'"{current_file.checksum[:16]}-{page}-{width}"',
    })


# --- Foto-Vorschau beim Hochladen --------------------------------------------------------------

photos_router = APIRouter(prefix="/photos", tags=["documents"])

MAX_PREVIEW_BYTES = 50 * 1024 * 1024


@photos_router.post(
    "/rectify",
    responses={200: {"content": {"image/jpeg": {}}, "description": "Aufbereitetes Foto als JPEG"}},
    response_class=Response,
)
async def rectify_photo(
    file: UploadFile = File(..., description="Ein Foto (JPEG, PNG, HEIC ...)"),
    user: User = Depends(get_current_user),
) -> Response:
    """Foto zuschneiden, entzerren und gerade richten - nur Vorschau, es wird nichts gespeichert.

    Die Weboberflaeche zeigt das Ergebnis direkt nach der Aufnahme an; der Nutzer kann dann
    zwischen aufbereitet und Original waehlen. Kopfzeilen: X-Cropped (true/false), X-Skew (Grad).
    """
    content = await file.read(MAX_PREVIEW_BYTES + 1)
    if len(content) > MAX_PREVIEW_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, _("Foto zu gross (max. 50 MB)"))
    if pages.Part(content, file.filename or "", file.content_type or "").kind != "image":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Nur Fotos lassen sich zuschneiden"))
    # Rechenarbeit (ca. 0,5 s) nicht im Event-Loop - sonst stockt die API fuer alle anderen
    jpeg, result = await run_in_threadpool(_apply, pages.preview, content)
    return Response(jpeg, media_type="image/jpeg", headers={
        "X-Cropped": "true" if result.cropped else "false",
        "X-Skew": f"{result.skew:.1f}",
        "Cache-Control": "no-store",
    })
