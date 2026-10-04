"""ImportSource, Notification, PushSubscription, AppSetting - Datenmodell 3.9 / 3.10."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, SmallInteger, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from homedms.models.base import Base, UUIDPKMixin


class ImportSource(Base, UUIDPKMixin):
    __tablename__ = "import_sources"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(SAEnum("nas_watch_folder", "client_agent", name="import_source_type"))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # Pfad bzw. Agent-Token, Poll-Intervall
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Die letzten Import-Ergebnisse (fuer die Anzeige in der App): [{at, file, status, message, document_id}]
    recent: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")


class Notification(Base, UUIDPKMixin):
    __tablename__ = "notifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(
        SAEnum(
            "new_document", "wiedervorlage_due", "wiedervorlage_vorschlag", "needs_review", "digest", "test",
            name="notification_type",
        )
    )
    channel: Mapped[str] = mapped_column(SAEnum("in_app", "email", "push", name="notification_channel"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(
        SAEnum("unread", "read", "sent", "failed", "pending", name="notification_status"), default="unread"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # E-Mail/Push (0013): "pending" bis verschickt; bei Fehlern mehrere Versuche (core/notifications.py)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class PushSubscription(Base, UUIDPKMixin):
    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000))
    keys: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)  # Geraetename (0013)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppSetting(Base):
    """Serverweite Werte, die mit der Datenbank gesichert werden sollen (z. B. Web-Push-Schluessel:
    geht er verloren, muesste jedes Geraet Push neu einschalten)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
