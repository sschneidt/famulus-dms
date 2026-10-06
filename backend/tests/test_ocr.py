"""homedms/tasks/ocr.py - Text-/OCR-Extraktion. Laeuft bewusst mit echtem Tesseract (keine DB
noetig dafuer), nutzt aber lang="eng", da in dieser Entwicklungsumgebung nur das englische
Sprachpaket installiert ist (im Produktiv-Image kommt zusaetzlich "deu" dazu - siehe
homedms/tasks/ocr.py Modul-Docstring). Der eigentliche Procrastinate-Task (`ocr_document`, der
Dokumente aus der DB laedt) braucht eine laufende Postgres-Instanz und ist hier nicht abgedeckt.
"""
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

from homedms.tasks.ocr import extract_text


def _make_digital_pdf(path: Path, text: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _make_scanned_pdf(path: Path, text: str) -> None:
    """PDF ohne eingebetteten Textlayer - nur ein gerastertes Bild mit Text, wie bei einem
    eingescannten Dokument."""
    source = pymupdf.open()
    page = source.new_page(width=400, height=200)
    page.insert_text((20, 100), text, fontsize=24)
    pix = page.get_pixmap(dpi=200)

    target = pymupdf.open()
    target_page = target.new_page(width=pix.width, height=pix.height)
    target_page.insert_image(target_page.rect, pixmap=pix)
    target.save(path)
    target.close()
    source.close()


def test_digital_pdf_uses_embedded_text_not_ocr(tmp_path):
    path = tmp_path / "digital.pdf"
    _make_digital_pdf(path, "Hello Famulus DMS Invoice 42 EUR")
    assert extract_text(path, lang="eng").strip() == "Hello Famulus DMS Invoice 42 EUR"


def test_scanned_pdf_falls_back_to_ocr(tmp_path):
    path = tmp_path / "scanned.pdf"
    _make_scanned_pdf(path, "SCANNED SAMPLE")
    text = extract_text(path, lang="eng")
    assert "SCANNED SAMPLE" in text


def test_image_uses_ocr(tmp_path):
    path = tmp_path / "photo.png"
    image = Image.new("RGB", (300, 80), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 25), "PHOTO IMPORT TEST", fill="black")
    image.save(path)

    text = extract_text(path, lang="eng")
    assert "PHOTO" in text.upper()


def test_eml_extracts_plain_text_body(tmp_path):
    path = tmp_path / "mail.eml"
    path.write_text(
        "From: sender@example.com\r\n"
        "To: empfaenger@example.com\r\n"
        "Subject: Test\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Hallo, das ist eine Test-Mail.\r\n"
    )
    text = extract_text(path)
    assert "Test-Mail" in text


def test_unsupported_suffix_raises_not_implemented(tmp_path):
    path = tmp_path / "vertrag.docx"
    path.write_bytes(b"not a real docx, nur fuer den Dateiendungs-Check")
    with pytest.raises(NotImplementedError):
        extract_text(path)


# --- Handy-Fotos (homedms/core/ocr_image.py) ---------------------------------------------------
# Praxisfall: Foto eines Kreditvertrags ergab nur "Kauderwelsch" - das Handy hatte quer gespeichert
# und die Drehung nur in den EXIF-Daten vermerkt; dazu Schatten auf dem Blatt.

def _handy_foto(tmp_path, *, exif_drehung: bool, schatten: bool, kopfueber: bool = False):
    from PIL import Image, ImageDraw, ImageFont

    size = (1240, 1754)
    img = Image.new("L", size, 235)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=40)
    zeilen = ["Musterbank AG", "Kreditvertrag Nr. 4711", "Nettodarlehensbetrag 15000 EUR",
              "Laufzeit 60 Monate", "Erste Rate faellig am 01.11.2026"]
    for i, zeile in enumerate(zeilen):
        draw.text((100, 150 + i * 80), zeile, fill=30, font=font)
    if schatten:
        verlauf = Image.linear_gradient("L").resize(size).rotate(30)
        img = Image.composite(img.point(lambda v: int(v * 0.45)), img, verlauf.point(lambda v: 255 - v))
    img = img.convert("RGB")
    if kopfueber:
        img = img.rotate(180)
    path = tmp_path / "foto.jpg"
    if exif_drehung:
        img = img.rotate(90, expand=True)
        exif = img.getexif()
        exif[0x0112] = 6
        img.save(path, "JPEG", quality=85, exif=exif)
    else:
        img.save(path, "JPEG", quality=85)
    return path


@pytest.mark.parametrize(
    ("exif_drehung", "schatten", "kopfueber"),
    [(True, False, False), (False, True, False), (True, True, False), (False, False, True)],
)
def test_handy_foto_wird_lesbar_erkannt(tmp_path, exif_drehung, schatten, kopfueber):
    path = _handy_foto(tmp_path, exif_drehung=exif_drehung, schatten=schatten, kopfueber=kopfueber)
    text = extract_text(path, lang="eng")
    assert "Kreditvertrag" in text
    assert "Musterbank" in text
    assert "01.11.2026" in text
