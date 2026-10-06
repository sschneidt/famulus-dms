"""Automatischer Zuschnitt + Neigungskorrektur (homedms/core/docscan.py) mit kuenstlichen Handy-Fotos.

Grundsatz der Tests: Wo ein Blatt klar zu sehen ist, wird es sauber ausgeschnitten - und wo nicht,
bleibt das Bild unveraendert (lieber Tischrand im Bild als abgeschnittener Text).
"""
import io

import cv2
import numpy as np
import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from homedms.core.docscan import estimate_skew, rectify
from homedms.core.pages import Part, combine
from homedms.tasks.ocr import extract_text

ZEILEN = ["Musterbank AG", "Kreditvertrag Nr. 4711", "Nettodarlehensbetrag 15000 EUR",
          "Laufzeit 60 Monate", "Erste Rate faellig am 01.11.2026"]


def blatt(size=(1240, 1754), rahmen=False, zeilen=24) -> Image.Image:
    """Eine A4-Seite mit Text (wie 150 dpi)."""
    img = Image.new("RGB", size, (244, 242, 236))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=34)
    for i in range(zeilen):
        text = ZEILEN[i] if i < len(ZEILEN) else f"Position {i} Lorem ipsum dolor sit amet {i * 37} EUR"
        draw.text((110, 140 + i * 62), text, fill=(25, 25, 30), font=font)
    if rahmen:  # grosser Tabellenrahmen IM Blatt - darf nicht als "Blatt" missverstanden werden
        draw.rectangle((80, 120, size[0] - 80, size[1] - 160), outline=(20, 20, 20), width=6)
    return img


def tisch(size=(3000, 4000), hell=False) -> np.ndarray:
    """Hintergrund: dunkler (oder heller) Tisch mit etwas Maserung und Rauschen."""
    rng = np.random.default_rng(7)
    base = 228 if hell else 70
    h, w = size[1], size[0]
    grain = (np.sin(np.linspace(0, 40, w))[None, :] * 8 + rng.normal(0, 6, (h, w))).astype(np.float32)
    bg = np.clip(base + grain, 0, 255).astype(np.uint8)
    return cv2.merge([bg, (bg * 0.85).astype(np.uint8) if not hell else bg, (bg * 0.7).astype(np.uint8) if not hell else bg])


def foto(page: Image.Image, ecken, hell=False, size=(3000, 4000)) -> tuple[Image.Image, np.ndarray]:
    """Seite perspektivisch auf den Tisch legen - ecken: ol, or, ur, ul im Foto."""
    src = cv2.cvtColor(np.asarray(page), cv2.COLOR_RGB2BGR)
    w, h = page.size
    quad = np.array(ecken, np.float32)
    m = cv2.getPerspectiveTransform(np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32), quad)
    warped = cv2.warpPerspective(src, m, size, flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, size)
    out = tisch(size, hell)
    out[mask > 0] = warped[mask > 0]
    # etwas Licht-Verlauf wie unter einer Lampe
    shade = np.linspace(1.0, 0.82, size[1], dtype=np.float32)[:, None, None]
    out = np.clip(out * shade, 0, 255).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB)), quad


SCHRAEG_VON_OBEN = [(620, 520), (2380, 640), (2560, 3520), (420, 3380)]


def test_blatt_auf_dem_tisch_wird_ausgeschnitten_und_entzerrt():
    img, quad = foto(blatt(), SCHRAEG_VON_OBEN)
    result = rectify(img)
    assert result.cropped
    assert result.corners is not None
    # Ecken auf ~1,5 % genau gefunden
    assert np.abs(np.array(result.corners) - quad).max() < 0.015 * 4000
    w, h = result.image.size
    assert abs(h / w - 2 ** 0.5) < 0.01  # genau A4
    # Ecken der Ausgabe sind Papier, nicht Tisch
    px = np.asarray(result.image.convert("L"))
    for y, x in ((15, 15), (15, w - 16), (h - 16, 15), (h - 16, w - 16)):
        assert px[y, x] > 150


