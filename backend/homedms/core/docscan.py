"""Fotografierte Dokumente automatisch zuschneiden und gerade richten ("Scanner-App"-Funktion).

Nutzerwunsch (03.10.2026): "beim Aufnehmen der Fotos die automatische Zuschnitt und
Neigungskorrektur". Ein Handy-Foto zeigt das Blatt meist schraeg von oben, mit Tisch drumherum
und leicht verdreht. Hier passiert in zwei Schritten, was eine Scanner-App macht:

1. Zuschnitt + Entzerrung: Blattrand als Viereck finden (Kanten UND hellste zusammenhaengende
   Flaeche, jeweils auf einer verkleinerten Kopie), dann das Viereck perspektivisch zu einem
   Rechteck ziehen. Liegt das Seitenverhaeltnis nahe an DIN A4, wird es genau A4.
2. Neigung: kleine Schraeglagen (bis 15 Grad) ueber die Textzeilen erkennen und ausgleichen -
   auch wenn kein Blattrand zu sehen ist (Foto ganz nah, Scan vom Flachbettscanner).

Grundsatz: lieber nichts tun als falsch schneiden. Ein Viereck wird nur genommen, wenn es
plausibel ist (gross genug, konvex, Winkel nahe 90 Grad, Blatt hebt sich vom Hintergrund ab).
Sonst bleibt das Bild, wie es ist - eine falsch abgeschnittene Seite waere schlimmer als ein
Tischrand im Bild. Drehungen um 90/180 Grad erledigt weiterhin die Texterkennung (ocr_image.py).

Reine Funktion (Bild rein, Bild raus), getestet in tests/test_docscan.py mit kuenstlichen Fotos.
"""
import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("homedms.core.docscan")

DETECT_EDGE = 900       # Erkennung auf einer Kopie mit dieser langen Kante - schnell und robust
WORK_EDGE = 3500        # Entzerrung auf hoechstens dieser Groesse (danach ohnehin max. 2500)
MIN_AREA = 0.18         # Blatt muss mindestens so viel vom Bild fuellen
MAX_AREA = 0.96         # fuellt das Viereck (fast) alles und ist rechtwinklig -> nichts zu tun
MIN_CORNER_ANGLE = 55   # Innenwinkel des Vierecks in Grad (Perspektive verzerrt etwas)
MAX_CORNER_ANGLE = 125
MIN_CONTRAST = 12       # Helligkeitsunterschied Blatt <-> Umgebung am Rand (0-255)
A4_RATIO = 2 ** 0.5
A4_SNAP = 0.08          # +-8 % am A4-Verhaeltnis -> genau A4
MAX_SKEW = 15.0         # groessere Schraeglagen sind keine "Neigung" mehr
MIN_SKEW = 0.4          # darunter lohnt das Drehen nicht
SKEW_PEAK = 1.6         # so deutlich muss die beste Ausrichtung hervorstechen


@dataclass(frozen=True)
class ScanResult:
    image: Image.Image
    cropped: bool = False
    skew: float = 0.0  # ausgeglichene Neigung in Grad
    corners: tuple[tuple[int, int], ...] | None = None  # erkannte Ecken im Eingangsbild (ol, or, ur, ul)

    @property
    def changed(self) -> bool:
        return self.cropped or self.skew != 0.0


# --- Viereck finden ------------------------------------------------------------------------


def _order(pts: np.ndarray) -> np.ndarray:
    """Ecken im Uhrzeigersinn ab oben links."""
    pts = pts.reshape(4, 2).astype(np.float32)
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    pts = pts[np.argsort(angles)]
    return np.roll(pts, -int(np.argmin(pts.sum(axis=1))), axis=0)


def _corner_angles(quad: np.ndarray) -> list[float]:
    result = []
    for i in range(4):
        a, b, c = quad[i - 1], quad[i], quad[(i + 1) % 4]
        v1, v2 = a - b, c - b
        cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
        result.append(float(np.degrees(np.arccos(np.clip(cos, -1, 1)))))
    return result


def _scaled(quad: np.ndarray, factor: float) -> np.ndarray:
    center = quad.mean(axis=0)
    return ((quad - center) * factor + center).astype(np.float32)


