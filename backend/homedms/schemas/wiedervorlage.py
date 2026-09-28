"""Schemas fuer Wiedervorlagen - docs/API-Design.md Abschnitt 6."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel


class WiedervorlageResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    due_date: date
    note: str
    type: str  # retention | custom
    source: str  # manual | ai_suggested | retention_rule
    status: str  # vorgeschlagen | offen | erledigt | verworfen
    confidence: float | None
    source_snippet: str | None  # Textstelle, aus der die KI die Frist abgeleitet hat
    recurrence: str  # none | monthly | yearly | custom_months
    recurrence_interval_months: int | None
    assigned_user_id: uuid.UUID | None
    reminder_lead_days: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WiedervorlageListResponse(BaseModel):
    items: list[WiedervorlageResponse]
    page: int
    page_size: int
    total: int
