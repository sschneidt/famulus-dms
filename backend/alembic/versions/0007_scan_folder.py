"""Scan-Ordner: Dokumente des Haushalts, Import-Protokoll

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02

1. documents.owner_user_id darf leer sein = Dokument gehoert dem Haushalt (Nutzerwunsch: Scans aus
   dem Scan-Ordner gehoeren nicht dem Admin, sondern allen). Zugriff dann ueber die Kategorie-Regeln.
2. import_sources.recent: die letzten Import-Ergebnisse fuer die Anzeige in der App.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("documents", "owner_user_id", existing_type=sa.UUID(), nullable=True)
    op.add_column(
        "import_sources",
        sa.Column("recent", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("import_sources", "recent")
    # Haushalts-Dokumente bekommen beim Zurueckrollen den aeltesten Admin als Eigentuemer
    op.execute(
        "UPDATE documents d SET owner_user_id = (SELECT u.id FROM users u WHERE u.tenant_id = d.tenant_id "
        "AND u.role = 'admin' ORDER BY u.created_at LIMIT 1) WHERE d.owner_user_id IS NULL"
    )
    op.alter_column("documents", "owner_user_id", existing_type=sa.UUID(), nullable=False)
