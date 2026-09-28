"""Hintergrund-Jobs der Klassifikation (Anforderungsdokument 4.3).

- classify_document: laeuft automatisch nach der Texterkennung (siehe tasks/ocr.py).
  Stufe 1 (Embedding-Vergleich mit Exemplaren) -> ggf. Stufe 2 (Sprachmodell) -> sonst
  Feedback-Loop (classification_status = needs_review). Jede Entscheidung wird als
  ClassificationEvent protokolliert; jede uebernommene Zuordnung wird sofort ein neues Exemplar,
  die Klassifikation lernt also mit jedem Dokument dazu.
- learn_exemplar: nach einer manuellen Zuordnung/Korrektur (POST /documents/{id}/category).
  Ersetzt die Exemplare dieses Dokuments durch eines in der richtigen Kategorie.

Die Entscheidungsregeln selbst stehen in homedms/ai/classifier.py.
"""
import logging
import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.ai.classifier import (
    CategoryScore,
    accept_llm,
    build_prompt,
    decide_stage1,
    parse_llm_answer,
    thresholds_for,
)
from homedms.ai import ollama
from homedms.ai.ollama import OllamaError
from homedms.config import get_settings
from homedms.jobs import app
from homedms.models.classification import AIModelConfig, CategoryExemplar, ClassificationEvent, ExemplarSource
from homedms.models.document import (
    Category,
    ClassificationStage,
    ClassificationStatus,
    Document,
)

logger = logging.getLogger("homedms.tasks.classification")


async def _config_for(db: AsyncSession, tenant_id: uuid.UUID) -> AIModelConfig | None:
    return await db.scalar(select(AIModelConfig).where(AIModelConfig.tenant_id == tenant_id))


async def _category_scores(
    db: AsyncSession, tenant_id: uuid.UUID, embedding: list[float], exclude_document_id: uuid.UUID
) -> list[CategoryScore]:
    """Beste Aehnlichkeit je Kategorie (1 - Kosinus-Abstand) plus Anzahl der Exemplare.
    Exemplare aus Dokumenten im Papierkorb zaehlen nicht mit."""
    distance = CategoryExemplar.embedding.cosine_distance(embedding)
    rows = (
        await db.execute(
            select(CategoryExemplar.category_id, func.max(1 - distance), func.count())
            .join(Category, Category.id == CategoryExemplar.category_id)
            .outerjoin(Document, Document.id == CategoryExemplar.document_id)
            .where(
                Category.tenant_id == tenant_id,
                or_(CategoryExemplar.document_id.is_(None), Document.deleted_at.is_(None)),
                or_(CategoryExemplar.document_id.is_(None), CategoryExemplar.document_id != exclude_document_id),
            )
            .group_by(CategoryExemplar.category_id)
        )
    ).all()
    return [CategoryScore(cat_id, float(sim), int(n)) for cat_id, sim, n in rows]


async def _replace_exemplar(
    db: AsyncSession, document: Document, category_id: uuid.UUID, embedding: list[float],
    source: ExemplarSource, user_id: uuid.UUID | None = None,
) -> None:
    """Ein Dokument steht fuer genau eine Kategorie - alte Exemplare (z. B. aus einer inzwischen
    korrigierten Zuordnung) werden ersetzt, damit die Korrektur nicht falsch weiterlernt."""
    await db.execute(delete(CategoryExemplar).where(CategoryExemplar.document_id == document.id))
    db.add(CategoryExemplar(
        category_id=category_id, document_id=document.id, embedding=embedding,
        created_via=source, confirmed_by_user_id=user_id,
    ))


def _record(db: AsyncSession, document: Document, *, new_category_id, stage: str, confidence, note: str) -> None:
    db.add(ClassificationEvent(
        document_id=document.id, previous_category_id=document.category_id, new_category_id=new_category_id,
        stage=stage, confidence=confidence, note=note[:1000],
    ))


