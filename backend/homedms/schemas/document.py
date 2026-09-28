"""Schemas fuer /documents/* - siehe docs/API-Design.md Abschnitt 5."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel

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

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
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

    title: str | None = None
    original_present: OriginalPresent | None = None
    original_location: str | None = None
