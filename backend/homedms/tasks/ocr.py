"""Hintergrund-Task: OCR/Text-Extraktion pro Dokument - Anforderungsdokument 4.2.

In dieser Iteration abgedeckt (Anforderungsdokument 4.1 nennt die unterstuetzten Formate):
  - PDF mit eingebettetem Text (typische "digitale" PDFs, z. B. Rechnungs-PDF-Exporte):
    Text wird direkt extrahiert - schneller und genauer als OCR, und OCR waere hier unnoetig.
  - PDF ohne (ausreichenden) eingebetteten Text (eingescanntes PDF): Seiten werden gerastert
    und per Tesseract erkannt.
  - Bilder (JPG/PNG/TIFF/HEIC, z. B. Foto-Import): direkt per Tesseract erkannt.
  - E-Mails (.eml): Klartext-/HTML-Body wird extrahiert, kein OCR noetig.

Noch NICHT abgedeckt (siehe backend/README.md "Was noch fehlt"): Office-Dokumente
(Word/Excel) und Outlook .msg (proprietaeres Format, eigene Bibliothek noetig). Solche Dateien
werden erkannt und explizit mit ocr_status=failed markiert statt stillschweigend leer zu bleiben.

Sprachen: Einstellung OCR_LANGUAGES (Standard "deu+eng", Anforderungsdokument 4.2: Primaersprachen).
Damit das im Container tatsaechlich funktioniert, muessen dort die Tesseract-Sprachpakete
tesseract-ocr-deu und tesseract-ocr-eng installiert sein (Dockerfile ist noch offen, siehe
docs/Docker-Compose-Entwurf.md Abschnitt 6 "Offene Punkte") - in dieser Entwicklungsumgebung
ist nur "eng" installiert, siehe die entsprechend angepassten Tests.
"""
import logging
import uuid
from email import message_from_binary_file, policy
from pathlib import Path

import pymupdf  # PyMuPDF - neuer Modulname, "fitz" ist deprecated
import pytesseract
from PIL import Image

from homedms.config import get_settings
from homedms.jobs import app
from homedms.models.document import Document, OcrStatus

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover - optionale Abhaengigkeit, siehe pyproject.toml
    pass

logger = logging.getLogger("homedms.tasks.ocr")

TESSERACT_LANG = get_settings().ocr_languages  # Standard "deu+eng", siehe config.py
MIN_EMBEDDED_TEXT_CHARS = 20  # darunter gilt eine PDF als "nur Bild" (Scan), nicht als "digital"
UNSUPPORTED_SUFFIXES = {".doc", ".docx", ".xls", ".xlsx", ".msg"}


def _extract_pdf_text(path: Path, lang: str) -> str:
    doc = pymupdf.open(path)
    try:
        embedded = "\n".join(page.get_text() for page in doc)
        if len(embedded.strip()) >= MIN_EMBEDDED_TEXT_CHARS:
            return embedded

        # Kein/zu wenig eingebetteter Text -> als Scan behandeln: Seiten rastern + Tesseract.
        parts = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            parts.append(pytesseract.image_to_string(image, lang=lang))
        return "\n".join(parts)
    finally:
        doc.close()


def _extract_image_text(path: Path, lang: str) -> str:
    with Image.open(path) as image:
        return pytesseract.image_to_string(image, lang=lang)


def _extract_eml_text(path: Path) -> str:
    with open(path, "rb") as f:
        message = message_from_binary_file(f, policy=policy.default)
    body = message.get_body(preferencelist=("plain", "html"))
    return body.get_content() if body is not None else ""


def extract_text(path: Path, *, lang: str = TESSERACT_LANG) -> str:
    """Dispatcht nach Dateiendung. Wirft NotImplementedError fuer (noch) nicht unterstuetzte
    Formate - der aufrufende Task faengt das ab und setzt ocr_status=failed."""
    suffix = path.suffix.lower()
    if suffix in UNSUPPORTED_SUFFIXES:
        raise NotImplementedError(f"Textextraktion fuer {suffix} ist noch nicht implementiert")
    if suffix == ".pdf":
        return _extract_pdf_text(path, lang)
    if suffix == ".eml":
        return _extract_eml_text(path)
    return _extract_image_text(path, lang)  # jpg/jpeg/png/tif/tiff/heic/heif


@app.task(name="ocr_document")
async def ocr_document(document_id: str) -> None:
    """Laedt alle Seiten/Dateien eines Dokuments, extrahiert je Seite den Text und fuegt sie
    zusammen. Tesseract/PyMuPDF sind blockierende (synchrone) Aufrufe - laufen deshalb ueber
    einen eigenen Thread (asyncio.to_thread), um den Event-Loop des Workers nicht zu blockieren.
    """
    import asyncio

    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        document = await db.get(Document, uuid.UUID(document_id))
        if document is None:
            logger.warning("ocr_document: Dokument %s existiert nicht mehr - ueberspringe", document_id)
            return

        try:
            texts = []
            for doc_file in sorted(document.files, key=lambda f: f.page_number):
                text = await asyncio.to_thread(extract_text, Path(doc_file.file_path))
                texts.append(text)
            document.ocr_text = "\n\n".join(texts)
            document.ocr_language = TESSERACT_LANG
            document.ocr_status = OcrStatus.done
        except Exception:
            logger.exception("OCR fehlgeschlagen fuer Dokument %s", document_id)
            document.ocr_status = OcrStatus.failed
        finally:
            await db.commit()

    # Naechste Schritte der Kette: Klassifikation (tasks/classification.py) und Metadaten-/
    # Fristenerkennung (tasks/extraction.py). Auch nach fehlgeschlagener Texterkennung - dann
    # landet das Dokument im Feedback-Loop und kann manuell zugeordnet werden, statt unbemerkt
    # ohne Kategorie liegen zu bleiben.
    await app.configure_task("classify_document").defer_async(document_id=document_id)
    await app.configure_task("extract_metadata").defer_async(document_id=document_id)
    # Ablage erst jetzt: waehrend der Texterkennung wird die Datei gelesen und darf nicht wandern.
    from homedms.tasks.filing import defer_filing

    await defer_filing(document_id)
