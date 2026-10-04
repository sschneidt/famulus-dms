"""Benachrichtigungen - docs/API-Design.md Abschnitt 9."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class NotificationItem(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    url: str
    read: bool
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationItem]
    unread: int


class PushDevice(BaseModel):
    id: uuid.UUID
    name: str
    endpoint: str
    created_at: datetime
    last_success_at: datetime | None = None
    last_error: str | None = None


class NotificationSettings(BaseModel):
    email: bool
    push: bool
    digest_hour: int
    email_address: str
    email_available: bool  # hat der Admin den E-Mail-Versand eingerichtet?
    push_public_key: str   # applicationServerKey fuer pushManager.subscribe()
    push_devices: list[PushDevice]
    timezone: str


class NotificationSettingsUpdate(BaseModel):
    email: bool | None = None
    push: bool | None = None
    digest_hour: int | None = Field(default=None, ge=0, le=23)


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=80, max_length=120)
    auth: str = Field(min_length=16, max_length=40)


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: PushKeys


class TestRequest(BaseModel):
    channel: Literal["email", "push"]


class TestResult(BaseModel):
    ok: bool
    message: str


class MailSettings(BaseModel):
    configured: bool
    host: str = ""
    port: int = 587
    security: Literal["starttls", "ssl", "none"] = "starttls"
    username: str = ""
    password_set: bool = False
    sender: str = ""
    app_url: str = ""
    last_ok_at: str | None = None
    last_error: str | None = None


class MailSettingsUpdate(BaseModel):
    host: str = Field(min_length=1, max_length=200)
    port: int = Field(ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"]
    username: str = Field(default="", max_length=200)
    # None = gespeichertes Passwort behalten, "" = entfernen
    password: str | None = Field(default=None, max_length=500)
    sender: EmailStr
    app_url: str = Field(default="", max_length=300)
