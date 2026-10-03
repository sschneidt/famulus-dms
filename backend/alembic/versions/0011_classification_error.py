"""KI-Ausfall bei der Einordnung merken

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-03

Nutzerwunsch: Dokumente, die nicht analysiert werden konnten (z. B. weil Ollama unter Windows erst
nach der Anmeldung laeuft), sollen gesammelt mit einem Knopf "Alle analysieren" nachgeholt werden.
Texterkennung und Angaben haben dafuer schon den Status "failed"; bei der Einordnung landete ein
KI-Ausfall bisher nur als Text im Verlauf. Jetzt steht er in documents.classification_error.

Bestand: Dokumente, deren letzte Einordnung an der KI scheiterte, bekommen den Vermerk nachtraeglich.
"""
import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("classification_error", sa.Text(), nullable=True))
    op.execute("""
        UPDATE documents d SET classification_error = left(e.note, 500)
        FROM (
            SELECT DISTINCT ON (document_id) document_id, note, new_category_id
            FROM classification_events
            ORDER BY document_id, created_at DESC, id DESC
        ) e
        WHERE e.document_id = d.id
          AND d.classification_status = 'needs_review'
          AND e.new_category_id IS NULL
          AND e.note ILIKE '%nicht verfuegbar%'
    """)


def downgrade() -> None:
    op.drop_column("documents", "classification_error")
