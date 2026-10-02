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
import logging
import uuid
from pathlib import Path
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user
from homedms.core import meili
from homedms.core.naming import refresh_title
from homedms.core.pages import PageError, Part, combine, file_page_count
from homedms.core.payments import PAYMENT_PATTERN, mark_paid
from homedms.core.search import has_hit, like_pattern, search_terms, segments_from_marked, snippet_for_terms
from homedms.core.retention import sync_retention
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
    ExtractionStatus,
    OcrStatus,
    OriginalPresent,
    Property,
)
from homedms.models.tenant import UserRole
from homedms.models.wiedervorlage import Wiedervorlage
from homedms.tasks.filing import defer_filing, request_filing
from homedms.models.tenant import User
from homedms.schemas.document import (
    CategoryAssignRequest,
    ClassificationEventResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdateRequest,
    SearchSegment,
    UnpaidListResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def today() -> date:
    """Eigene Funktion, damit Tests ein festes Datum setzen koennen."""
    return date.today()

logger = logging.getLogger("homedms.api.documents")


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
    q: str | None = Query(None, max_length=200, description="Volltextsuche (Titel, Betreff, Absender, Objekt, Text)"),
    payment_status: str | None = Query(None, pattern="^(offen|bezahlt)$", description="Zahlungsstatus"),
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
    if payment_status is not None:
        conditions.append(Document.payment_status == payment_status)

    if q and q.strip():
        return await _search(db, user, q.strip(), conditions, category_id, page, page_size)

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


async def _search(
    db: AsyncSession, user: User, q: str, conditions: list, category_id: uuid.UUID | None, page: int, page_size: int,
) -> DocumentListResponse:
    """Volltextsuche - Ablauf und Gruende fuer die zwei Quellen: homedms/core/search.py."""
    terms = search_terms(q)

    # 1. Meilisearch: tippfehlertolerant, nach Relevanz sortiert
    hits: list[dict] = []
    try:
        hits = await meili.client().search(q, str(user.tenant_id), str(category_id) if category_id else None)
    except meili.SearchUnavailable as exc:
        logger.warning("Suche ohne Meilisearch (nur Teilwort-Suche): %s", exc)
    formatted: dict[uuid.UUID, dict] = {}
    for hit in hits:
        try:
            formatted.setdefault(uuid.UUID(str(hit.get("id"))), hit.get("_formatted") or {})
        except ValueError:
            continue
    ranked = list(formatted)
    allowed = set(
        (await db.execute(select(Document.id).where(*conditions, Document.id.in_(ranked)))).scalars()
    ) if ranked else set()  # Zugriffsrechte und Filter prueft immer die Datenbank

    # 2. Teilwort-Suche in der Datenbank (Wortteile, Rueckfall ohne Meilisearch)
    partial: list[uuid.UUID] = []
    if terms:
        columns = (Document.title, Document.subject, Document.issuer, Document.ocr_text)
        partial = list((await db.execute(
            select(Document.id)
            .where(*conditions, *(or_(*(c.ilike(like_pattern(t), escape="\\") for c in columns)) for t in terms))
            .order_by(Document.created_at.desc())
            .limit(meili.MAX_HITS)
        )).scalars())

    order = [i for i in ranked if i in allowed] + [i for i in partial if i not in allowed]
    page_ids = order[(page - 1) * page_size: page * page_size]
    docs = {d.id: d for d in (await db.execute(select(Document).where(Document.id.in_(page_ids)))).scalars()}

    items = []
    for document_id in page_ids:
        document = docs[document_id]
        segments = segments_from_marked(formatted.get(document_id, {}).get("ocr_text") or "")
        if not has_hit(segments):
            segments = snippet_for_terms(document.ocr_text or "", terms)
        items.append(DocumentResponse.model_validate(document).model_copy(update={
            "search_snippet": [SearchSegment(text=s.text, hit=s.hit) for s in segments] if has_hit(segments) else None,
        }))
    return DocumentListResponse(items=items, page=page, page_size=page_size, total=len(order))


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


@router.get("/unpaid", response_model=UnpaidListResponse)
async def list_unpaid(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UnpaidListResponse:
    """Unbezahlte Rechnungen (payment_status = offen) mit ihrer naechsten Zahlungsfrist - ueberfaellige
    zuerst, ohne Frist am Ende. Ohne Seitenaufteilung: Offene Rechnungen sind im Haushalt wenige."""
    due = (
        select(Wiedervorlage.document_id, func.min(Wiedervorlage.due_date).label("due"))
        .where(
            Wiedervorlage.tenant_id == user.tenant_id,
            Wiedervorlage.status.in_(("offen", "vorgeschlagen")),
            Wiedervorlage.note.op("~*")(PAYMENT_PATTERN),
        )
        .group_by(Wiedervorlage.document_id)
        .subquery()
    )
    rows = (await db.execute(
        select(Document, due.c.due)
        .outerjoin(due, due.c.document_id == Document.id)
        .where(
            Document.tenant_id == user.tenant_id,
            Document.deleted_at.is_(None),
            Document.payment_status == "offen",
            visible_documents_expr(user),
        )
        .order_by(due.c.due.asc().nulls_last(), Document.created_at.desc())
        .limit(500)
    )).all()
    items = [DocumentResponse.model_validate(d).model_copy(update={"payment_due": d_due}) for d, d_due in rows]
    return UnpaidListResponse(
        items=items, total=len(items), total_amount=round(sum(float(d.amount or 0) for d, _ in rows), 2)
    )


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
    file: list[UploadFile] = File(..., description="Eine Datei - oder mehrere, die zu EINEM Dokument werden"),
    title: str = Form(""),
    source: DocumentSource = Form(DocumentSource.upload),
    original_present: OriginalPresent = Form(OriginalPresent.unbekannt),
    original_location: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Mehrere Dateien (z. B. Handy-Fotos eines zweiseitigen Briefs) werden in der gesendeten
    Reihenfolge zu einer PDF zusammengefasst (homedms/core/pages.py)."""
    uploads = [(f.filename or "", f.content_type or "", await f.read()) for f in file]
    if len(uploads) == 1:
        filename, mime, content = uploads[0]
    else:
        try:
            content = combine([Part(c, n, m) for n, m, c in uploads])
        except PageError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        filename, mime = f"{Path(uploads[0][0]).stem or 'Dokument'}.pdf", "application/pdf"

    document = Document(
        tenant_id=user.tenant_id,
        owner_user_id=user.id,
        title=title or filename,
        title_locked=bool(title.strip()),  # selbst vergebener Titel wird nie automatisch ersetzt
        source=source,
        original_present=original_present,
        original_location=original_location,
    )
    db.add(document)
    await db.flush()  # document.id verfuegbar machen, ohne schon zu committen

    path = document_file_path(user.tenant_id, document.id, page_number=1, original_filename=filename)
    checksum = save_upload(path, content)

    db.add(
        DocumentFile(
            document_id=document.id,
            file_path=str(path),
            page_number=1,
            mime_type=mime or "application/octet-stream",
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
) -> DocumentDetailResponse:
    document = await _get_visible_document(db, user, document_id)
    if document.deleted_at is not None:
        # Im Papierkorb - ueber GET /documents/trash sichtbar, nicht ueber die normale Detailansicht.
        raise _not_found()
    pages = file_page_count(document.files[0].file_path) if document.files else 1
    return DocumentDetailResponse.model_validate(document).model_copy(update={"page_count": pages})


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
    if "title" in updates:
        title = (updates["title"] or "").strip()
        if not title:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Titel darf nicht leer sein")
        updates["title"] = title
        # Selbst gesetzter Titel bleibt - ausser im selben Aufruf wird title_locked=false verlangt
        updates.setdefault("title_locked", True)
    if "subject" in updates:
        updates["subject"] = (updates["subject"] or "").strip() or None
    if updates.get("property_id") is not None:
        prop = await db.get(Property, updates["property_id"])
        if prop is None or prop.tenant_id != user.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Objekt nicht gefunden")
    if updates.get("title_locked") is None:
        updates.pop("title_locked", None)
    payment = updates.pop("payment_status", "unset")
    paid_on = updates.pop("paid_on", None)
    if payment == "bezahlt":
        await mark_paid(db, document, paid_on or today(), today=today(), user_id=user.id)
    elif payment == "offen":
        document.payment_status, document.paid_on, document.paid_assumed = "offen", None, False
    elif payment is None:
        document.payment_status, document.paid_on, document.paid_assumed = None, None, False
    elif paid_on is not None:  # nur Zahlungsdatum korrigieren
        if document.payment_status != "bezahlt":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Zahlungsdatum nur bei bezahlten Dokumenten")
        document.paid_on, document.paid_assumed = paid_on, False
    for field, value in updates.items():
        setattr(document, field, value)
    refresh_title(document)  # nur wenn nicht gesperrt: "Betreff – Absender" nachziehen
    if "document_date" in updates:
        await sync_retention(db, document)  # Aufbewahrungsfrist haengt am Dokumentdatum

    await db.commit()
    await request_filing(document.id)  # Dateiname/Ordner folgen Titel, Datum, Absender, Betreff
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
        await request_filing(document.id)  # Datei wandert in den Ordner _Papierkorb


@router.post("/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Document:
    document = await _get_editable_document(db, user, document_id)
    if document.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokument liegt nicht im Papierkorb")
    document.deleted_at = None
    await db.commit()
    await request_filing(document.id)  # zurueck in den Kategorie-Ordner
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
    await sync_retention(db, document)
    await db.commit()

    # Lernbeispiel im Hintergrund anlegen - braucht das Embedding-Modell und soll die Antwort
    # nicht verzoegern.
    async with jobs_app.open_async():
        await jobs_app.configure_task("learn_exemplar").defer_async(
            document_id=str(document.id), category_id=str(category.id), user_id=str(user.id)
        )
        await defer_filing(document.id)  # in den Ordner der neuen Kategorie
    return document


@router.post("/{document_id}/reprocess", response_model=DocumentDetailResponse)
async def reprocess_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Document:
    """KI-Auswertung erneut anstossen, z. B. nach einem KI-Ausfall oder nach verbesserten
    Kategorien. Eine vom Nutzer bestaetigte Kategorie bleibt; Metadaten fuellen weiterhin nur leere
    Felder. War die Texterkennung fehlgeschlagen, laeuft auch sie erneut."""
    document = await _get_editable_document(db, user, document_id)
    if document.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokument liegt im Papierkorb - erst wiederherstellen")
    if document.ocr_status == OcrStatus.pending or document.extraction_status == ExtractionStatus.pending or (
        document.classification_status == ClassificationStatus.pending
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Das Dokument wird gerade schon verarbeitet")

    redo_ocr = document.ocr_status == OcrStatus.failed
    if redo_ocr:
        document.ocr_status = OcrStatus.pending
    if document.classification_status != ClassificationStatus.confirmed:
        document.classification_status = ClassificationStatus.pending
    document.extraction_status = ExtractionStatus.pending
    await db.commit()

    async with jobs_app.open_async():
        if redo_ocr:
            await jobs_app.configure_task("ocr_document").defer_async(document_id=str(document.id))
        else:
            if document.classification_status == ClassificationStatus.pending:
                await jobs_app.configure_task("classify_document").defer_async(document_id=str(document.id))
            await jobs_app.configure_task("extract_metadata").defer_async(document_id=str(document.id))
    await db.refresh(document)
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
