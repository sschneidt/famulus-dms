"""Schemas fuer /auth/* - siehe docs/API-Design.md Abschnitt 2."""
import uuid

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    display_name: str
    role: str
    locale: str
    household_name: str = ""


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200, examples=["Max Mustermann"])


class HouseholdResponse(BaseModel):
    name: str
    documents_refiled: int = 0


class HouseholdUpdate(BaseModel):
    # Zugleich Name des Haushalts-Ordners in der Ablage - beim Umbenennen ziehen die Dateien um
    name: str = Field(min_length=1, max_length=200, examples=["Familie Mustermann"])
