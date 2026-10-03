"""Sicherheit: Anmeldeschutz, Sitzungen/Geraete, Zwei-Faktor

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-03

Nutzerwunsch: "Da es sich um sensible Dokumente handelt, ist die Sicherheit enorm wichtig."
- users.failed_logins / locked_until: Sperrzeit nach mehreren Fehlversuchen (waechst)
- users.totp_*: Zwei-Faktor-Anmeldung per Authenticator-App, Wiederherstellungscodes (gehasht)
- refresh_tokens.session_id: alle Tokens einer Anmeldung (Rotation) bilden eine Sitzung = ein
  Geraet in "Angemeldete Geraete"; rotated_at erkennt wiederverwendete (gestohlene) Tokens;
  user_agent/ip/last_used_at fuer die Anzeige.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("totp_pending_secret", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("recovery_codes", postgresql.JSONB(), nullable=True))

    op.add_column("refresh_tokens", sa.Column("session_id", sa.UUID(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("user_agent", sa.String(300), nullable=True))
    op.add_column("refresh_tokens", sa.Column("ip", sa.String(64), nullable=True))
    # Bestand: jede bisherige Anmeldung ist eine eigene Sitzung
    op.execute("UPDATE refresh_tokens SET session_id = id, session_started_at = created_at, last_used_at = created_at")
    op.alter_column("refresh_tokens", "session_id", nullable=False)
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens")
    for column in ("ip", "user_agent", "session_started_at", "last_used_at", "rotated_at", "session_id"):
        op.drop_column("refresh_tokens", column)
    for column in ("recovery_codes", "totp_last_step", "totp_pending_secret", "totp_secret", "locked_until", "failed_logins"):
        op.drop_column("users", column)
