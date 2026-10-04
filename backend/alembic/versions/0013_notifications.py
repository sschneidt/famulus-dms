"""Erinnerungen und Benachrichtigungen (Anforderungsdokument 4.5)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-04

Nutzerwunsch: taegliche Sammel-Erinnerung morgens - in der App (Glocke), per E-Mail und per Push
aufs Handy, mit Details.
- tenants.mail_settings: E-Mail-Versand des Haushalts (SMTP; Passwort verschluesselt)
- users.digest_hour / last_digest_on / last_digest_at: Uhrzeit der Zusammenfassung, zuletzt erstellt
- wiedervorlagen.reminder_stage / reminded_on: welche Erinnerungsstufe schon verschickt wurde
  (Vorlauf -> 1 Woche -> 1 Tag -> heute -> ueberfaellig, dann woechentlich)
- notifications: neue Arten "digest" und "test", Status "pending" (E-Mail/Push noch zu senden),
  sent_at und Fehlertext fuer Wiederholungsversuche
- push_subscriptions: Geraetename, letzte Nutzung, Fehler; Endpunkt eindeutig
- app_settings: serverweite Werte (Web-Push-Schluessel)
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("mail_settings", postgresql.JSONB(), nullable=True))

    op.add_column("users", sa.Column("digest_hour", sa.SmallInteger(), nullable=False, server_default="7"))
    op.add_column("users", sa.Column("last_digest_on", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True))
    # Bestand: Push war vorher nicht moeglich, In-App immer an
    op.execute("""
        UPDATE users SET notification_channels =
            jsonb_build_object('in_app', true,
                               'email', coalesce((notification_channels->>'email')::boolean, true),
                               'push', coalesce((notification_channels->>'push')::boolean, false))
    """)

    op.add_column("wiedervorlagen", sa.Column("reminder_stage", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column("wiedervorlagen", sa.Column("reminded_on", sa.Date(), nullable=True))

    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'digest'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'test'")
    op.execute("ALTER TYPE notification_status ADD VALUE IF NOT EXISTS 'pending'")
    op.add_column("notifications", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column("notifications", sa.Column("error", sa.Text(), nullable=True))
    op.create_index("ix_notifications_user_channel_status", "notifications", ["user_id", "channel", "status"])

    op.add_column("push_subscriptions", sa.Column("user_agent", sa.String(300), nullable=True))
    op.add_column("push_subscriptions", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("push_subscriptions", sa.Column("last_error", sa.Text(), nullable=True))
    op.create_index("ux_push_subscriptions_endpoint", "push_subscriptions", ["endpoint"], unique=True)

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    # Enum-Werte lassen sich in PostgreSQL nicht entfernen - sie stoeren aber auch nicht.
    op.drop_table("app_settings")
    op.drop_index("ux_push_subscriptions_endpoint", table_name="push_subscriptions")
    for column in ("last_error", "last_success_at", "user_agent"):
        op.drop_column("push_subscriptions", column)
    op.drop_index("ix_notifications_user_channel_status", table_name="notifications")
    for column in ("error", "attempts", "sent_at"):
        op.drop_column("notifications", column)
    for column in ("reminded_on", "reminder_stage"):
        op.drop_column("wiedervorlagen", column)
    for column in ("last_digest_at", "last_digest_on", "digest_hour"):
        op.drop_column("users", column)
    op.drop_column("tenants", "mail_settings")
