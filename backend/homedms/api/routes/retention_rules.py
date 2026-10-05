"""Aufbewahrungsregeln - docs/API-Design.md Abschnitt 7 (nur Admin).

Eine Regel je Kategorie. Jede Aenderung wird sofort auf alle Dokumente der betroffenen
Kategorie(n) angewendet (homedms/core/retention.py). Bewusst ohne vorbelegte Regeln: Welche
Fristen gelten, haengt vom Einzelfall ab und ist keine Entscheidung, die die Software trifft.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import require_admin
from homedms.core.retention import sync_category
from homedms.db import get_db
from homedms.models.document import Category
from homedms.models.tenant import User
from homedms.models.wiedervorlage import RetentionRule
from homedms.schemas.retention import RetentionRuleCreate, RetentionRuleResponse, RetentionRuleUpdate
from homedms.i18n import _

router = APIRouter(prefix="/retention-rules", tags=["retention-rules"])


async def _check_category(db: AsyncSession, user: User, category_id: uuid.UUID, exclude_rule: uuid.UUID | None = None) -> None:
    category = await db.get(Category, category_id)
    if category is None or category.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Kategorie nicht gefunden"))
    clash = await db.scalar(
        select(RetentionRule.id).where(
            RetentionRule.tenant_id == user.tenant_id,
            RetentionRule.category_id == category_id,
            *([RetentionRule.id != exclude_rule] if exclude_rule else []),
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Fuer diese Kategorie gibt es schon eine Aufbewahrungsregel"))


async def _get(db: AsyncSession, user: User, rule_id: uuid.UUID) -> RetentionRule:
    rule = await db.get(RetentionRule, rule_id)
    if rule is None or rule.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Aufbewahrungsregel nicht gefunden"))
    return rule


@router.get("", response_model=list[RetentionRuleResponse])
async def list_rules(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> list[RetentionRule]:
    result = await db.execute(select(RetentionRule).where(RetentionRule.tenant_id == user.tenant_id))
    return list(result.scalars().all())


@router.post("", response_model=RetentionRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RetentionRuleCreate, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> RetentionRule:
    await _check_category(db, user, payload.category_id)
    rule = RetentionRule(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(rule)
    await db.flush()
    await sync_category(db, user.tenant_id, rule.category_id)
    await db.commit()
    return rule


@router.patch("/{rule_id}", response_model=RetentionRuleResponse)
async def update_rule(
    rule_id: uuid.UUID, payload: RetentionRuleUpdate,
    user: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
) -> RetentionRule:
    rule = await _get(db, user, rule_id)
    updates = payload.model_dump(exclude_unset=True)
    for field in ("retention_period_months", "requires_original", "notify_before_days", "category_id"):
        if field in updates and updates[field] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("{field} darf nicht leer sein", field=field))
    old_category = rule.category_id
    if "category_id" in updates and updates["category_id"] != old_category:
        await _check_category(db, user, updates["category_id"], exclude_rule=rule.id)
    for field, value in updates.items():
        setattr(rule, field, value)
    await db.flush()
    await sync_category(db, user.tenant_id, old_category)
    if rule.category_id != old_category:
        await sync_category(db, user.tenant_id, rule.category_id)
    await db.commit()
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> None:
    rule = await _get(db, user, rule_id)
    category_id = rule.category_id
    await db.delete(rule)
    await db.flush()
    await sync_category(db, user.tenant_id, category_id)  # entfernt offene Aufbewahrungs-Termine
    await db.commit()