def test_tabellenrahmen_im_blatt_wird_nicht_fuer_das_blatt_gehalten():
    img, quad = foto(blatt(rahmen=True), SCHRAEG_VON_OBEN)
    result = rectify(img)
    assert result.cropped
    assert np.abs(np.array(result.corners) - quad).max() < 0.015 * 4000


def test_weisses_blatt_auf_weissem_tisch_wird_nicht_falsch_beschnitten():
    """Blattrand kaum sichtbar, aber ein Rahmen im Blatt: NICHT auf den Rahmen zuschneiden."""
    img, _ = foto(blatt(rahmen=True), SCHRAEG_VON_OBEN, hell=True)
    result = rectify(img)
    if result.cropped:  # wenn doch geschnitten, dann nur am echten Blattrand
        assert np.abs(np.array(result.corners) - np.array(SCHRAEG_VON_OBEN)).max() < 0.02 * 4000


@pytest.mark.parametrize("winkel", [-9.0, -3.0, 4.5, 12.0])
def test_schraeger_scan_ohne_blattrand_wird_gerade_gerichtet(winkel):
    page = blatt().rotate(winkel, expand=True, fillcolor=(244, 242, 236), resample=Image.Resampling.BICUBIC)
    assert estimate_skew(np.asarray(page.convert("L"))) == pytest.approx(-winkel, abs=0.4)
    result = rectify(page)
    assert not result.cropped
    assert result.skew == pytest.approx(-winkel, abs=0.4)
    # danach misst man (fast) keine Neigung mehr
    assert abs(estimate_skew(np.asarray(result.image.convert("L")))) <= 0.5


def test_gerader_scan_bleibt_unveraendert():
    page = blatt()
    result = rectify(page)
    assert not result.changed
    assert result.image is page


@pytest.mark.parametrize("motiv", ["rauschen", "verlauf", "leer"])
def test_bilder_ohne_dokument_bleiben_unveraendert(motiv):
    rng = np.random.default_rng(1)
    if motiv == "rauschen":
        arr = rng.integers(0, 255, (1200, 900, 3), dtype=np.uint8)
    elif motiv == "verlauf":
        arr = np.repeat(np.linspace(0, 255, 900, dtype=np.uint8)[None, :, None], 1200, axis=0).repeat(3, axis=2)
    else:
        arr = np.full((1200, 900, 3), 250, np.uint8)
    img = Image.fromarray(arr)
    assert not rectify(img).changed


def test_kaputtes_bild_fuehrt_nie_zum_fehler():
    img = Image.new("RGB", (3, 2), "white")
    assert not rectify(img).changed


def _pdf_bild(pdf: bytes) -> Image.Image:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        [ref] = doc[0].get_images()
        return Image.open(io.BytesIO(doc.extract_image(ref[0])["image"]))


def test_hochgeladenes_foto_wird_als_zugeschnittene_seite_gespeichert():
    img, _ = foto(blatt(), SCHRAEG_VON_OBEN)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    seite = _pdf_bild(combine([Part(buf.getvalue(), "foto.jpg", "image/jpeg")]))
    assert abs(seite.height / seite.width - 2 ** 0.5) < 0.01
    # ohne Zuschnitt (Nutzer hat "Original" gewaehlt) bleibt das Seitenverhaeltnis des Fotos
    seite = _pdf_bild(combine([Part(buf.getvalue(), "foto.jpg", "image/jpeg", auto_crop=False)]))
    assert seite.height / seite.width == pytest.approx(4000 / 3000, abs=0.01)


@pytest.mark.needs_tesseract
def test_zugeschnittenes_foto_wird_gelesen(tmp_path):
    img, _ = foto(blatt(), SCHRAEG_VON_OBEN)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    path = tmp_path / "seite.pdf"
    path.write_bytes(combine([Part(buf.getvalue(), "foto.jpg", "image/jpeg")]))
    text = extract_text(path, lang="eng")
    assert "Kreditvertrag" in text
    assert "01.11.2026" in text
