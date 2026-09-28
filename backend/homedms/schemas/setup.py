"""Schema fuer POST /setup/bootstrap - Anforderungsdokument 4.7 (Einrichtungsassistent, erster Schritt)."""
from pydantic import BaseModel, EmailStr, Field

# Basis-Kategorien-Set, bestaetigt in Anforderungsdokument 4.3 - (Name, Beschreibung).
# Die Beschreibung bekommt das Sprachmodell bei der Klassifikation (Stufe 2) mit; klare
# Abgrenzungen (z. B. Strom -> Wohnen & Nebenkosten statt Rechnungen) verbessern die Treffer.
# Gleicher Stand wie in alembic/versions/0004 - dort fuer bestehende Installationen nachgetragen.
DEFAULT_CATEGORIES = [
    ("Rechnungen", "Rechnungen, Quittungen und Zahlungsaufforderungen, die in keinen spezielleren Bereich gehören, z. B. Handwerker, Online-Einkäufe, Telefon und Internet."),
    ("Vertraege", "Verträge und Vertragsänderungen, z. B. Mobilfunk, Strom- und Gasliefervertrag, Abonnements, Mitgliedschaften."),
    ("Versicherungen", "Versicherungsscheine, Beitragsrechnungen und Schreiben von Versicherungen (Haftpflicht, Hausrat, Kfz, Leben, Rente, Zusatzversicherungen)."),
    ("Bank & Finanzen", "Kontoauszüge, Kredit- und Darlehensunterlagen, Depot- und Sparverträge, Kreditkartenabrechnungen."),
    ("Steuern", "Steuerbescheide, Steuererklärungen, Lohnsteuerbescheinigungen und Schreiben des Finanzamts."),
    ("Gesundheit & Medizinisches", "Arztbriefe, Befunde, Rezepte, Arzt- und Apothekenrechnungen, Schreiben der Krankenkasse."),
    ("Behoerden & Amtliches", "Schreiben von Ämtern und Behörden, Urkunden, Meldebescheinigungen, Rundfunkbeitrag."),
    ("Wohnen & Nebenkosten", "Miet- oder Kaufunterlagen der Wohnung, Nebenkostenabrechnungen, Abrechnungen für Strom, Gas, Wasser, Müll und Grundsteuer."),
    ("Fahrzeug", "Fahrzeugpapiere, Werkstattrechnungen, TÜV-Berichte, Kfz-Steuer, Leasing- und Finanzierungsunterlagen zum Fahrzeug."),
    ("Arbeit & Gehalt", "Arbeitsvertrag, Gehaltsabrechnungen, Arbeitszeugnisse und Schreiben des Arbeitgebers."),
    ("Bildung", "Zeugnisse, Schul- und Studienunterlagen, Kurs- und Weiterbildungsnachweise."),
    ("Garantien & Kaufbelege", "Kassenbons, Kaufbelege und Garantiescheine für Geräte und größere Anschaffungen."),
    ("Sonstiges", "Dokumente, die eindeutig in keine der anderen Kategorien passen."),
]


class BootstrapRequest(BaseModel):
    household_name: str = Field(min_length=1, max_length=200)
    default_language: str = Field(default="de", max_length=10)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)
    admin_display_name: str = Field(min_length=1, max_length=200)


class BootstrapResponse(BaseModel):
    tenant_id: str
    admin_user_id: str
    categories_created: int
