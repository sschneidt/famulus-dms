"""Tenant (Haushalt), User, RefreshToken. Siehe docs/Datenmodell.md 3.1, 3.2 und Abschnitt 4 (Auth)."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from homedms.models.base import Base, TimestampMixin, UUIDPKMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class Tenant(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    default_language: Mapped[str] = mapped_column(String(10), default="de")

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.member)
    locale: Mapped[str] = mapped_column(String(10), default="de")
    # z.B. {"in_app": true, "email": true, "push": false} - siehe Anforderungsdokument 4.5
    notification_channels: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")

    __table_args__ = ({"comment": "email ist pro Tenant eindeutig - siehe Datenmodell 3.2"},)


class RefreshToken(Base, UUIDPKMixin):
    """Serverseitig widerrufbare Refresh-Tokens - siehe Datenmodell Abschnitt 4 (Auth-Umsetzung: JWT)."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
