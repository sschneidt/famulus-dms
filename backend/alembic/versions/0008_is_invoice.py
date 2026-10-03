"""Rechnung ja/nein

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-03

Nutzerwunsch: Bei einem Kreditvertrag tauchte ein (falsch erkannter) Betrag samt "Bezahlt" auf.
Nur Rechnungen/Mahnungen/Zahlungsaufforderungen haben Betrag und Zahlungsstatus; der Nutzer kann
ein Dokument als "Keine Rechnung" (oder umgekehrt) markieren - das ueberschreibt die KI dauerhaft.

Bestand: Dokumente mit Betrag oder Zahlungsstatus gelten als Rechnung, alle anderen bleiben
"unbekannt" (werden beim naechsten "Erneut analysieren" eingeordnet).
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("is_invoice", sa.Boolean(), nullable=True))
    op.add_column("documents", sa.Column("is_invoice_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE documents SET is_invoice = true WHERE amount IS NOT NULL OR payment_status IS NOT NULL")


def downgrade() -> None:
    op.drop_column("documents", "is_invoice_locked")
    op.drop_column("documents", "is_invoice")
