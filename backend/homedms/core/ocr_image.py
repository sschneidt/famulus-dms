"""Texterkennung fuer Fotos und gescannte Seiten - robust gegen typische Handy-Fotos.

Praxisfall (Nutzer, 03.10.2026): Kreditvertrag per Handy fotografiert, erkannter Text nur
"Kauderwelsch". Ursachen, alle hier abgefangen:
1. Drehung: Handys speichern Fotos oft quer und vermerken die Drehung nur in den EXIF-Daten.
   Tesseract kennt EXIF nicht und liest den Text dann seitlich -> Buchstabensalat.
   -> EXIF-Drehung anwenden, danach Tesseracts Ausrichtungserkennung (OSD) fuer Fotos ohne
      EXIF, die quer oder kopfueber aufgenommen wurden.
2. Schatten/ungleichmaessige Ausleuchtung: Tesseract trennt Schrift und Papier mit EINER
   Helligkeitsschwelle fuer die ganze Seite - im Schatten verschwindet dann der Text.
   -> Hintergrund ausgleichen (Seite durch ihre unscharfe Version teilen).
3. Aufloesung: zu kleine Fotos vergroessern, riesige verkleinern.

Es werden zwei Varianten erkannt (Original-Graustufen und ausgeglichen) und die mit mehr sicher
erkannten Zeichen genommen. Bleibt das Ergebnis schwach und war die Ausrichtung nicht sicher
bestimmbar, werden zusaetzlich die anderen Drehungen probiert.
"""
import logging
from dataclasses import dataclass

import pytesseract
from PIL import Image, ImageFilter, ImageMath, ImageOps

from homedms.runtime import configure_tesseract

logger = logging.getLogger("homedms.core.ocr_image")
configure_tesseract()  # Windows: tesseract.exe liegt meist nicht im PATH

MAX_EDGE = 4000
MIN_EDGE = 1600
MIN_CONFIDENCE = 60  # Woerter mit geringerer Tesseract-Konfidenz zaehlen nicht als "sicher erkannt"
WEAK_RESULT_CHARS = 40  # darunter gilt ein Ergebnis als schwach -> weitere Drehungen probieren


@dataclass(frozen=True)
class OcrResult:
    text: str
    good_chars: int  # Zeichen in sicher erkannten Woertern
    rotation: int
    variant: str


def prepare(img: Image.Image) -> Image.Image:
    """EXIF-Drehung anwenden, Graustufen, sinnvolle Groesse."""
    img = ImageOps.exif_transpose(img)
    gray = img.convert("L")
    long_edge = max(gray.size)
    if long_edge > MAX_EDGE:
        scale = MAX_EDGE / long_edge
        gray = gray.resize((round(gray.width * scale), round(gray.height * scale)), Image.Resampling.LANCZOS)
    elif long_edge < MIN_EDGE:
        scale = min(3.0, MIN_EDGE / long_edge)
        gray = gray.resize((round(gray.width * scale), round(gray.height * scale)), Image.Resampling.LANCZOS)
    return gray


def flatten(gray: Image.Image) -> Image.Image:
    """Ausleuchtung ausgleichen: Papier wird ueberall gleich hell, Schrift bleibt dunkel."""
    w, h = gray.size
    # Hintergrund schaetzen: Schrift "wegfiltern" (Maximum = helles Papier) und stark weichzeichnen.
    # Ueber eine verkleinerte Kopie - auf dem vollen Bild waere das auf einem NAS zu langsam.
    small = gray.resize((max(1, w // 8), max(1, h // 8)), Image.Resampling.BILINEAR)
    background = small.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(6))
    background = background.resize((w, h), Image.Resampling.BILINEAR)
    normalized = ImageMath.lambda_eval(
        lambda a: a["convert"](a["min"](a["a"] * 255 / a["max"](a["b"], 1), 255), "L"), a=gray, b=background
    )
    return ImageOps.autocontrast(normalized, cutoff=1)


def detect_rotation(gray: Image.Image) -> int | None:
    """Drehung in Grad (0/90/180/270), die das Bild aufrecht stellt - None, wenn unsicher."""
    try:
        osd = pytesseract.image_to_osd(gray, output_type=pytesseract.Output.DICT, config="--psm 0")
    except pytesseract.TesseractError:
        return None  # zu wenig Text fuer eine Aussage oder osd-Daten fehlen
    rotate = int(osd.get("rotate", 0)) % 360
    if float(osd.get("orientation_conf", 0)) < 1.5:
        return None
    return rotate


def _rotate(gray: Image.Image, degrees: int) -> Image.Image:
    # Tesseract meldet, um wie viel Grad im Uhrzeigersinn gedreht werden muss; PIL dreht gegen ihn.
    return gray.rotate(-degrees, expand=True, fillcolor=255) if degrees else gray


def _ocr(img: Image.Image, lang: str, rotation: int, variant: str) -> OcrResult:
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT, config="--psm 3")
    lines: dict[tuple, list[str]] = {}
    good = 0
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf >= MIN_CONFIDENCE and any(c.isalnum() for c in word):
            good += len(word)
    text_lines: list[str] = []
    previous_block = None
    for (block, _par, _line), words in sorted(lines.items()):
        if previous_block is not None and block != previous_block:
            text_lines.append("")
        text_lines.append(" ".join(words))
        previous_block = block
    return OcrResult("\n".join(text_lines), good, rotation, variant)


def recognize(img: Image.Image, lang: str) -> OcrResult:
    gray = prepare(img)
    rotation = detect_rotation(gray)
    upright = _rotate(gray, rotation or 0)
    flat = flatten(upright)
    results = [_ocr(upright, lang, rotation or 0, "original"), _ocr(flat, lang, rotation or 0, "ausgeglichen")]
    best = max(results, key=lambda r: r.good_chars)
    if best.good_chars < WEAK_RESULT_CHARS and rotation is None:
        for degrees in (90, 180, 270):
            results.append(_ocr(flatten(_rotate(gray, degrees)), lang, degrees, "ausgeglichen"))
        best = max(results, key=lambda r: r.good_chars)
    logger.info("OCR: Drehung %s Grad, Variante %s, %s sicher erkannte Zeichen", best.rotation, best.variant, best.good_chars)
    return best
