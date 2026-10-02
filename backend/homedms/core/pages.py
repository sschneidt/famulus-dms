"""Mehrseitige Dokumente (Datenmodell: "Mehrseiten-Scan, Foto-Serie").

Ein Dokument mit mehreren Seiten liegt als EINE PDF-Datei vor - mehrere Handy-Fotos werden beim
Hochladen zu einem PDF zusammengefasst. Vorteile: eine Datei je Dokument in der Ablage (File
Station), Vorschau/Download/Texterkennung wie gehabt, jeder PDF-Betrachter zeigt alle Seiten.
Seiten hinzufuegen, entfernen und umsortieren arbeitet direkt auf dieser PDF.

Reine Funktionen (Bytes rein, Bytes raus), getestet in tests/test_pages.py.
"""
import io
from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pass

MAX_PAGES = 100
MAX_IMAGE_EDGE = 2500  # Handy-Fotos (12+ MP) verkleinern - reicht fuer Texterkennung und Lesen
JPEG_QUALITY = 85
PAGE_WIDTH_PT = 595  # A4-Breite; Hoehe ergibt sich aus dem Seitenverhaeltnis des Fotos
IMAGE_MIMES = {"image/jpeg", "image/png", "image/tiff", "image/webp", "image/heic", "image/heif", "image/gif", "image/bmp"}


class PageError(ValueError):
    """Verstaendliche Fehlermeldung fuer den Nutzer (-> HTTP 422/409)."""


@dataclass(frozen=True)
class Part:
    content: bytes
    filename: str = ""
    mime: str = ""

    @property
    def kind(self) -> str:
        """"pdf", "image" oder "other" - nach Inhalt, nicht nur nach Endung."""
        if self.content.startswith(b"%PDF"):
            return "pdf"
        name = self.filename.lower()
        if self.mime in IMAGE_MIMES or name.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif")):
            return "image"
        return "other"


def _image_page(doc: pymupdf.Document, content: bytes) -> None:
    try:
        with Image.open(io.BytesIO(content)) as img:
            img = ImageOps.exif_transpose(img)  # Handy-Fotos stehen sonst oft quer
            img = img.convert("RGB")
            img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            width, height = img.size
    except Exception as exc:  # noqa: BLE001 - jedes defekte Bild
        raise PageError("Ein Bild konnte nicht gelesen werden") from exc
    page = doc.new_page(width=PAGE_WIDTH_PT, height=PAGE_WIDTH_PT * height / width)
    page.insert_image(page.rect, stream=buf.getvalue())


def _append(doc: pymupdf.Document, part: Part) -> None:
    if part.kind == "pdf":
        try:
            with pymupdf.open(stream=part.content, filetype="pdf") as src:
                if src.needs_pass:
                    raise PageError("Passwortgeschuetzte PDFs koennen nicht zusammengefuegt werden")
                doc.insert_pdf(src)
        except PageError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PageError("Eine PDF-Datei ist beschaedigt") from exc
    elif part.kind == "image":
        _image_page(doc, part.content)
    else:
        raise PageError(f"{part.filename or 'Datei'}: nur PDF und Bilder lassen sich zu Seiten zusammenfassen")


def _save(doc: pymupdf.Document) -> bytes:
    if doc.page_count > MAX_PAGES:
        raise PageError(f"Hoechstens {MAX_PAGES} Seiten je Dokument")
    return doc.tobytes(garbage=3, deflate=True)


def combine(parts: list[Part]) -> bytes:
    """Mehrere PDFs/Bilder in der angegebenen Reihenfolge zu einer PDF zusammenfassen."""
    if not parts:
        raise PageError("Keine Seiten")
    doc = pymupdf.open()
    try:
        for part in parts:
            _append(doc, part)
        return _save(doc)
    finally:
        doc.close()


def as_pdf(current: Part) -> bytes:
    """Vorhandene Datei als PDF (ein Einzelfoto wird zur einseitigen PDF)."""
    return current.content if current.kind == "pdf" else combine([current])


def page_count(content: bytes) -> int:
    if not content.startswith(b"%PDF"):
        return 1
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return 1


def file_page_count(path) -> int:
    """Seitenzahl direkt aus der Datei (ohne sie ganz einzulesen)."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"%PDF":
                return 1
        with pymupdf.open(path) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return 1


def insert_pages(pdf: bytes, parts: list[Part], position: int | None = None) -> bytes:
    """Seiten einfuegen - position 1-basiert (vor dieser Seite), None = ans Ende."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc, pymupdf.open(stream=combine(parts), filetype="pdf") as new:
        if position is None or position > doc.page_count:
            doc.insert_pdf(new)
        else:
            if position < 1:
                raise PageError("Ungueltige Position")
            doc.insert_pdf(new, start_at=position - 1)
        return _save(doc)


def delete_page(pdf: bytes, page: int) -> bytes:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        if not 1 <= page <= doc.page_count:
            raise PageError("Diese Seite gibt es nicht")
        if doc.page_count == 1:
            raise PageError("Die letzte Seite kann nicht entfernt werden - dann lieber das Dokument loeschen")
        doc.delete_page(page - 1)
        return _save(doc)


def reorder(pdf: bytes, order: list[int]) -> bytes:
    """order: neue Reihenfolge als 1-basierte Seitennummern, z. B. [2, 1, 3]."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        if sorted(order) != list(range(1, doc.page_count + 1)):
            raise PageError("Die Reihenfolge muss jede Seite genau einmal enthalten")
        doc.select([p - 1 for p in order])
        return _save(doc)


def thumbnail(current: Part, page: int, width: int = 240) -> bytes:
    """Vorschaubild (PNG) einer Seite."""
    width = max(60, min(width, 1200))
    if current.kind == "pdf":
        with pymupdf.open(stream=current.content, filetype="pdf") as doc:
            if not 1 <= page <= doc.page_count:
                raise PageError("Diese Seite gibt es nicht")
            p = doc[page - 1]
            zoom = width / p.rect.width
            return p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
    if current.kind == "image" and page == 1:
        with Image.open(io.BytesIO(current.content)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((width, width * 4))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    raise PageError("Keine Seitenvorschau fuer diesen Dateityp")
