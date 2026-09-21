"""Wiedervorlage (generisches Termin-Feature) + RetentionRule - Datenmodell 3.8 / Anforderungsdokument 4.4a."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from homedms.models.base import Base, TimestampMixin, UUIDPKMixin


class Wiedervorlage(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "wiedervorlagen"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)

    due_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(SAEnum("retention", "custom", name="wiedervorlage_type"))
    source: Mapped[str] = mapped_column(
        SAEnum("manual", "ai_suggested", "retention_rule", name="wiedervorlage_source")
    )
    status: Mapped[str] = mapped_column(
        SAEnum("vorgeschlagen", "offen", "erledigt", "verworfen", name="wiedervorlage_status"),
        default="offen",
    )
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    recurrence: Mapped[str] = mapped_column(
        SAEnum("none", "monthly", "yearly", "custom_months", name="wiedervorlage_recurrence"),
        default="none",
    )
    recurrence_interval_months: Mapped[int | None] = mapped_column(nullable=True)

    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reminder_lead_days: Mapped[int] = mapped_column(default=30)

    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class RetentionRule(Base, UUIDPKMixin):
    __tablename__ = "retention_rules"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    retention_period_months: Mapped[int | None] = mapped_column(nullable=True)
    requires_original: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_before_days: Mapped[int] = mapped_column(default=30)
