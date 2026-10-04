"""Tenant (Haushalt), User, RefreshToken. Siehe docs/Datenmodell.md 3.1, 3.2 und Abschnitt 4 (Auth)."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, SmallInteger, String, Text, func, true
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
    # E-Mail-Versand (0013, core/mailer.py): host, port, security, username, password (verschluesselt),
    # sender, app_url (fuer Links in der E-Mail). None = kein E-Mail-Versand eingerichtet.
    mail_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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
    # Taegliche Zusammenfassung (0013): ab dieser Stunde (Ortszeit, TZ) einmal pro Tag
    digest_hour: Mapped[int] = mapped_column(SmallInteger, default=7, server_default="7")
    last_digest_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Deaktiviert statt geloescht: Dokumente/Verlauf bleiben, Anmelden geht nicht mehr (0009)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Anmeldeschutz (0012): Fehlversuche in Folge, Sperre bis (waechst mit jedem Fehlversuch)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Zwei-Faktor (TOTP, 0012): Geheimnis der Authenticator-App; "pending" bis zur Bestaetigung
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_pending_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # gegen doppelt benutzte Codes
    recovery_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # Hashes, je einmal nutzbar

    @property
    def two_factor_enabled(self) -> bool:
        return bool(self.totp_secret)

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
    # Sitzung = eine Anmeldung auf einem Geraet; bei jeder Erneuerung entsteht ein neues Token mit
    # derselben session_id, das alte bekommt rotated_at (0012).
    session_id: Mapped[uuid.UUID] = mapped_column(index=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
