"""Schemas fuer /system - Seite "Diagnose"."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DiagnosticDetail(BaseModel):
    label: str
    value: str


class DiagnosticAction(BaseModel):
    id: str
    label: str
    confirm: str | None = None


class DiagnosticComponent(BaseModel):
    key: str
    name: str
    status: Literal["ok", "warning", "error", "disabled"]
    summary: str
    details: list[DiagnosticDetail] = []
    hint: str | None = None
    actions: list[DiagnosticAction] = []


class FailedJob(BaseModel):
    job_id: int
    task: str
    at: datetime
    document_id: uuid.UUID | None = None
    document_title: str | None = None


class DiagnosticsResponse(BaseModel):
    version: str  # installierte Famulus-DMS-Version (homedms/__init__.py) - nur fuer Admins sichtbar
    checked_at: datetime
    overall: Literal["ok", "warning", "error"]
    components: list[DiagnosticComponent]
    recent_failures: list[FailedJob]


class ActionResult(BaseModel):
    message: str