def _contrast(gray: np.ndarray, quad: np.ndarray) -> float:
    """Helligkeit knapp innerhalb minus knapp ausserhalb des Blattrands (Betrag)."""
    h, w = gray.shape

    def ring(outer: np.ndarray, inner: np.ndarray) -> np.ndarray:
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [np.round(outer).astype(np.int32)], 255)
        cv2.fillPoly(mask, [np.round(inner).astype(np.int32)], 0)
        return gray[mask > 0]

    # Ringe in festen Abstaenden zum Rand (in Pixeln), damit auch ein Blatt mit schmalem Rand
    # rundherum beurteilt werden kann
    size = float(np.sqrt(cv2.contourArea(quad)))
    step = 0.01 * min(h, w)

    def at(offset: float) -> np.ndarray:
        return _scaled(quad, 1 + 2 * offset * step / size)

    outer, inner = at(2.5), at(0.6)
    inside = ring(at(-0.6), at(-3))
    outside = ring(outer, inner)
    expected = cv2.contourArea(outer.astype(np.float32)) - cv2.contourArea(inner.astype(np.float32))
    if inside.size < 50 or outside.size < 0.6 * expected:
        return 0.0  # Blatt reicht (fast) bis an den Bildrand - Umgebung nicht beurteilbar
    return abs(float(np.median(inside)) - float(np.median(outside)))


def _plausible(quad: np.ndarray, gray: np.ndarray) -> bool:
    h, w = gray.shape
    if not cv2.isContourConvex(quad.reshape(-1, 1, 2).astype(np.int32)):
        return False
    area = cv2.contourArea(quad) / (w * h)
    if not MIN_AREA <= area <= 0.995:
        return False
    if not all(MIN_CORNER_ANGLE <= a <= MAX_CORNER_ANGLE for a in _corner_angles(quad)):
        return False
    sides = [np.linalg.norm(quad[i] - quad[(i + 1) % 4]) for i in range(4)]
    if min(sides) < 0.2 * min(w, h):
        return False
    return _contrast(gray, quad) >= MIN_CONTRAST


def _to_quad(contour: np.ndarray) -> np.ndarray | None:
    """Kontur zu einem Viereck vereinfachen (ueber die konvexe Huelle - Finger/Knicke stoeren so weniger)."""
    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    for eps in (0.01, 0.02, 0.03, 0.045, 0.06, 0.08):
        approx = cv2.approxPolyDP(hull, eps * perimeter, True)
        if len(approx) == 4:
            return _order(approx)
        if len(approx) < 4:
            return None
    return None


def _edge_candidates(gray: np.ndarray) -> list[np.ndarray]:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    median = float(np.median(blurred))
    candidates = []
    for low, high in ((0.66 * median, 1.33 * median), (30, 90), (60, 180)):
        edges = cv2.Canny(blurred, max(5, low), max(20, high))
        edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
            quad = _to_quad(contour)
            if quad is not None:
                candidates.append(quad)
    return candidates


