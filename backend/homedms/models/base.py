"""Gemeinsame Basis fuer alle Modelle: UUID-PK + Timestamps (Datenmodell 1: "Alle IDs sind UUIDs")."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    # Die Zeitstempel setzt die Datenbank selbst. eager_defaults=True holt sie per RETURNING
    # direkt beim INSERT *und* UPDATE zurueck - sonst waere updated_at nach einem UPDATE
    # "abgelaufen" und wuerde beim Serialisieren der Antwort nachgeladen, was im async-Kontext
    # mit MissingGreenlet scheitert (gefunden durch tests/integration).
    __mapper_args__ = {"eager_defaults": True}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantScopedMixin:
    """Markiert Modelle, die tenant_id tragen - siehe Datenmodell 1 (RLS-Empfehlung).
    Die eigentliche tenant_id-Spalte wird pro Modell deklariert (Fremdschluessel-Ziel variiert nicht,
    aber der Mixin dokumentiert die Konvention und dient als Marker fuer zukuenftige RLS-Tooling)."""
    pass
