"""Zeitstempel einheitlich mit Zeitzone, created_at-Standardwerte reparieren

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22

Behebt zwei Maengel aus dem Anfangsschema (gefunden durch tests/integration):

1. Einige Zeitstempel-Spalten waren "timestamp without time zone", der Code schreibt aber
   zeitzonenbehaftete Werte (datetime.now(timezone.utc)). Das liess z. B. das Loeschen in den
   Papierkorb (documents.deleted_at) mit einem Datenbankfehler scheitern. Alle betroffenen
   Spalten werden auf "timestamp with time zone" umgestellt; vorhandene Werte werden dabei in
   der Zeitzone der Datenbank interpretiert - also genau so, wie sie entstanden sind.

2. Bei sechs Tabellen war der Standardwert von created_at der *Text* 'now()' statt des
   Funktionsaufrufs now(). Postgres wertet einen solchen Text einmalig beim Anlegen der Tabelle
   aus, sodass jede neue Zeile denselben festen Zeitpunkt erhalten haette. Bereits vorhandene
   Zeilen behalten ihren (ungenauen) Wert, neue Zeilen bekommen ab jetzt den echten Zeitpunkt.
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NAIVE_COLUMNS = [
    ("category_exemplars", "created_at"),
    ("chat_messages", "created_at"),
    ("classification_events", "created_at"),
    ("notifications", "created_at"),
    ("push_subscriptions", "created_at"),
    ("documents", "deleted_at"),
    ("import_sources", "last_scanned_at"),
    ("wiedervorlagen", "completed_at"),
]

BROKEN_DEFAULT_TABLES = [
    "category_exemplars",
    "chat_messages",
    "classification_events",
    "notifications",
    "push_subscriptions",
    "refresh_tokens",
]


def upgrade() -> None:
    for table, column in NAIVE_COLUMNS:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE timestamp with time zone')
    for table in BROKEN_DEFAULT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "created_at" SET DEFAULT now()')


def downgrade() -> None:
    # Die fehlerhaften Text-Standardwerte werden bewusst NICHT wiederhergestellt.
    for table, column in NAIVE_COLUMNS:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE timestamp without time zone')
