"""Exemplare ohne pgvector

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-03

Nutzerwunsch: HomeDMS soll auch ohne NAS/Docker direkt auf einem Windows-PC oder Linux-Server
laufen. Die PostgreSQL-Erweiterung pgvector gibt es fuer Windows nicht als fertiges Paket -
deshalb speichern die Kategorie-Exemplare ihren Vektor jetzt als normale Zahlenliste
(double precision[]) und die Aehnlichkeit rechnet der Worker selbst (tasks/classification.py).
Bei einem Haushalt (einige tausend Exemplare) dauert das Bruchteile einer Sekunde.

Bestehende Installationen: Die vector-Spalte wird verlustfrei umgewandelt. Die Erweiterung selbst
bleibt installiert (schadet nicht, das Docker-Image bringt sie mit).
"""
import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _column_type() -> str:
    return op.get_bind().scalar(sa.text(
        "SELECT udt_name FROM information_schema.columns "
        "WHERE table_name = 'category_exemplars' AND column_name = 'embedding'"
    ))


def upgrade() -> None:
    if _column_type() == "vector":
        op.execute(
            "ALTER TABLE category_exemplars ALTER COLUMN embedding "
            "TYPE double precision[] USING embedding::real[]::double precision[]"
        )


def downgrade() -> None:
    # Bewusst nichts zuruecks - aeltere Versionen lesen die Zahlenliste nicht, setzen aber pgvector
    # voraus; ein Zurueckwandeln waere nur mit installierter Erweiterung moeglich:
    #   ALTER TABLE category_exemplars ALTER COLUMN embedding TYPE vector(768) USING embedding::vector
    pass
