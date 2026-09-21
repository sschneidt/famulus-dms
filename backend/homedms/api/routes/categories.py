"""GET/POST /categories - docs/API-Design.md Abschnitt 4. Dient als Referenz-Pattern fuer
tenant-gescopte CRUD-Endpunkte: weitere Ressourcen (Dokumente, Tags, ...) folgen demselben Muster.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user, require_admin
from homedms.db import get_db
from homedms.models.document import Category
from homedms.models.tenant import User
from homedms.schemas.category import CategoryCreateRequest, CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Category]:
    result = await db.execute(select(Category).where(Category.tenant_id == user.tenant_id).order_by(Category.name))
    return list(result.scalars().all())


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Category:
    category = Category(
        tenant_id=user.tenant_id,
        name=payload.name,
        description=payload.description,
        is_restricted=payload.is_restricted,
        is_system_default=False,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category
