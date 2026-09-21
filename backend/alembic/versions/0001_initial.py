"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-21

Hinweis zum Vorgehen: Diese erste Migration erzeugt das Schema direkt aus den SQLAlchemy-
Modellen (Base.metadata.create_all), statt jede Tabelle einzeln per op.create_table
nachzubilden. Das ist fuer eine Bootstrap-Migration pragmatisch und garantiert Konsistenz
mit den Modellen (kein Abschreibfehler moeglich); ab hier laufen weitere Schema-Aenderungen
ueber normale `alembic revision --autogenerate` gegen eine laufende Dev-Datenbank.
"""
import sqlalchemy as sa
from alembic import op

from homedms.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
