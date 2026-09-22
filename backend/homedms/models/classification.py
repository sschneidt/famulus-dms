"""CategoryExemplar (pgvector), ClassificationEvent, AIModelConfig - Datenmodell 3.7."""
import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Numeric, String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from homedms.models.base import Base, UUIDPKMixin

# Dimension haengt vom gewaehlten Embedding-Modell ab (offener Punkt, Anforderungsdokument 7).
# nomic-embed-text (Default in .env.example) liefert 768-dimensionale Vektoren.
EMBEDDING_DIM = 768


class ExemplarSource(str, enum.Enum):
    auto_high_confidence = "auto_high_confidence"
    llm_confirmed = "llm_confirmed"
    manual_feedback = "manual_feedback"
    chat_correction = "chat_correction"


class CategoryExemplar(Base, UUIDPKMixin):
    __tablename__ = "category_exemplars"

    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_via: Mapped[ExemplarSource] = mapped_column(SAEnum(ExemplarSource, name="exemplar_source"))
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClassificationEvent(Base, UUIDPKMixin):
    """Audit-Trail jeder (Um-)Kategorisierung - Grundlage fuer Feedback-Loop + Chat-Aenderungen."""

    __tablename__ = "classification_events"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    previous_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    new_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    stage: Mapped[str] = mapped_column(SAEnum(
        "embedding", "llm", "manual", "chat", name="classification_event_stage"
    ))
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIModelConfig(Base, UUIDPKMixin):
    """Ein Datensatz pro Tenant - Anforderungsdokument 4.3 ("einfacher Regler" caution_level)."""

    __tablename__ = "ai_model_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(SAEnum("ollama_local", "external_api", name="ai_provider"))
    chat_model_name: Mapped[str] = mapped_column(String(200), default="llama3.2:3b")
    embedding_model_name: Mapped[str] = mapped_column(String(200), default="nomic-embed-text")
    external_api_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    caution_level: Mapped[str] = mapped_column(
        SAEnum("vorsichtig", "normal", "mutig", name="ai_caution_level"), default="normal"
    )
    min_exemplars_fast_path: Mapped[int] = mapped_column(default=5)
