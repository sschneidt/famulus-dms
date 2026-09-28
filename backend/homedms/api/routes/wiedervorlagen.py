"""Wiedervorlagen - docs/API-Design.md Abschnitt 6 (Anforderungsdokument 4.4a).

Umgesetzt: Uebersicht, Wiedervorlagen eines Dokuments, KI-Vorschlaege bestaetigen/verwerfen.
Noch offen: manuell anlegen, aendern, erledigen (inkl. automatischer Wiederholung), loeschen,
Erinnerungen - siehe backend/README.md "Was noch fehlt".

Rechte richten sich nach dem zugehoerigen Dokument (homedms/core/visibility.py): sehen, wer das
Dokument sehen darf; bestaetigen/verwerfen, wer es bearbeiten darf.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user
from homedms.core.visibility import is_document_editable, is_document_visible, visible_documents_expr
from homedms.db import get_db
from homedms.models.document import Document
from homedms.models.tenant import User
from homedms.models.wiedervorlage import Wiedervorlage
from homedms.schemas.wiedervorlage import WiedervorlageListResponse, WiedervorlageResponse

router = APIRouter(tags=["wiedervorlagen"])

STATUSES = ("vorgeschlagen", "offen", "erledigt", "verworfen")


@router.get("/wiedervorlagen", response_model=WiedervorlageListResponse)
async def list_wiedervorlagen(
    status_filter: str | None = Query(None, alias="status", description="vorgeschlagen | offen | erledigt | verworfen"),
    due_before: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WiedervorlageListResponse:
    """Haushaltsweite Termin-Uebersicht, frueheste zuerst - nur fuer sichtbare Dokumente, die
    nicht im Papierkorb liegen."""
    if status_filter is not None and status_filter not in STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"status muss einer von {', '.join(STATUSES)} sein")
    conditions = [
        Wiedervorlage.tenant_id == user.tenant_id,
        Document.deleted_at.is_(None),
        visible_documents_expr(user),
    ]
    if status_filter:
        conditions.append(Wiedervorlage.status == status_filter)
    if due_before:
        conditions.append(Wiedervorlage.due_date <= due_before)

    base = select(Wiedervorlage).join(Document, Document.id == Wiedervorlage.document_id).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.execute(
            base.order_by(Wiedervorlage.due_date, Wiedervorlage.id).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return WiedervorlageListResponse(items=list(items), page=page, page_size=page_size, total=total or 0)


@router.get("/documents/{document_id}/wiedervorlagen", response_model=list[WiedervorlageResponse])
async def list_document_wiedervorlagen(
    document_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Wiedervorlage]:
    visible = await is_document_visible(db, user, document_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokument nicht gefunden")
    if not visible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Zugriff auf dieses Dokument")
    result = await db.execute(
        select(Wiedervorlage).where(Wiedervorlage.document_id == document_id)
        .order_by(Wiedervorlage.due_date, Wiedervorlage.id)
    )
    return list(result.scalars().all())


async def _get_editable(db: AsyncSession, user: User, wiedervorlage_id: uuid.UUID) -> Wiedervorlage:
    wv = await db.get(Wiedervorlage, wiedervorlage_id)
    if wv is None or wv.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wiedervorlage nicht gefunden")
    if not await is_document_editable(db, user, wv.document_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Schreibzugriff auf das zugehoerige Dokument")
    return wv


async def _decide_proposal(db: AsyncSession, user: User, wiedervorlage_id: uuid.UUID, new_status: str) -> Wiedervorlage:
    wv = await _get_editable(db, user, wiedervorlage_id)
    if wv.status != "vorgeschlagen":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Nur Vorschlaege koennen bestaetigt oder verworfen werden (Status: {wv.status})")
    wv.status = new_status
    await db.commit()
    return wv


@router.post("/wiedervorlagen/{wiedervorlage_id}/confirm", response_model=WiedervorlageResponse)
async def confirm_wiedervorlage(
    wiedervorlage_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Wiedervorlage:
    """KI-Vorschlag uebernehmen: vorgeschlagen -> offen."""
    return await _decide_proposal(db, user, wiedervorlage_id, "offen")


@router.post("/wiedervorlagen/{wiedervorlage_id}/reject", response_model=WiedervorlageResponse)
async def reject_wiedervorlage(
    wiedervorlage_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Wiedervorlage:
    """KI-Vorschlag verwerfen: vorgeschlagen -> verworfen. Wird nicht erneut vorgeschlagen."""
    return await _decide_proposal(db, user, wiedervorlage_id, "verworfen")
