"""Schemas fuer /documents/* - siehe docs/API-Design.md Abschnitt 5."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from homedms.models.document import (
    ClassificationStage,
    ClassificationStatus,
    DocumentSource,
    ExtractionStatus,
    OcrStatus,
    OriginalPresent,
)


class DocumentFileResponse(BaseModel):
    id: uuid.UUID
    page_number: int
    mime_type: str
    filename: str
    # Ablageort relativ zum Dokumente-Ordner, z. B. "Familie/Steuern/2026/2026-03-01 Finanzamt – Bescheid.pdf"
    path: str = ""

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    title_locked: bool = False
    subject: str | None = None
    property_id: uuid.UUID | None = None
    category_id: uuid.UUID | None
    owner_user_id: uuid.UUID
    source: DocumentSource

    ocr_status: OcrStatus
    classification_status: ClassificationStatus
    classification_confidence: float | None
    classification_stage: ClassificationStage | None
    extraction_status: ExtractionStatus

    document_date: date | None
    issuer: str | None
    amount: float | None

    original_present: OriginalPresent
    original_location: str | None

    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    files: list[DocumentFileResponse] = []

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    """Detailansicht (GET /documents/{id}) - zusaetzlich mit dem erkannten Text. In Listen bewusst
    nicht enthalten, weil der Text pro Dokument sehr lang sein kann."""

    ocr_text: str
    ocr_language: str


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    page: int
    page_size: int
    total: int


class DocumentUpdateRequest(BaseModel):
    """Nur die Felder, die sich schon ohne Tag-/Klassifikations-Verwaltung sinnvoll aendern lassen
    (siehe backend/README.md "Was noch fehlt" fuer Tags/Kategorie-Korrektur ueber eigene Endpunkte)."""

    title: str | None = Field(default=None, max_length=300)
    # false = Titel wieder automatisch aus Betreff und Absender bilden
    title_locked: bool | None = None
    subject: str | None = Field(default=None, max_length=300)
    property_id: uuid.UUID | None = None  # Objekt (Haus/Wohnung); null = keinem Objekt zugeordnet
    original_present: OriginalPresent | None = None
    original_location: str | None = None
    # Von der KI erkannte Metadaten korrigieren (null = Feld leeren)
    document_date: date | None = None
    issuer: str | None = Field(default=None, max_length=300)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class CategoryAssignRequest(BaseModel):
    """POST /documents/{id}/category - manuelle Zuordnung bzw. Bestaetigung (Feedback-Loop)."""

    category_id: uuid.UUID


class ClassificationEventResponse(BaseModel):
    id: uuid.UUID
    previous_category_id: uuid.UUID | None
    new_category_id: uuid.UUID | None
    stage: str  # embedding | llm | manual | chat
    confidence: float | None
    note: str | None
    triggered_by_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
