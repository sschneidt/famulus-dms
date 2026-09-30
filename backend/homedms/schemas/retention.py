"""Schemas fuer /retention-rules - docs/API-Design.md Abschnitt 7."""
import uuid

from pydantic import BaseModel, Field


class RetentionRuleCreate(BaseModel):
    category_id: uuid.UUID
    retention_period_months: int = Field(ge=1, le=1200, description="z. B. 120 = 10 Jahre")
    requires_original: bool = False
    notify_before_days: int = Field(default=30, ge=0, le=3650)


class RetentionRuleUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    retention_period_months: int | None = Field(default=None, ge=1, le=1200)
    requires_original: bool | None = None
    notify_before_days: int | None = Field(default=None, ge=0, le=3650)


class RetentionRuleResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID | None
    retention_period_months: int | None
    requires_original: bool
    notify_before_days: int

    model_config = {"from_attributes": True}
