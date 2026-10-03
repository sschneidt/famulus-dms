"""Schemas fuer /users - docs/API-Design.md Abschnitt 3 (Nutzer & Haushalt)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from homedms.schemas.auth import MIN_PASSWORD_LENGTH


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    two_factor_enabled: bool = False

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr = Field(examples=["anna@example.com"])
    display_name: str = Field(min_length=1, max_length=200, examples=["Anna"])
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200, description="Startpasswort")
    role: str = Field("member", pattern="^(admin|member)$")


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=200)
    role: str | None = Field(None, pattern="^(admin|member)$")
    is_active: bool | None = None
    reset_two_factor: bool | None = None  # Handy verloren: Zwei-Faktor des Mitglieds ausschalten


class PasswordReset(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
