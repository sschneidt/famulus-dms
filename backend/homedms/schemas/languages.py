"""Sprachen der Texterkennung - Seite "Sprachen" (nur Admin)."""
from pydantic import BaseModel, Field


class OcrLanguage(BaseModel):
    code: str           # Tesseract-Code, z. B. "rus"
    name: str           # Name in der Sprache selbst, z. B. "Русский"
    installed: bool
    selected: bool      # vom Admin gewaehlt (bzw. Standard aus OCR_LANGUAGES)
    required_by: list[str] = []  # Personen, deren Oberflaeche diese Sprache braucht
    active: bool        # wird bei der Texterkennung verwendet (gewaehlt oder gebraucht, installiert)
    status: str         # installed | installing | failed | missing | available
    error: str | None = None


class OcrLanguagesResponse(BaseModel):
    languages: list[OcrLanguage]
    effective: str      # aktuell an Tesseract uebergeben, z. B. "deu+eng+rus"


class OcrLanguagesUpdate(BaseModel):
    languages: list[str] = Field(min_length=1, max_length=20)
