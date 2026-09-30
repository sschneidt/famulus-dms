"""Wiedervorlagen - docs/API-Design.md Abschnitt 6 (Anforderungsdokument 4.4a).

Uebersicht, Wiedervorlagen eines Dokuments, manuell anlegen, aendern (auch KI-Vorschlaege vor dem
Bestaetigen), bestaetigen/verwerfen, erledigen (bei Wiederholung mit automatischem Folgetermin),
loeschen. Erinnerungen per Benachrichtigung folgen mit Abschnitt 9 (Benachrichtigungen).

Rechte richten sich nach dem zugehoerigen Dokument (homedms/core/visibility.py): sehen, wer das
Dokument sehen darf; bestaetigen/verwerfen, wer es bearbeiten darf.
"""
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user
from homedms.core.visibility import is_document_editable, is_document_visible, visible_documents_expr
from homedms.db import get_db
from homedms.core.wiedervorlage import EDITABLE_STATUSES, next_due
from homedms.models.document import Document
from homedms.models.tenant import User
from homedms.models.wiedervorlage import Wiedervorlage
from homedms.schemas.wiedervorlage import (
    WiedervorlageCompleteResponse,
    WiedervorlageCreate,
    WiedervorlageListResponse,
    WiedervorlageResponse,
    WiedervorlageUpdate,
)

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


def today() -> date:
    """Eigene Funktion, damit Tests ein festes Datum setzen koennen."""
    return date.today()


async def _check_assignee(db: AsyncSession, user: User, assigned_user_id: uuid.UUID | None) -> None:
    if assigned_user_id is None:
        return
    assignee = await db.get(User, assigned_user_id)
    if assignee is None or assignee.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "assigned_user_id ist kein Mitglied dieses Haushalts")


@router.post("/documents/{document_id}/wiedervorlagen", response_model=WiedervorlageResponse,
             status_code=status.HTTP_201_CREATED)
async def create_wiedervorlage(
    document_id: uuid.UUID, payload: WiedervorlageCreate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> Wiedervorlage:
    editable = await is_document_editable(db, user, document_id)
    if editable is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokument nicht gefunden")
    if not editable:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Schreibzugriff auf dieses Dokument")
    document = await db.get(Document, document_id)
    if document.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokument liegt im Papierkorb - erst wiederherstellen")
    await _check_assignee(db, user, payload.assigned_user_id)

    wv = Wiedervorlage(
        tenant_id=user.tenant_id, document_id=document_id, due_date=payload.due_date, note=payload.note,
        type="custom", source="manual", status="offen", recurrence=payload.recurrence,
        recurrence_interval_months=payload.recurrence_interval_months,
        assigned_user_id=payload.assigned_user_id or document.owner_user_id,
        created_by_user_id=user.id, reminder_lead_days=payload.reminder_lead_days,
    )
    db.add(wv)
    await db.commit()
    return wv


@router.patch("/wiedervorlagen/{wiedervorlage_id}", response_model=WiedervorlageResponse)
async def update_wiedervorlage(
    wiedervorlage_id: uuid.UUID, payload: WiedervorlageUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> Wiedervorlage:
    wv = await _get_editable(db, user, wiedervorlage_id)
    if wv.status not in EDITABLE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Wiedervorlage ist {wv.status} und kann nicht mehr geaendert werden")
    updates = payload.model_dump(exclude_unset=True)
    for field in ("due_date", "note", "recurrence", "reminder_lead_days"):
        if field in updates and updates[field] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} darf nicht leer sein")
    if wv.source == "retention_rule" and "due_date" in updates and updates["due_date"] != wv.due_date:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Der Termin ergibt sich aus der Aufbewahrungsregel - bitte dort bzw. am Dokumentdatum aendern")
    if "assigned_user_id" in updates:
        await _check_assignee(db, user, updates["assigned_user_id"])

    recurrence = updates.get("recurrence", wv.recurrence)
    interval = updates.get("recurrence_interval_months", wv.recurrence_interval_months)
    if recurrence == "custom_months" and not interval:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Bei recurrence=custom_months ist recurrence_interval_months (1-120) noetig")
    if recurrence != "custom_months":
        updates["recurrence_interval_months"] = None

    for field, value in updates.items():
        setattr(wv, field, value)
    await db.commit()
    return wv


@router.post("/wiedervorlagen/{wiedervorlage_id}/complete", response_model=WiedervorlageCompleteResponse)
async def complete_wiedervorlage(
    wiedervorlage_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WiedervorlageCompleteResponse:
    """Als erledigt markieren. Bei Wiederholung wird sofort der naechste Termin angelegt - wurde
    zu spaet erledigt, der naechste in der Zukunft (keine Reihe verpasster Termine)."""
    wv = await _get_editable(db, user, wiedervorlage_id)
    if wv.status != "offen":
        hint = " - Vorschlaege zuerst bestaetigen" if wv.status == "vorgeschlagen" else ""
        raise HTTPException(status.HTTP_409_CONFLICT, f"Nur offene Wiedervorlagen koennen erledigt werden (Status: {wv.status}){hint}")

    wv.status = "erledigt"
    wv.completed_at = datetime.now(timezone.utc)
    wv.completed_by_user_id = user.id

    follow_up = None
    due = next_due(wv.due_date, wv.recurrence, wv.recurrence_interval_months, today())
    if due is not None:
        follow_up = Wiedervorlage(
            tenant_id=wv.tenant_id, document_id=wv.document_id, due_date=due, note=wv.note, type=wv.type,
            source=wv.source, status="offen", confidence=wv.confidence, source_snippet=wv.source_snippet,
            recurrence=wv.recurrence, recurrence_interval_months=wv.recurrence_interval_months,
            assigned_user_id=wv.assigned_user_id, created_by_user_id=wv.created_by_user_id,
            reminder_lead_days=wv.reminder_lead_days,
        )
        db.add(follow_up)
    await db.commit()
    return WiedervorlageCompleteResponse(
        completed=WiedervorlageResponse.model_validate(wv),
        next=WiedervorlageResponse.model_validate(follow_up) if follow_up else None,
    )


@router.delete("/wiedervorlagen/{wiedervorlage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wiedervorlage(
    wiedervorlage_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    """Endgueltig loeschen. Hinweis: Termine aus einer Aufbewahrungsregel entstehen neu, sobald sich
    Kategorie oder Datum des Dokuments aendern - dauerhaft entfernen laesst sich so ein Termin ueber
    die Regel selbst."""
    wv = await _get_editable(db, user, wiedervorlage_id)
    await db.delete(wv)
    await db.commit()
