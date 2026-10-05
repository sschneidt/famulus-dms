"""Mehrsprachigkeit: Sprachen der Texterkennung je Haushalt

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-05

Nutzerwunsch: Oberflaeche auch auf Englisch und Russisch; die Texterkennung richtet sich nach den
Sprachen der Oberflaeche, weitere Sprachpakete lassen sich nachinstallieren.
- tenants.ocr_languages: vom Admin gewaehlte Sprachen (Tesseract-Codes), None = OCR_LANGUAGES
- documents.ocr_language: Platz fuer mehrere Sprachen ("deu+eng+rus")
- users.locale: nur noch de/en/ru (Unbekanntes -> de)
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("ocr_languages", postgresql.JSONB(), nullable=True))
    op.alter_column("documents", "ocr_language", type_=sa.String(100), existing_type=sa.String(10))
    op.execute("UPDATE users SET locale = 'de' WHERE locale NOT IN ('de', 'en', 'ru')")


def downgrade() -> None:
    op.execute("UPDATE documents SET ocr_language = left(ocr_language, 10)")
    op.alter_column("documents", "ocr_language", type_=sa.String(10), existing_type=sa.String(100))
    op.drop_column("tenants", "ocr_languages")
