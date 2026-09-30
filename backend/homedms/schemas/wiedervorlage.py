"""Schemas fuer Wiedervorlagen - docs/API-Design.md Abschnitt 6."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    # Nur in der haushaltsweiten Uebersicht gefuellt - damit die Oberflaeche nicht fuer jeden
    # Termin einzeln das Dokument nachladen muss.
    document_title: str | None = None

    model_config = {"from_attributes": True}


class WiedervorlageListResponse(BaseModel):
    items: list[WiedervorlageResponse]
    page: int
    page_size: int
    total: int


Recurrence = Literal["none", "monthly", "yearly", "custom_months"]


class WiedervorlageCreate(BaseModel):
    """POST /documents/{id}/wiedervorlagen - manuell angelegter Termin (Status sofort "offen")."""

    due_date: date
    note: str = Field(min_length=1, max_length=1000)
    recurrence: Recurrence = "none"
    recurrence_interval_months: int | None = Field(default=None, ge=1, le=120)
    assigned_user_id: uuid.UUID | None = None  # Standard: Eigentuemer des Dokuments
    reminder_lead_days: int = Field(default=30, ge=0, le=3650)

    @model_validator(mode="after")
    def _interval(self):
        if self.recurrence == "custom_months" and not self.recurrence_interval_months:
            raise ValueError("Bei recurrence=custom_months ist recurrence_interval_months (1-120) noetig")
        if self.recurrence != "custom_months":
            self.recurrence_interval_months = None
        return self


class WiedervorlageUpdate(BaseModel):
    """PATCH /wiedervorlagen/{id} - auch zum Korrigieren eines KI-Vorschlags vor dem Bestaetigen."""

    due_date: date | None = None
    note: str | None = Field(default=None, min_length=1, max_length=1000)
    recurrence: Recurrence | None = None
    recurrence_interval_months: int | None = Field(default=None, ge=1, le=120)
    assigned_user_id: uuid.UUID | None = None
    reminder_lead_days: int | None = Field(default=None, ge=0, le=3650)


class WiedervorlageCompleteResponse(BaseModel):
    completed: WiedervorlageResponse
    next: WiedervorlageResponse | None  # automatisch angelegter Folgetermin bei Wiederholung
