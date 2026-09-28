"""Dokumente - docs/API-Design.md Abschnitt 5.

Umgesetzt in dieser Iteration: Liste/Filter/Pagination, Upload (Foto-Import/manueller Upload
decken denselben Endpunkt ab - siehe Anforderungsdokument 4.1), Detail, Teil-Update, Soft-Delete
+ Wiederherstellung, Papierkorb, Feedback-Loop-Warteschlange, Download. Das Sichtbarkeitsmodell
(Datenmodell 3.6) wird ueberall angewendet (homedms/core/visibility.py).

Noch nicht umgesetzt (siehe backend/README.md "Was noch fehlt"): Mehrseiten-Dateien
hinzufuegen/entfernen, Kategorie-Korrektur/Klassifikations-Verlauf, Massen-Umkategorisierung,
Zugriffs-Ausnahmen verwalten, Tag-Zuordnung, Volltextsuche (Meilisearch) - der `q`-Parameter aus
der API-Design ist hier bewusst noch nicht angeschlossen. OCR/Klassifikation laufen nach dem
Upload noch nicht automatisch an (kein Worker-Task dafuer vorhanden) - Dokumente bleiben bis dahin
im Status "pending".
"""
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user
from homedms.core.storage import document_file_path, save_upload
from homedms.core.visibility import is_document_editable, is_document_visible, visible_documents_expr
from homedms.db import get_db
from homedms.jobs import app as jobs_app
from homedms.models.classification import ClassificationEvent
from homedms.models.document import (
    Category,
    CategoryAccess,
    ClassificationStage,
    ClassificationStatus,
    Document,
    DocumentFile,
    DocumentSource,
    OriginalPresent,
)
from homedms.models.tenant import UserRole
from homedms.models.tenant import User
from homedms.schemas.document import (
    CategoryAssignRequest,
    ClassificationEventResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdateRequest,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Dokument nicht gefunden")


async def _get_visible_document(db: AsyncSession, user: User, document_id: uuid.UUID) -> Document:
    """Fuer GET-artige Zugriffe: 404 wenn nicht vorhanden (im Tenant), 403 wenn vorhanden aber
    nicht sichtbar (docs/API-Design.md 1: "ein direkter Zugriff per ID liefert 403")."""
    visible = await is_document_visible(db, user, document_id)
    if visible is None:
        raise _not_found()
    if not visible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Zugriff auf dieses Dokument")
    document = await db.get(Document, document_id)
    assert document is not None
    return document


async def _get_editable_document(db: AsyncSession, user: User, document_id: uuid.UUID) -> Document:
    editable = await is_document_editable(db, user, document_id)
    if editable is None:
        raise _not_found()
    if not editable:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Schreibzugriff auf dieses Dokument")
    document = await db.get(Document, document_id)
    assert document is not None
    return document


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    category_id: uuid.UUID | None = None,
    status_filter: ClassificationStatus | None = Query(None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    conditions = [
        Document.tenant_id == user.tenant_id,
        Document.deleted_at.is_(None),
        visible_documents_expr(user),
    ]
    if category_id is not None:
        conditions.append(Document.category_id == category_id)
    if status_filter is not None:
        conditions.append(Document.classification_status == status_filter)
    if date_from is not None:
        conditions.append(Document.document_date >= date_from)
    if date_to is not None:
        conditions.append(Document.document_date <= date_to)

    total = await db.scalar(select(func.count()).select_from(Document).where(*conditions))

    result = await db.execute(
        select(Document)
        .where(*conditions)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return DocumentListResponse(items=items, page=page, page_size=page_size, total=total or 0)


@router.get("/needs-review", response_model=DocumentListResponse)
async def list_needs_review(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    conditions = [
        Document.tenant_id == user.tenant_id,
        Document.deleted_at.is_(None),
        Document.classification_status == ClassificationStatus.needs_review,
        visible_documents_expr(user),
    ]
    total = await db.scalar(select(func.count()).select_from(Document).where(*conditions))
    result = await db.execute(
        select(Document)
        .where(*conditions)
        .order_by(Document.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return DocumentListResponse(items=items, page=page, page_size=page_size, total=total or 0)


@router.get("/trash", response_model=DocumentListResponse)
async def list_trash(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """Papierkorb (Datenmodell 3.5: 30 Tage wiederherstellbar). Der Hintergrund-Job, der nach
    30 Tagen endgueltig loescht, ist noch nicht implementiert (siehe README "Was noch fehlt")."""
    conditions = [
        Document.tenant_id == user.tenant_id,
        Document.deleted_at.isnot(None),
        visible_documents_expr(user),
    ]
    total = await db.scalar(select(func.count()).select_from(Document).where(*conditions))
    result = await db.execute(
        select(Document)
        .where(*conditions)
        .order_by(Document.deleted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return DocumentListResponse(items=items, page=page, page_size=page_size, total=total or 0)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    source: DocumentSource = Form(DocumentSource.upload),
    original_present: OriginalPresent = Form(OriginalPresent.unbekannt),
    original_location: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = Document(
        tenant_id=user.tenant_id,
        owner_user_id=user.id,
        title=title or (file.filename or ""),
        source=source,
        original_present=original_present,
        original_location=original_location,
    )
    db.add(document)
    await db.flush()  # document.id verfuegbar machen, ohne schon zu committen

    content = await file.read()
    path = document_file_path(user.tenant_id, document.id, page_number=1, original_filename=file.filename or "")
    checksum = save_upload(path, content)

    db.add(
        DocumentFile(
            document_id=document.id,
            file_path=str(path),
            page_number=1,
            mime_type=file.content_type or "application/octet-stream",
            checksum=checksum,
        )
    )

    await db.commit()
    await db.refresh(document, attribute_names=["files"])

    # OCR-Job einreihen (homedms/tasks/ocr.py, ausgefuehrt vom app-worker-Prozess). Der
    # Connector wird hier pro Request kurz geoeffnet/geschlossen statt dauerhaft offen gehalten -
    # bei dem geplanten Volumen (< 50 Dokumente/Monat, Anforderungsdokument 2) unkritisch; bei
    # groesserem Durchsatz waere ein beim App-Start einmal geoeffneter Pool effizienter.
    async with jobs_app.open_async():
        await jobs_app.configure_task("ocr_document", queue="default").defer_async(
            document_id=str(document.id)
        )

    return document


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Document:
    document = await _get_visible_document(db, user, document_id)
    if document.deleted_at is not None:
        # Im Papierkorb - ueber GET /documents/trash sichtbar, nicht ueber die normale Detailansicht.
        raise _not_found()
    return document


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = await _get_editable_document(db, user, document_id)
    if document.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokument liegt im Papierkorb - erst wiederherstellen")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(document, field, value)

    await db.commit()
    await db.refresh(document, attribute_names=["files"])
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    document = await _get_editable_document(db, user, document_id)
    if document.deleted_at is None:
        document.deleted_at = datetime.now(timezone.utc)
        await db.commit()


@router.post("/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Document:
    document = await _get_editable_document(db, user, document_id)
    if document.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokument liegt nicht im Papierkorb")
    document.deleted_at = None
    await db.commit()
    await db.refresh(document, attribute_names=["files"])
    return document


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    document = await _get_visible_document(db, user, document_id)
    first_file = next((f for f in sorted(document.files, key=lambda f: f.page_number)), None)
    if first_file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keine Datei zu diesem Dokument vorhanden")
    return FileResponse(
        path=first_file.file_path,
        media_type=first_file.mime_type,
        filename=first_file.filename,
    )


@router.post("/{document_id}/category", response_model=DocumentDetailResponse)
async def assign_category(
    document_id: uuid.UUID,
    payload: CategoryAssignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Kategorie manuell setzen oder einen KI-Vorschlag bestaetigen (Feedback-Loop,
    Anforderungsdokument 4.3). Das Dokument wird danach nie mehr automatisch umkategorisiert und
    dient als neues Lernbeispiel fuer die Klassifikation."""
    document = await _get_editable_document(db, user, document_id)
    if document.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokument liegt im Papierkorb - erst wiederherstellen")

    category = await db.get(Category, payload.category_id)
    if category is None or category.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategorie nicht gefunden")
    if category.is_restricted and user.role != UserRole.admin:
        allowed = await db.scalar(
            select(CategoryAccess.can_edit).where(
                CategoryAccess.category_id == category.id, CategoryAccess.user_id == user.id
            )
        )
        if not allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine Berechtigung fuer diese Kategorie")

    note = "Kategorie bestaetigt" if document.category_id == category.id else "Kategorie manuell zugeordnet"
    db.add(ClassificationEvent(
        document_id=document.id, previous_category_id=document.category_id, new_category_id=category.id,
        stage="manual", confidence=None, triggered_by_user_id=user.id, note=note,
    ))
    document.category_id = category.id
    document.classification_status = ClassificationStatus.confirmed
    document.classification_stage = ClassificationStage.manual
    document.classification_confidence = None
    await db.commit()

    # Lernbeispiel im Hintergrund anlegen - braucht das Embedding-Modell und soll die Antwort
    # nicht verzoegern.
    async with jobs_app.open_async():
        await jobs_app.configure_task("learn_exemplar").defer_async(
            document_id=str(document.id), category_id=str(category.id), user_id=str(user.id)
        )
    return document


@router.get("/{document_id}/classification-history", response_model=list[ClassificationEventResponse])
async def classification_history(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ClassificationEvent]:
    await _get_visible_document(db, user, document_id)
    result = await db.execute(
        select(ClassificationEvent)
        .where(ClassificationEvent.document_id == document_id)
        .order_by(ClassificationEvent.created_at, ClassificationEvent.id)
    )
    return list(result.scalars().all())
