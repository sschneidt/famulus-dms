"""Gemeinsame Response-Huellen - siehe docs/API-Design.md Abschnitt 1 (Konventionen)."""
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
