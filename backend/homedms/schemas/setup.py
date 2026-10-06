"""Schema fuer POST /setup/bootstrap - Anforderungsdokument 4.7 (Einrichtungsassistent, erster Schritt)."""
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from homedms.i18n import N_

# Basis-Kategorien-Set, bestaetigt in Anforderungsdokument 4.3 - (Name, Beschreibung).
# Die Beschreibung bekommt das Sprachmodell bei der Klassifikation (Stufe 2) mit; klare
# Abgrenzungen (z. B. Strom -> Wohnen & Nebenkosten statt Rechnungen) verbessern die Treffer.
# Gleicher Stand wie in alembic/versions/0004 und 0005 - dort fuer bestehende Installationen nachgetragen.
DEFAULT_CATEGORIES = [
    (N_("Rechnungen"), "Rechnungen, Quittungen und Zahlungsaufforderungen, die in keinen spezielleren Bereich gehören, z. B. Online-Einkäufe, Telefon und Internet."),
    (N_("Vertraege"), "Verträge und Vertragsänderungen, z. B. Mobilfunk, Strom- und Gasliefervertrag, Abonnements, Mitgliedschaften."),
    (N_("Versicherungen"), "Versicherungsscheine, Beitragsrechnungen und Schreiben von Versicherungen (Haftpflicht, Hausrat, Kfz, Leben, Rente, Zusatzversicherungen)."),
    (N_("Bank & Finanzen"), "Kontoauszüge, Kredit- und Darlehensunterlagen, Depot- und Sparverträge, Kreditkartenabrechnungen."),
    (N_("Steuern"), "Steuerbescheide, Steuererklärungen, Lohnsteuerbescheinigungen und Schreiben des Finanzamts."),
    (N_("Gesundheit & Medizinisches"), "Arztbriefe, Befunde, Rezepte, Arzt- und Apothekenrechnungen, Schreiben der Krankenkasse."),
    (N_("Behoerden & Amtliches"), "Schreiben von Ämtern und Behörden, Urkunden, Meldebescheinigungen, Rundfunkbeitrag."),
    (N_("Wohnen & Nebenkosten"), "Miet- oder Kaufunterlagen der Wohnung, Nebenkostenabrechnungen, Abrechnungen für Strom, Gas, Wasser, Müll und Grundsteuer."),
    (N_("Haus & Reparaturen"), "Handwerker- und Reparaturrechnungen, Schäden (z. B. Wasserschaden), Wartung, Renovierung und Modernisierung an Haus oder Wohnung, z. B. Sanitär, Heizung, Elektro, Dach, Fenster."),
    (N_("Fahrzeug"), "Nur Unterlagen zu einem Kraftfahrzeug (Auto, Motorrad, Wohnmobil): Fahrzeugpapiere, Rechnungen von Kfz-Werkstätten, TÜV-Berichte, Kfz-Steuer, Leasing und Finanzierung. Erkennbar an Kennzeichen, Fahrgestellnummer oder Kilometerstand."),
    (N_("Arbeit & Gehalt"), "Arbeitsvertrag, Gehaltsabrechnungen, Arbeitszeugnisse und Schreiben des Arbeitgebers."),
    (N_("Bildung"), "Zeugnisse, Schul- und Studienunterlagen, Kurs- und Weiterbildungsnachweise."),
    (N_("Garantien & Kaufbelege"), "Kassenbons, Kaufbelege und Garantiescheine für Geräte und größere Anschaffungen."),
    (N_("Sonstiges"), "Dokumente, die eindeutig in keine der anderen Kategorien passen."),
]


# Unterordner pro Objekt-Adresse (homedms/core/addresses.py) - wie in alembic/versions/0005.
PROPERTY_MODES = {"Haus & Reparaturen": "all", "Wohnen & Nebenkosten": "all", "Versicherungen": "buildings"}


DEFAULT_HOUSEHOLD_NAME = "Home"


class BootstrapRequest(BaseModel):
    # Beispielwerte statt "string" in der API-Doku (/docs) - sonst landet beim Ausprobieren
    # leicht "string" als Haushalts- bzw. Anzeigename in der Datenbank.
    # Ohne Angabe (fehlt, leer oder nur Leerzeichen) heisst der Haushalt "Home": Der Name ist zugleich
    # der oberste Ablage-Ordner, ein neutraler englischer Standard ist dort besser als ein Platzhalter.
    household_name: str = Field(default=DEFAULT_HOUSEHOLD_NAME, max_length=200, examples=["Familie Mustermann"])
    default_language: Literal["de", "en", "ru"] = Field(default="de", examples=["de"])
    # Sprachen der Texterkennung (Tesseract-Codes); leer = Sprache der Oberflaeche + OCR_LANGUAGES
    ocr_languages: list[str] = Field(default_factory=list, max_length=20, examples=[["deu", "eng"]])
    admin_email: EmailStr = Field(examples=["max@example.com"])
    admin_password: str = Field(min_length=8, examples=["ein-langes-Passwort"])
    admin_display_name: str = Field(min_length=1, max_length=200, examples=["Max Mustermann"])
    # Einmal-Code aus dem Server-Protokoll bzw. <Dokumente-Ordner>/.einrichtungscode (core/setup_code.py)
    setup_code: str = Field(min_length=1, max_length=40)

    @field_validator("household_name", mode="before")
    @classmethod
    def _blank_household_name_means_default(cls, value):
        if value is None:
            return DEFAULT_HOUSEHOLD_NAME
        if isinstance(value, str):
            return value.strip() or DEFAULT_HOUSEHOLD_NAME
        return value


class BootstrapResponse(BaseModel):
    tenant_id: str
    admin_user_id: str
    categories_created: int
