"""Schemas fuer /auth/* - siehe docs/API-Design.md Abschnitt 2."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Antwort auf Anmeldung/Erneuerung. Die Weboberflaeche bekommt das Refresh-Token nur als
    HttpOnly-Cookie (refresh_token dann leer); andere Clients (z. B. Skripte) im Antworttext.
    Bei Zwei-Faktor-Konten liefert /auth/login zuerst nur two_factor_required + challenge."""

    access_token: str = ""
    refresh_token: str | None = None
    token_type: str = "bearer"
    two_factor_required: bool = False
    challenge: str | None = None  # fuer POST /auth/login/2fa, 5 Minuten gueltig
    notice: str | None = None  # z. B. "Noch 3 Wiederherstellungscodes uebrig"


class RefreshRequest(BaseModel):
    refresh_token: str | None = None  # leer = aus dem Cookie


class TwoFactorLogin(BaseModel):
    challenge: str
    code: str = Field(min_length=6, max_length=20, description="Code aus der App oder Wiederherstellungscode")


class SessionInfo(BaseModel):
    id: uuid.UUID
    device: str  # z. B. "Safari auf iPhone"
    ip: str | None = None
    started_at: datetime | None = None
    last_used_at: datetime | None = None
    current: bool = False


class PasswordConfirm(BaseModel):
    password: str


class TwoFactorStatus(BaseModel):
    enabled: bool
    recovery_codes_left: int = 0


class TwoFactorSetup(BaseModel):
    secret: str  # zum Abtippen, falls der QR-Code nicht geht
    uri: str
    qr_svg: str


class TwoFactorCode(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]


class MeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    display_name: str
    role: str
    locale: str
    household_name: str = ""
    two_factor_enabled: bool = False


MIN_PASSWORD_LENGTH = 8  # wie bei der Ersteinrichtung (schemas/setup.py)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200, examples=["Max Mustermann"])
    locale: Literal["de", "en", "ru"] | None = None  # Sprache der Oberflaeche, E-Mails und Push


class HouseholdResponse(BaseModel):
    name: str
    documents_refiled: int = 0


class HouseholdUpdate(BaseModel):
    # Zugleich Name des Haushalts-Ordners in der Ablage - beim Umbenennen ziehen die Dateien um
    name: str = Field(min_length=1, max_length=200, examples=["Familie Mustermann"])
