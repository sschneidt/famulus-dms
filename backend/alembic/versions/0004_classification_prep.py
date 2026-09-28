"""Vorbereitung Klassifikation: Exemplare an Dokumente koppeln, Kategorie-Beschreibungen

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28

1. category_exemplars.document_id: ON DELETE CASCADE + Index. Ein Exemplar ist aus dem Text
   eines Dokuments abgeleitet - wird das Dokument endgueltig geloescht (Papierkorb nach 30 Tagen),
   soll auch das Exemplar verschwinden, statt das Loeschen zu blockieren.
2. Beschreibungen fuer die 13 Basiskategorien nachtragen. Das Sprachmodell (Stufe 2) bekommt sie
   mit und grenzt Kategorien damit deutlich besser ab. Nur bei System-Kategorien mit
   unveraendertem Namen und noch leerer Beschreibung - eigene Anpassungen bleiben unberuehrt.
   Die Texte stehen hier als feste Kopie (nicht aus dem App-Code importiert), damit diese
   Migration auch nach spaeteren Aenderungen am Code immer dasselbe tut.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

DESCRIPTIONS = {
    "Rechnungen": "Rechnungen, Quittungen und Zahlungsaufforderungen, die in keinen spezielleren Bereich gehören, z. B. Handwerker, Online-Einkäufe, Telefon und Internet.",
    "Vertraege": "Verträge und Vertragsänderungen, z. B. Mobilfunk, Strom- und Gasliefervertrag, Abonnements, Mitgliedschaften.",
    "Versicherungen": "Versicherungsscheine, Beitragsrechnungen und Schreiben von Versicherungen (Haftpflicht, Hausrat, Kfz, Leben, Rente, Zusatzversicherungen).",
    "Bank & Finanzen": "Kontoauszüge, Kredit- und Darlehensunterlagen, Depot- und Sparverträge, Kreditkartenabrechnungen.",
    "Steuern": "Steuerbescheide, Steuererklärungen, Lohnsteuerbescheinigungen und Schreiben des Finanzamts.",
    "Gesundheit & Medizinisches": "Arztbriefe, Befunde, Rezepte, Arzt- und Apothekenrechnungen, Schreiben der Krankenkasse.",
    "Behoerden & Amtliches": "Schreiben von Ämtern und Behörden, Urkunden, Meldebescheinigungen, Rundfunkbeitrag.",
    "Wohnen & Nebenkosten": "Miet- oder Kaufunterlagen der Wohnung, Nebenkostenabrechnungen, Abrechnungen für Strom, Gas, Wasser, Müll und Grundsteuer.",
    "Fahrzeug": "Fahrzeugpapiere, Werkstattrechnungen, TÜV-Berichte, Kfz-Steuer, Leasing- und Finanzierungsunterlagen zum Fahrzeug.",
    "Arbeit & Gehalt": "Arbeitsvertrag, Gehaltsabrechnungen, Arbeitszeugnisse und Schreiben des Arbeitgebers.",
    "Bildung": "Zeugnisse, Schul- und Studienunterlagen, Kurs- und Weiterbildungsnachweise.",
    "Garantien & Kaufbelege": "Kassenbons, Kaufbelege und Garantiescheine für Geräte und größere Anschaffungen.",
    "Sonstiges": "Dokumente, die eindeutig in keine der anderen Kategorien passen.",
}


def upgrade() -> None:
    op.drop_constraint("category_exemplars_document_id_fkey", "category_exemplars", type_="foreignkey")
    op.create_foreign_key(
        "category_exemplars_document_id_fkey", "category_exemplars", "documents",
        ["document_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index(op.f("ix_category_exemplars_document_id"), "category_exemplars", ["document_id"])

    stmt = sa.text(
        "UPDATE categories SET description = :description "
        "WHERE is_system_default AND name = :name AND description = ''"
    )
    for name, description in DESCRIPTIONS.items():
        op.get_bind().execute(stmt, {"name": name, "description": description})


def downgrade() -> None:
    # Beschreibungen bleiben stehen (koennen inzwischen bearbeitet worden sein).
    op.drop_index(op.f("ix_category_exemplars_document_id"), table_name="category_exemplars")
    op.drop_constraint("category_exemplars_document_id_fkey", "category_exemplars", type_="foreignkey")
    op.create_foreign_key(
        "category_exemplars_document_id_fkey", "category_exemplars", "documents", ["document_id"], ["id"]
    )
