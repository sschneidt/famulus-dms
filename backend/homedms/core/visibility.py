"""Sichtbarkeits-/Rechtemodell fuer Dokumente - siehe docs/Datenmodell.md 3.6 und
docs/Anforderungsdokument.md Abschnitt 3.

Regeln (in dieser Reihenfolge, siehe auch docs/API-Design.md Abschnitt 1
"Rechte-Durchsetzung"):
  1. Admin sieht/bearbeitet immer alles im eigenen Tenant.
  2. Eigentuemer (Document.owner_user_id) sieht/bearbeitet immer die eigenen Dokumente.
  3. Existiert eine DocumentAccessOverride fuer (Dokument, Nutzer), entscheidet die - als
     Einzelfall-Ausnahme unabhaengig von der Kategorie-Regel (kann grosszuegiger oder
     strenger sein als diese).
  4. Sonst: ist die Kategorie nicht `is_restricted`, ist das Dokument fuer alle
     Haushaltsmitglieder sichtbar/bearbeitbar.
  5. Ist die Kategorie `is_restricted`, entscheidet ein CategoryAccess-Eintrag fuer
     (Kategorie, Nutzer) - ohne Eintrag: kein Zugriff.

Als SQL-Ausdruck implementiert (nicht als Python-Funktion ueber bereits geladene Objekte),
damit Listen-Queries (`GET /documents`) die Filterung direkt in der Datenbank erledigen
statt jede Zeile einzeln in Python zu pruefen. Einzel-Dokument-Endpunkte (GET/PATCH/DELETE
by id) nutzen denselben Ausdruck ueber `is_document_visible`/`is_document_editable`, damit
es nur eine Quelle der Wahrheit fuer die Regeln gibt.
"""
import uuid

from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from homedms.models.document import Category, CategoryAccess, Document, DocumentAccessOverride
from homedms.models.tenant import User, UserRole


def _category_restricted_expr() -> ColumnElement:
    return (
        select(Category.is_restricted)
        .where(Category.id == Document.category_id)
        .correlate(Document)
        .scalar_subquery()
    )


def _category_access_expr(user: User, *, field) -> ColumnElement:
    return (
        select(field)
        .where(CategoryAccess.category_id == Document.category_id, CategoryAccess.user_id == user.id)
        .correlate(Document)
        .scalar_subquery()
    )


def _override_expr(user: User, *, field) -> ColumnElement:
    return (
        select(field)
        .where(DocumentAccessOverride.document_id == Document.id, DocumentAccessOverride.user_id == user.id)
        .correlate(Document)
        .scalar_subquery()
    )


def _access_expr(user: User, *, category_access_field, override_field) -> ColumnElement[bool]:
    if user.role == UserRole.admin:
        return true()

    category_restricted = _category_restricted_expr()
    category_access_ok = _category_access_expr(user, field=category_access_field)
    base_access = or_(
        Document.owner_user_id == user.id,
        category_restricted.isnot(True),
        category_access_ok.is_(True),
    )

    override = _override_expr(user, field=override_field)
    # Override entscheidet, wenn vorhanden (True oder False); ohne Override zaehlt base_access.
    return or_(override.is_(True), and_(override.is_(None), base_access))


def visible_documents_expr(user: User) -> ColumnElement[bool]:
    """Fuer WHERE-Klauseln in Listen-/Such-Queries (z. B. GET /documents)."""
    return _access_expr(
        user, category_access_field=CategoryAccess.can_view, override_field=DocumentAccessOverride.can_view
    )


def editable_documents_expr(user: User) -> ColumnElement[bool]:
    """Fuer WHERE-Klauseln bzw. Einzel-Checks bei schreibenden Endpunkten."""
    return _access_expr(
        user, category_access_field=CategoryAccess.can_edit, override_field=DocumentAccessOverride.can_edit
    )


async def is_document_visible(db: AsyncSession, user: User, document_id: uuid.UUID) -> bool | None:
    """None, wenn das Dokument im Tenant des Nutzers gar nicht existiert (-> 404 statt 403)."""
    exists_id = await db.scalar(
        select(Document.id).where(Document.id == document_id, Document.tenant_id == user.tenant_id)
    )
    if exists_id is None:
        return None
    visible = await db.scalar(
        select(visible_documents_expr(user)).where(Document.id == document_id)
    )
    return bool(visible)


async def is_document_editable(db: AsyncSession, user: User, document_id: uuid.UUID) -> bool | None:
    exists_id = await db.scalar(
        select(Document.id).where(Document.id == document_id, Document.tenant_id == user.tenant_id)
    )
    if exists_id is None:
        return None
    editable = await db.scalar(
        select(editable_documents_expr(user)).where(Document.id == document_id)
    )
    return bool(editable)