def _brightness_candidates(img: np.ndarray, gray: np.ndarray) -> list[np.ndarray]:
    """Papier ist hell und ungesaettigt - die groesste solche Flaeche ist meist das Blatt."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    paperness = cv2.subtract(hsv[:, :, 2], hsv[:, :, 1])
    paperness = cv2.GaussianBlur(paperness, (7, 7), 0)
    _, mask = cv2.threshold(paperness, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    size = max(3, int(min(gray.shape) * 0.03) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # Schrift im Blatt schliessen
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:2]:
        quad = _to_quad(contour)
        if quad is not None:
            candidates.append(quad)
    return candidates


def find_page(img: np.ndarray) -> np.ndarray | None:
    """Ecken des Blatts (ol, or, ur, ul) in Koordinaten von img - None, wenn nicht sicher erkennbar."""
    h, w = img.shape[:2]
    scale = DETECT_EDGE / max(h, w)
    small = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
    scale = min(scale, 1.0)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    candidates = [q for q in _edge_candidates(gray) + _brightness_candidates(small, gray) if _plausible(q, gray)]
    if not candidates:
        return None
    # Das groesste plausible Viereck ist das Blatt (kleinere sind Kaesten/Tabellen IM Blatt)
    best = max(candidates, key=cv2.contourArea)
    # Kanten werden bei der Erkennung etwas verbreitert -> minimal nach innen, sonst bleibt ein
    # duenner Streifen Tisch am Rand stehen
    inset = 0.004 * min(gray.shape) * 2 / np.sqrt(cv2.contourArea(best))
    return (_scaled(best, 1 - inset) / scale).astype(np.float32)


def _target_size(quad: np.ndarray) -> tuple[int, int]:
    tl, tr, br, bl = quad
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    long_edge, short_edge = max(width, height), min(width, height)
    if abs(long_edge / short_edge - A4_RATIO) / A4_RATIO <= A4_SNAP:
        short_edge = long_edge / A4_RATIO  # Perspektive verfaelscht das Verhaeltnis etwas -> A4
    return (round(long_edge), round(short_edge)) if width >= height else (round(short_edge), round(long_edge))


def _warp(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    width, height = _target_size(quad)
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    matrix = cv2.getPerspectiveTransform(quad.astype(np.float32), target)
    return cv2.warpPerspective(img, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


# --- Neigung -------------------------------------------------------------------------------


def _profile_scores(ink: np.ndarray, angles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = ink.shape
    center = (w / 2, h / 2)
    rows, cols = [], []
    for angle in angles:
        matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(ink, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        rows.append(float(np.var(rotated.sum(axis=1, dtype=np.float64))))
        cols.append(float(np.var(rotated.sum(axis=0, dtype=np.float64))))
    return np.array(rows), np.array(cols)


def estimate_skew(gray: np.ndarray) -> float:
    """Neigung der Textzeilen in Grad (positiv = gegen den Uhrzeigersinn zu drehen); 0 = keine/unsicher.

    Projektionsprofil: Bei der richtigen Drehung liegen die Zeilen genau waagerecht - die Summen
    je Bildzeile wechseln dann am staerksten zwischen "voll Schrift" und "leer". Spalten werden
    ebenso geprueft, damit auch ein quer liegendes Blatt erkannt wird.
    """
    h, w = gray.shape
    scale = 1000 / max(h, w)
    if scale < 1:
        gray = cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ink = cv2.adaptiveThreshold(gray, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    if not 0.004 < float(ink.mean()) < 0.35:
        return 0.0  # kaum Schrift (oder fast alles dunkel) - nichts Verlaessliches zu messen

    coarse = np.arange(-MAX_SKEW, MAX_SKEW + 0.01, 0.5)
    rows, cols = _profile_scores(ink, coarse)
    best = None
    for scores in (rows, cols):
        peak = float(scores.max()) / (float(np.median(scores)) + 1e-9)
        if best is None or peak > best[0]:
            best = (peak, scores)
    peak, scores = best
    if peak < SKEW_PEAK:
        return 0.0
    use_rows = scores is rows
    angle = float(coarse[int(np.argmax(scores))])
    fine = np.arange(angle - 0.5, angle + 0.51, 0.1)
    fine_rows, fine_cols = _profile_scores(ink, fine)
    angle = float(fine[int(np.argmax(fine_rows if use_rows else fine_cols))])
    if abs(angle) < MIN_SKEW or abs(angle) > MAX_SKEW - 0.25:
        return 0.0  # am Rand des Suchbereichs = vermutlich keine echte Zeilenstruktur
    return round(angle, 1)


def _rotate(img: np.ndarray, angle: float) -> np.ndarray:
    """Um angle Grad drehen; die Flaeche waechst mit, damit keine Ecke abgeschnitten wird."""
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(h * sin + w * cos + 0.5), int(h * cos + w * sin + 0.5)
    matrix[0, 2] += new_w / 2 - w / 2
    matrix[1, 2] += new_h / 2 - h / 2
    border = np.concatenate([img[0], img[-1], img[:, 0], img[:, -1]])
    fill = tuple(int(v) for v in np.median(border, axis=0))  # Farbe des Randes (meist Papier)
    return cv2.warpAffine(img, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC, borderValue=fill)


# --- Gesamtablauf --------------------------------------------------------------------------


def rectify(image: Image.Image) -> ScanResult:
    """Blatt ausschneiden, entzerren und gerade richten. Erwartet ein bereits per EXIF aufgerichtetes Bild."""
    try:
        return _rectify(image)
    except Exception:  # noqa: BLE001 - die Verbesserung darf das Hochladen nie verhindern
        logger.exception("Zuschnitt/Neigungskorrektur fehlgeschlagen - Bild bleibt unveraendert")
        return ScanResult(image)


def _rectify(image: Image.Image) -> ScanResult:
    rgb = image.convert("RGB")
    if max(rgb.size) > WORK_EDGE:
        rgb = rgb.copy()
        rgb.thumbnail((WORK_EDGE, WORK_EDGE), Image.Resampling.LANCZOS)
    factor = image.width / rgb.width
    img = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]

    corners = None
    quad = find_page(img)
    if quad is not None:
        area = cv2.contourArea(quad) / (w * h)
        square = all(abs(a - 90) < 3 for a in _corner_angles(quad))
        if area > MAX_AREA and square:
            quad = None  # Blatt fuellt das Bild schon - Zuschnitt wuerde nur Pixel kosten
    if quad is not None:
        img = _warp(img, quad)
        corners = tuple((round(x * factor), round(y * factor)) for x, y in quad)

    skew = estimate_skew(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if skew:
        img = _rotate(img, skew)

    if corners is None and not skew:
        return ScanResult(image)
    out = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    logger.info("Foto aufbereitet: zugeschnitten=%s, Neigung=%.1f Grad", corners is not None, skew)
    return ScanResult(out, cropped=corners is not None, skew=skew, corners=corners)
