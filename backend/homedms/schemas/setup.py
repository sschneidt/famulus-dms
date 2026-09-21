"""Schema fuer POST /setup/bootstrap - Anforderungsdokument 4.7 (Einrichtungsassistent, erster Schritt)."""
from pydantic import BaseModel, EmailStr, Field

# Basis-Kategorien-Set, bestaetigt in Anforderungsdokument 4.3
DEFAULT_CATEGORIES = [
    "Rechnungen", "Vertraege", "Versicherungen", "Bank & Finanzen", "Steuern",
    "Gesundheit & Medizinisches", "Behoerden & Amtliches", "Wohnen & Nebenkosten",
    "Fahrzeug", "Arbeit & Gehalt", "Bildung", "Garantien & Kaufbelege", "Sonstiges",
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
