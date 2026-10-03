"""Haushalt (Mandant) anzeigen und umbenennen - docs/API-Design.md Abschnitt 2.

Der Haushaltsname ist zugleich der oberste Ordner in der Ablage (core/filing.py). Nach dem
Umbenennen werden deshalb alle Dokumente des Haushalts neu abgelegt - der Worker verschiebt die
Dateien in den neuen Ordner, der alte leere Ordner wird entfernt.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user, require_admin
from homedms.db import get_db
from homedms.jobs import app as jobs_app
from homedms.models.document import Document
from homedms.models.tenant import Tenant, User
from homedms.schemas.auth import HouseholdResponse, HouseholdUpdate
from homedms.tasks.filing import defer_filing

router = APIRouter(prefix="/tenant", tags=["auth"])


@router.get("", response_model=HouseholdResponse)
async def get_household(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> HouseholdResponse:
    tenant = await db.get(Tenant, user.tenant_id)
    return HouseholdResponse(name=tenant.name)


@router.patch("", response_model=HouseholdResponse)
async def rename_household(
    payload: HouseholdUpdate, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> HouseholdResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bitte einen Namen angeben")
    tenant = await db.get(Tenant, user.tenant_id)
    if tenant.name == name:
        return HouseholdResponse(name=name)
    tenant.name = name
    await db.commit()
    ids = (await db.execute(select(Document.id).where(Document.tenant_id == user.tenant_id))).scalars().all()
    async with jobs_app.open_async():
        for document_id in ids:
            await defer_filing(document_id)
    return HouseholdResponse(name=name, documents_refiled=len(ids))
