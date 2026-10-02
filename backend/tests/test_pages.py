"""Mehrseitige Dokumente (homedms/core/pages.py)."""
import io

import pymupdf
import pytest
from PIL import Image

from homedms.core.pages import (
    MAX_PAGES,
    PageError,
    Part,
    as_pdf,
    combine,
    delete_page,
    insert_pages,
    page_count,
    reorder,
    thumbnail,
)


def photo(text_color="black", size=(3000, 4000), exif_rotate=False) -> bytes:
    img = Image.new("RGB", size, "white")
    buf = io.BytesIO()
    exif = None
    if exif_rotate:
        exif = img.getexif()
        exif[0x0112] = 6  # "um 90 Grad gedreht" wie bei Handy-Fotos im Hochformat
    img.save(buf, format="JPEG", exif=exif) if exif else img.save(buf, format="JPEG")
    return buf.getvalue()


def pdf(*texts: str) -> bytes:
    doc = pymupdf.open()
    for t in texts:
        doc.new_page().insert_text((72, 72), t)
    data = doc.tobytes()
    doc.close()
    return data


def texts(data: bytes) -> list[str]:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [p.get_text().strip() for p in doc]


def test_fotos_und_pdf_zu_einem_dokument():
    out = combine([Part(photo(), "seite1.jpg"), Part(pdf("Seite 2", "Seite 3"), "rest.pdf"), Part(photo(), "s4.jpg")])
    assert page_count(out) == 4
    assert texts(out)[1:3] == ["Seite 2", "Seite 3"]


def test_fotos_werden_verkleinert_und_aufgerichtet():
    out = combine([Part(photo(size=(4000, 3000), exif_rotate=True), "quer.jpg")])
    with pymupdf.open(stream=out, filetype="pdf") as doc:
        page = doc[0]
        assert page.rect.height > page.rect.width  # nach EXIF-Drehung Hochformat
        [img] = page.get_images()
        info = doc.extract_image(img[0])
        assert max(info["width"], info["height"]) <= 2500
    assert len(out) < 2_000_000


def test_ungueltige_teile():
    with pytest.raises(PageError, match="nur PDF und Bilder"):
        combine([Part(b"hallo", "mail.eml")])
    with pytest.raises(PageError, match="Bild"):
        combine([Part(b"kein bild", "x.jpg")])
    with pytest.raises(PageError, match="beschaedigt"):
        combine([Part(b"%PDF-1.7 kaputt", "x.pdf")])
    with pytest.raises(PageError):
        combine([])


def test_seiten_einfuegen_loeschen_umsortieren():
    base = pdf("A", "B", "C")
    assert texts(insert_pages(base, [Part(pdf("X"))])) == ["A", "B", "C", "X"]
    assert texts(insert_pages(base, [Part(pdf("X"))], position=1)) == ["X", "A", "B", "C"]
    assert texts(insert_pages(base, [Part(pdf("X"))], position=3)) == ["A", "B", "X", "C"]
    assert texts(delete_page(base, 2)) == ["A", "C"]
    assert texts(reorder(base, [3, 1, 2])) == ["C", "A", "B"]
    with pytest.raises(PageError, match="genau einmal"):
        reorder(base, [1, 1, 2])
    with pytest.raises(PageError, match="gibt es nicht"):
        delete_page(base, 4)
    with pytest.raises(PageError, match="letzte Seite"):
        delete_page(pdf("A"), 1)


def test_hoechstzahl_seiten():
    with pytest.raises(PageError, match=str(MAX_PAGES)):
        combine([Part(pdf(*["x"] * (MAX_PAGES + 1)))])


def test_einzelfoto_wird_zur_pdf_und_vorschaubilder():
    single = Part(photo(size=(800, 1000)), "foto.jpg", "image/jpeg")
    assert page_count(as_pdf(single)) == 1
    assert as_pdf(Part(pdf("A"))) == pdf("A") or page_count(as_pdf(Part(pdf("A")))) == 1
    png = thumbnail(Part(pdf("A", "B")), 2, width=200)
    with Image.open(io.BytesIO(png)) as img:
        assert img.width == 200
    with Image.open(io.BytesIO(thumbnail(single, 1, width=120))) as img:
        assert img.width == 120
    with pytest.raises(PageError):
        thumbnail(Part(pdf("A")), 2)
