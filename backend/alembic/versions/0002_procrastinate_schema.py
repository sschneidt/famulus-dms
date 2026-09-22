"""procrastinate job-queue schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

Legt die Tabellen/Funktionen der PostgreSQL-Job-Queue Procrastinate an (docs/Docker-Compose-
Entwurf.md Abschnitt 2). Ohne sie scheitert jedes Einreihen eines Jobs (z. B. OCR nach dem
Upload) und der Worker kann nicht starten.

Das SQL liegt als feste Kopie daneben (sql/procrastinate_3.9.0_schema.sql), statt zur Laufzeit
aus dem installierten Paket gelesen zu werden: So erzeugt diese Migration auf jeder Installation
exakt dasselbe Schema, auch nach einem spaeteren Procrastinate-Update. Deshalb ist Procrastinate
in pyproject.toml auf 3.9.x festgelegt. **Beim Anheben der Version** muss eine neue Alembic-
Migration die passenden Delta-Skripte aus procrastinate/sql/migrations/ anwenden.
"""
from pathlib import Path

from alembic import op
from sqlalchemy.util import await_only

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCHEMA_FILE = Path(__file__).parent / "sql" / "procrastinate_3.9.0_schema.sql"


def _execute_script(sql: str) -> None:
    """Das Skript enthaelt viele Anweisungen inkl. PL/pgSQL-Funktionen ($$ ... ; ... $$).
    Ueber SQLAlchemy/asyncpg laufen Anweisungen als Prepared Statement, das nur EINE Anweisung
    erlaubt - daher direkt ueber die asyncpg-Verbindung (einfaches Query-Protokoll), weiterhin
    innerhalb der Alembic-Transaktion."""
    driver_connection = op.get_bind().connection.driver_connection
    await_only(driver_connection.execute(sql))


def upgrade() -> None:
    _execute_script(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    _execute_script(
        """
        DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers,
            procrastinate_jobs, procrastinate_workers CASCADE;
        DROP TYPE IF EXISTS procrastinate_job_status, procrastinate_job_event_type,
            procrastinate_job_to_defer_v1 CASCADE;
        """
    )