@app.task(name="classify_document")
async def classify_document(document_id: str) -> None:
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        document = await db.get(Document, uuid.UUID(document_id))
        if document is None or document.deleted_at is not None:
            return
        if document.classification_status == ClassificationStatus.confirmed:
            return  # Nutzer hat schon entschieden - nie ueberschreiben

        config = await _config_for(db, document.tenant_id)
        t = thresholds_for(
            config.caution_level if config else get_settings().ai_caution_level,
            config.min_exemplars_fast_path if config else 5,
        )
        client = ollama.client_for(config)

        def needs_review(stage: str, note: str, confidence: float | None = None) -> None:
            _record(db, document, new_category_id=None, stage=stage, confidence=confidence, note=note)
            document.classification_status = ClassificationStatus.needs_review
            document.classification_stage = ClassificationStage(stage)
            document.classification_confidence = confidence

        text = (document.ocr_text or "").strip()
        if not text:
            needs_review("embedding", "Kein erkannter Text - bitte Kategorie manuell zuordnen.")
            await db.commit()
            return

        # --- Stufe 1: Embedding-Vergleich ---------------------------------------------------
        try:
            embedding = await client.embed(text)
        except OllamaError as exc:
            logger.warning("Embedding fehlgeschlagen fuer %s: %s", document_id, exc)
            needs_review("embedding", f"KI nicht verfuegbar: {exc}")
            await db.commit()
            return

        stage1 = decide_stage1(await _category_scores(db, document.tenant_id, embedding, document.id), t)
        if stage1.assigned:
            _record(db, document, new_category_id=stage1.category_id, stage="embedding",
                    confidence=stage1.similarity, note=stage1.reason)
            document.category_id = stage1.category_id
            document.classification_status = ClassificationStatus.auto_assigned
            document.classification_stage = ClassificationStage.embedding
            document.classification_confidence = stage1.similarity
            await _replace_exemplar(db, document, stage1.category_id, embedding, ExemplarSource.auto_high_confidence)
            await db.commit()
            return

        # --- Stufe 2: Sprachmodell ----------------------------------------------------------
        categories = (
            await db.execute(select(Category).where(Category.tenant_id == document.tenant_id).order_by(Category.name))
        ).scalars().all()
        system, user, schema = build_prompt([(c.name, c.description) for c in categories], text)
        try:
            raw = await client.chat_json(system, user, schema)
        except OllamaError as exc:
            logger.warning("Sprachmodell fehlgeschlagen fuer %s: %s", document_id, exc)
            needs_review("llm", f"Stufe 1: {stage1.reason}. Sprachmodell nicht verfuegbar: {exc}")
            await db.commit()
            return

        answer = parse_llm_answer(raw, {c.name: c.id for c in categories})
        if accept_llm(answer, t):
            _record(db, document, new_category_id=answer.category_id, stage="llm", confidence=answer.confidence,
                    note=f"Stufe 1: {stage1.reason}. Sprachmodell: {answer.reason}".strip())
            document.category_id = answer.category_id
            document.classification_status = ClassificationStatus.auto_assigned
            document.classification_stage = ClassificationStage.llm
            document.classification_confidence = answer.confidence
            await _replace_exemplar(db, document, answer.category_id, embedding, ExemplarSource.llm_confirmed)
        else:
            vorschlag = f"Vorschlag '{answer.category_name}'" if answer.category_name else "Keine passende Kategorie"
            needs_review(
                "llm",
                f"Stufe 1: {stage1.reason}. {vorschlag} mit {answer.confidence:.0%} Sicherheit - "
                f"unter der Schwelle von {t.llm_confidence:.0%}. {answer.reason}".strip(),
                confidence=answer.confidence,
            )
        await db.commit()


@app.task(name="learn_exemplar")
async def learn_exemplar(document_id: str, category_id: str, user_id: str | None = None) -> None:
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        document = await db.get(Document, uuid.UUID(document_id))
        if document is None or str(document.category_id) != category_id:
            return  # inzwischen geloescht oder erneut umkategorisiert - der neuere Job lernt
        text = (document.ocr_text or "").strip()
        if not text:
            return
        config = await _config_for(db, document.tenant_id)
        try:
            embedding = await ollama.client_for(config).embed(text)
        except OllamaError as exc:
            # Kein Datenverlust: die Zuordnung selbst ist gespeichert, nur das Lernbeispiel fehlt.
            logger.warning("Exemplar fuer %s nicht gelernt: %s", document_id, exc)
            return
        await _replace_exemplar(
            db, document, uuid.UUID(category_id), embedding, ExemplarSource.manual_feedback,
            uuid.UUID(user_id) if user_id else None,
        )
        await db.commit()
