"""Objekte (Haus/Wohnung) - Ablage pro Adresse, siehe homedms/core/addresses.py.

Objekte entstehen automatisch, wenn die KI eine neue Adresse erkennt, oder von Hand (POST). Hier lassen sie sich
umbenennen (= Ordnername auf dem NAS), doppelt erkannte zusammenfuehren oder loeschen. Jede
Aenderung zieht die Ablage der betroffenen Dokumente nach. Objekte gehoeren dem ganzen Haushalt -
jedes Mitglied darf sie pflegen.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user
from homedms.db import get_db
from homedms.jobs import app as jobs_app
from homedms.models.document import Document, Property
from homedms.models.tenant import User
from homedms.core.addresses import Address, normalize_street
from homedms.schemas.property import PropertyCreate, PropertyMerge, PropertyResponse, PropertyUpdate
from homedms.tasks.filing import defer_filing
from homedms.i18n import _

router = APIRouter(prefix="/properties", tags=["properties"])


async def _get(db: AsyncSession, user: User, property_id: uuid.UUID) -> Property:
    prop = await db.get(Property, property_id)
    if prop is None or prop.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Objekt nicht gefunden"))
    return prop


async def _document_ids(db: AsyncSession, property_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(select(Document.id).where(Document.property_id == property_id))).scalars())


async def _refile(document_ids: list[uuid.UUID]) -> None:
    if not document_ids:
        return
    async with jobs_app.open_async():
        for document_id in document_ids:
            await defer_filing(document_id)


async def _response(db: AsyncSession, prop: Property) -> PropertyResponse:
    count = await db.scalar(
        select(func.count()).select_from(Document).where(Document.property_id == prop.id, Document.deleted_at.is_(None))
    )
    return PropertyResponse.model_validate(prop).model_copy(update={"document_count": count or 0})


@router.get("", response_model=list[PropertyResponse])
async def list_properties(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[PropertyResponse]:
    counts = (
        select(Document.property_id, func.count().label("n"))
        .where(Document.tenant_id == user.tenant_id, Document.deleted_at.is_(None))
        .group_by(Document.property_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Property, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.property_id == Property.id)
            .where(Property.tenant_id == user.tenant_id)
            .order_by(Property.name)
        )
    ).all()
    return [PropertyResponse.model_validate(p).model_copy(update={"document_count": n}) for p, n in rows]


@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(
    payload: PropertyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PropertyResponse:
    """Objekt von Hand anlegen (Seite "Objekte" oder beim Zuordnen im Dokument). Ohne Adresse erkennt die KI es nicht
    von selbst wieder - mit Adresse schon: dieselbe Adresse in einem Dokument landet dann in diesem Objekt."""
    name = payload.name.strip()
    street, postal_code, city = payload.street.strip(), payload.postal_code.strip(), payload.city.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Name darf nicht leer sein"))
    if any((street, postal_code, city)) and not all((street, postal_code, city)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Bitte Straße, Postleitzahl und Ort zusammen angeben oder alle drei leer lassen"))
    if await db.scalar(select(Property.id).where(Property.tenant_id == user.tenant_id, func.lower(Property.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, _("Ein Objekt mit diesem Namen gibt es schon"))
    key = Address(street, postal_code, city).match_key if street else f"name|{normalize_street(name)}"
    twin = await db.scalar(select(Property).where(Property.tenant_id == user.tenant_id, Property.match_key == key))
    if twin is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Für diese Adresse gibt es schon das Objekt „{name}“", name=twin.name))
    prop = Property(tenant_id=user.tenant_id, name=name, street=street, postal_code=postal_code, city=city, match_key=key)
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    return await _response(db, prop)


@router.patch("/{property_id}", response_model=PropertyResponse)
async def rename_property(
    property_id: uuid.UUID, payload: PropertyUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> PropertyResponse:
    prop = await _get(db, user, property_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Name darf nicht leer sein"))
    clash = await db.scalar(
        select(Property.id).where(
            Property.tenant_id == user.tenant_id, func.lower(Property.name) == name.lower(), Property.id != prop.id
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Ein Objekt mit diesem Namen gibt es schon - ggf. zusammenfuehren"))
    prop.name = name
    await db.commit()
    await _refile(await _document_ids(db, prop.id))  # Ordner auf dem NAS umbenennen
    return await _response(db, prop)


@router.post("/{property_id}/merge", response_model=PropertyResponse)
async def merge_property(
    property_id: uuid.UUID, payload: PropertyMerge,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> PropertyResponse:
    source = await _get(db, user, property_id)
    target = await _get(db, user, payload.into_id)
    if source.id == target.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Ein Objekt kann nicht mit sich selbst zusammengefuehrt werden"))
    moved = await _document_ids(db, source.id)
    await db.execute(update(Document).where(Document.property_id == source.id).values(property_id=target.id))
    await db.delete(source)
    await db.commit()
    await _refile(moved)
    return await _response(db, target)


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    """Dokumente bleiben erhalten und landen im Ordner "_Ohne Adresse"."""
    prop = await _get(db, user, property_id)
    affected = await _document_ids(db, prop.id)
    await db.delete(prop)
    await db.commit()
    await _refile(affected)
