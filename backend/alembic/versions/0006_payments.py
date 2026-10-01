"""Zahlungsstatus fuer Rechnungen

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

documents.payment_status (offen | bezahlt | NULL), paid_on, paid_assumed - siehe homedms/core/payments.py.

Bestand: KI-Zahlungsfristen (vorgeschlagen/offen), die schon mehr als 3 Monate zurueckliegen,
gehoeren zu eingescannten, laengst bezahlten Rechnungen -> Termin erledigt, Dokument "bezahlt
(angenommen)". Dokumente mit juengeren offenen Zahlungsfristen gelten als "offen".
Regel und Stichworte als feste Kopie (unabhaengig vom spaeteren App-Code).
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PAYMENT = "(zahl|überweis|ueberweis|fällig|faellig|begleich)"


def upgrade() -> None:
    op.add_column("documents", sa.Column("payment_status", sa.String(20), nullable=True))
    op.add_column("documents", sa.Column("paid_on", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("paid_assumed", sa.Boolean(), nullable=False, server_default=sa.false()))
    bind = op.get_bind()
    old = (
        "w.source = 'ai_suggested' AND w.status IN ('vorgeschlagen', 'offen') "
        f"AND w.note ~* '{PAYMENT}' AND w.due_date < (CURRENT_DATE - INTERVAL '3 months')"
    )
    bind.execute(sa.text(
        "UPDATE documents d SET payment_status = 'bezahlt', paid_assumed = true "
        f"WHERE d.payment_status IS NULL AND EXISTS (SELECT 1 FROM wiedervorlagen w WHERE w.document_id = d.id AND {old})"
    ))
    bind.execute(sa.text(f"UPDATE wiedervorlagen w SET status = 'erledigt', completed_at = now() WHERE {old}"))
    bind.execute(sa.text(
        "UPDATE documents d SET payment_status = 'offen' WHERE d.payment_status IS NULL AND EXISTS ("
        "SELECT 1 FROM wiedervorlagen w WHERE w.document_id = d.id AND w.status IN ('vorgeschlagen', 'offen') "
        f"AND w.note ~* '{PAYMENT}')"
    ))


def downgrade() -> None:
    op.drop_column("documents", "paid_assumed")
    op.drop_column("documents", "paid_on")
    op.drop_column("documents", "payment_status")
