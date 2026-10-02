"""Schemas fuer /import-sources - docs/API-Design.md Abschnitt 8 (Scan-Ordner)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImportLogEntry(BaseModel):
    at: str
    file: str
    status: str  # importiert | duplikat | fehler
    message: str = ""
    document_id: uuid.UUID | None = None


class ImportSourceResponse(BaseModel):
    id: uuid.UUID
    type: str
    path: str  # Unterordner im Scan-Ordner, "" = der ganze Scan-Ordner
    is_active: bool
    last_scanned_at: datetime | None
    waiting: int = 0  # Dateien, die noch nicht abgeholt wurden (z. B. noch im Schreiben)
    error: str | None = None
    recent: list[ImportLogEntry] = []


class ImportSourceCreate(BaseModel):
    path: str = Field(default="", max_length=200)


class ImportSourceUpdate(BaseModel):
    path: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None
