"""Automatische Benennung, Ablage nach Kategorie/Jahr, Kategorie "Haus & Reparaturen"

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30

1. documents.subject: kurzer Betreff, den die KI erkennt (z. B. "Rechnung Wasserschaden-Reparatur").
   Daraus entstehen Titel ("Betreff – Absender") und Dateiname ("JJJJ-MM-TT Absender – Betreff").
2. documents.title_locked: Titel wurde vom Nutzer selbst vergeben -> nie automatisch ueberschreiben.
   Bestehende Dokumente: Titel, die wie ein Upload-Dateiname aussehen ("ScannedDocument1.pdf"),
   gelten als nicht gesetzt; alle anderen hat jemand bewusst vergeben.
3. Neue Basiskategorie "Haus & Reparaturen" (Nutzerwunsch: Handwerker-Rechnung zum Wasserschaden
   landete unter "Fahrzeug") fuer jeden bestehenden Haushalt, sofern es sie dort noch nicht gibt.
   Die Beschreibungen von "Rechnungen" und "Fahrzeug" werden geschaerft - aber nur, wenn sie noch
   dem bisherigen Standardtext entsprechen (eigene Anpassungen bleiben unberuehrt).
   Texte als feste Kopie, damit die Migration unabhaengig vom spaeteren App-Code gleich bleibt.

4. Objekte (properties): Adressen von Haus/Wohnung. Dokumente der Kategorien "Haus & Reparaturen"
   und "Wohnen & Nebenkosten" sowie Gebaeude-/Hausrat-Versicherungen bekommen einen Unterordner
   "<Ort> <Strasse Nr>" (categories.property_mode: none | all | buildings).

Die Dateien selbst verschiebt diese Migration NICHT (Migrationen laufen auch ohne Zugriff auf den
Dokumente-Ordner). Das erledigt der Worker bzw. "python -m homedms.cli refile".
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

NEW_CATEGORY = (
    "Haus & Reparaturen",
    "Handwerker- und Reparaturrechnungen, Schäden (z. B. Wasserschaden), Wartung, Renovierung und "
    "Modernisierung an Haus oder Wohnung, z. B. Sanitär, Heizung, Elektro, Dach, Fenster.",
)

UPDATED_DESCRIPTIONS = {
    "Rechnungen": (
        "Rechnungen, Quittungen und Zahlungsaufforderungen, die in keinen spezielleren Bereich gehören, z. B. Handwerker, Online-Einkäufe, Telefon und Internet.",
        "Rechnungen, Quittungen und Zahlungsaufforderungen, die in keinen spezielleren Bereich gehören, z. B. Online-Einkäufe, Telefon und Internet.",
    ),
    "Fahrzeug": (
        "Fahrzeugpapiere, Werkstattrechnungen, TÜV-Berichte, Kfz-Steuer, Leasing- und Finanzierungsunterlagen zum Fahrzeug.",
        "Nur Unterlagen zu einem Kraftfahrzeug (Auto, Motorrad, Wohnmobil): Fahrzeugpapiere, Rechnungen von Kfz-Werkstätten, TÜV-Berichte, Kfz-Steuer, Leasing und Finanzierung. Erkennbar an Kennzeichen, Fahrgestellnummer oder Kilometerstand.",
    ),
}


PROPERTY_MODES = {"Haus & Reparaturen": "all", "Wohnen & Nebenkosten": "all", "Versicherungen": "buildings"}


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("street", sa.String(200), nullable=False),
        sa.Column("postal_code", sa.String(10), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("match_key", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "match_key", name="uq_property_tenant_key"),
    )
    op.create_index(op.f("ix_properties_tenant_id"), "properties", ["tenant_id"])
    op.add_column("documents", sa.Column("property_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "documents_property_id_fkey", "documents", "properties", ["property_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(op.f("ix_documents_property_id"), "documents", ["property_id"])
    op.add_column(
        "categories", sa.Column("property_mode", sa.String(20), nullable=False, server_default="none")
    )
    op.add_column("documents", sa.Column("subject", sa.String(300), nullable=True))
    op.add_column(
        "documents", sa.Column("title_locked", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE documents SET title_locked = true "
        "WHERE title <> '' AND title !~ '\\.[A-Za-z0-9]{1,5}$'"
    ))

    name, description = NEW_CATEGORY
    bind.execute(
        sa.text(
            "INSERT INTO categories (id, tenant_id, name, description, is_restricted, is_system_default, "
            "created_at, updated_at) "
            "SELECT gen_random_uuid(), t.id, CAST(:name AS varchar), CAST(:description AS text), false, true, now(), now() "
            "FROM tenants t WHERE NOT EXISTS "
            "(SELECT 1 FROM categories c WHERE c.tenant_id = t.id AND lower(c.name) = lower(CAST(:name AS varchar)))"
        ),
        {"name": name, "description": description},
    )
    for cat, mode in PROPERTY_MODES.items():
        bind.execute(
            sa.text("UPDATE categories SET property_mode = :mode WHERE is_system_default AND name = :name"),
            {"name": cat, "mode": mode},
        )
    for cat, (old, new) in UPDATED_DESCRIPTIONS.items():
        bind.execute(
            sa.text("UPDATE categories SET description = :new WHERE is_system_default AND name = :name AND description = :old"),
            {"name": cat, "old": old, "new": new},
        )


def downgrade() -> None:
    # Kategorie und Beschreibungen bleiben (koennen inzwischen Dokumente enthalten).
    op.drop_column("categories", "property_mode")
    op.drop_index(op.f("ix_documents_property_id"), table_name="documents")
    op.drop_constraint("documents_property_id_fkey", "documents", type_="foreignkey")
    op.drop_column("documents", "property_id")
    op.drop_index(op.f("ix_properties_tenant_id"), table_name="properties")
    op.drop_table("properties")
    op.drop_column("documents", "title_locked")
    op.drop_column("documents", "subject")
