"""ImportSource, Notification, PushSubscription - Datenmodell 3.9 / 3.10."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from homedms.models.base import Base, UUIDPKMixin


class ImportSource(Base, UUIDPKMixin):
    __tablename__ = "import_sources"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(SAEnum("nas_watch_folder", "client_agent", name="import_source_type"))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # Pfad bzw. Agent-Token, Poll-Intervall
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Notification(Base, UUIDPKMixin):
    __tablename__ = "notifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(
        SAEnum(
            "new_document", "wiedervorlage_due", "wiedervorlage_vorschlag", "needs_review",
            name="notification_type",
        )
    )
    channel: Mapped[str] = mapped_column(SAEnum("in_app", "email", "push", name="notification_channel"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(
        SAEnum("unread", "read", "sent", "failed", name="notification_status"), default="unread"
    )
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class PushSubscription(Base, UUIDPKMixin):
    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000))
    keys: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
