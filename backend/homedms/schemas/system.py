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


class UpdateStatus(BaseModel):
    current: str  # installierte Version
    latest: str  # neueste veroeffentlichte Version
    available: bool  # latest ist neuer als current
    url: str  # Release-Seite mit den Aenderungen
    published_at: datetime | None = None
    checked_at: datetime


class BackupItem(BaseModel):
    name: str
    size: int  # Bytes
    created: datetime


class BackupsResponse(BaseModel):
    available: bool  # false: pg_dump fehlt, Sicherungen aus der Anwendung sind hier nicht moeglich
    folder: str  # wo die Dateien liegen (fuer Anzeige)
    keep: int  # so viele Sicherungen bleiben erhalten
    items: list[BackupItem]
