"""Category, Tag, Document, DocumentFile + Rechte-Modell. Siehe docs/Datenmodell.md 3.3-3.6."""
import enum
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Numeric, String, Text, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from homedms.models.base import Base, TimestampMixin, UUIDPKMixin


class ClassificationStatus(str, enum.Enum):
    pending = "pending"
    auto_assigned = "auto_assigned"
    needs_review = "needs_review"
    confirmed = "confirmed"


class ClassificationStage(str, enum.Enum):
    embedding = "embedding"
    llm = "llm"
    manual = "manual"
    chat = "chat"


class ExtractionStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class OcrStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class DocumentSource(str, enum.Enum):
    photo_app = "photo_app"
    upload = "upload"
    nas_scan_folder = "nas_scan_folder"
    client_agent = "client_agent"
    email = "email"


class OriginalPresent(str, enum.Enum):
    ja = "ja"
    nein = "nein"
    unbekannt = "unbekannt"


class Category(Base, UUIDPKMixin, TimestampMixin):
    """Pro Tenant eigenstaendig, aus dem Basis-Set vorbefuellt (Anforderungsdokument 4.3)."""

    __tablename__ = "categories"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # Unterordner pro Objekt-Adresse: none | all | buildings (nur Gebaeude-/Hausrat-Versicherungen),
    # siehe homedms/core/addresses.py
    property_mode: Mapped[str] = mapped_column(String(20), default="none", server_default="none")


class CategoryAccess(Base, UUIDPKMixin):
    """Sichtbarkeits-Allowlist fuer is_restricted=true Kategorien (Datenmodell 3.6)."""

    __tablename__ = "category_access"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("category_id", "user_id", name="uq_category_access_user"),)


class Tag(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tags"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tag_tenant_name"),)


class Property(Base, UUIDPKMixin, TimestampMixin):
    """Ein Objekt (Haus/Wohnung) des Haushalts - automatisch angelegt, sobald die KI eine neue
    Adresse erkennt. Der Name ist zugleich der Ordnername in der Ablage."""

    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("tenant_id", "match_key", name="uq_property_tenant_key"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    street: Mapped[str] = mapped_column(String(200))
    postal_code: Mapped[str] = mapped_column(String(10))
    city: Mapped[str] = mapped_column(String(100))
    match_key: Mapped[str] = mapped_column(String(300))  # normalisiert, siehe core/addresses.py


class Document(Base, UUIDPKMixin, TimestampMixin):
    """Das zentrale Objekt - siehe Datenmodell 3.5."""

    __tablename__ = "documents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    # None = gehoert dem ganzen Haushalt (z. B. aus dem Scan-Ordner) - Zugriff dann nur ueber die
    # Kategorie-Regeln (core/visibility.py), keine einzelne Person ist Eigentuemer.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(300), default="")
    # True = Titel hat der Nutzer selbst vergeben -> nie automatisch ueberschreiben (Migration 0005)
    title_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Kurzer Betreff, von der KI erkannt oder vom Nutzer gesetzt - Grundlage fuer Titel und Dateiname
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    ocr_language: Mapped[str] = mapped_column(String(10), default="")
    ocr_status: Mapped[OcrStatus] = mapped_column(
        SAEnum(OcrStatus, name="ocr_status"), default=OcrStatus.pending
    )

    classification_status: Mapped[ClassificationStatus] = mapped_column(
        SAEnum(ClassificationStatus, name="classification_status"),
        default=ClassificationStatus.pending,
    )
    classification_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    classification_stage: Mapped[ClassificationStage | None] = mapped_column(
        SAEnum(ClassificationStage, name="classification_stage"), nullable=True
    )
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(ExtractionStatus, name="extraction_status"),
        default=ExtractionStatus.pending,
    )

    source: Mapped[DocumentSource] = mapped_column(
        SAEnum(DocumentSource, name="document_source")
    )

    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)

    original_present: Mapped[OriginalPresent] = mapped_column(
        SAEnum(OriginalPresent, name="original_present"),
        default=OriginalPresent.unbekannt,
    )
    original_location: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Rechnung ja/nein (KI: Dokumenttyp; Nutzer: "Keine Rechnung"). None = unbekannt (aeltere Dokumente)
    is_invoice: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_invoice_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Zahlung (core/payments.py): None = keine Rechnung/unbekannt, "offen", "bezahlt"
    payment_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # True = nicht vom Nutzer bestaetigt, sondern angenommen (Frist lag beim Einlesen > 3 Monate zurueck)
    paid_assumed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # Soft-Delete, Datenmodell 3.5

    # lazy="selectin": im async-Kontext bequemer als lazy-loading (das ausserhalb eines awaited
    # Kontexts einen MissingGreenlet-Fehler wirft) - bei unserem Volumen (< 50 Dok./Monat) unkritisch.
    files: Mapped[list["DocumentFile"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentFile.page_number",
        lazy="selectin",
    )


class DocumentFile(Base, UUIDPKMixin):
    """Physische Seite/Datei eines Dokuments - trennt logisches Dokument von Dateien (Mehrseiten-Scan)."""

    __tablename__ = "document_files"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(1000))
    page_number: Mapped[int] = mapped_column(default=1)
    mime_type: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(128), default="")

    document: Mapped["Document"] = relationship(back_populates="files")

    @property
    def filename(self) -> str:
        """Reiner Dateiname fuer die API-Antwort, ohne den vollen Speicherpfad preiszugeben."""
        return Path(self.file_path).name

    @property
    def path(self) -> str:
        from homedms.core.filing import relative_to_root

        return relative_to_root(self.file_path)


class DocumentTag(Base):
    """n:m Dokument <-> Tag."""

    __tablename__ = "document_tags"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class DocumentAccessOverride(Base, UUIDPKMixin):
    """Einzelfall-Ausnahmen zur Kategorie-Sichtbarkeit (Datenmodell 3.6)."""

    __tablename__ = "document_access_overrides"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("document_id", "user_id", name="uq_doc_access_user"),)
