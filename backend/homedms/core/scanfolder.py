"""Scan-Ordner-Import (Anforderungsdokument 4.1): Scanner/Multifunktionsgeraet legt Dateien per
SMB/FTP in einen NAS-Ordner, HomeDMS holt sie automatisch ab.

Ablauf je Datei (Job tasks/scanfolder.py, jede Minute):
1. Nur "fertige" Dateien: seit mind. MIN_AGE_SECONDS unveraendert und - bei PDF/Bild - vollstaendig
   lesbar. Ein Scanner, der gerade noch schreibt, wird so nicht halb importiert.
2. Gleicher Inhalt schon vorhanden (Pruefsumme)? Dann kein zweites Dokument.
3. Import als Dokument des Haushalts (kein einzelner Eigentuemer), danach laeuft die gewohnte
   Kette: Texterkennung -> Kategorie, Metadaten, Fristen -> Ablage.
4. Original nach "_importiert/JJJJ-MM/" verschieben; Unbrauchbares nach "_fehler/".

Reine Hilfsfunktionen hier (getestet in tests/test_scanfolder.py).
"""
import time
from pathlib import Path

SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif", ".webp", ".eml"}
DONE_DIR = "_importiert"
ERROR_DIR = "_fehler"
MIN_AGE_SECONDS = 30
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_FILES_PER_RUN = 50  # grosse Stapel in mehreren Durchgaengen, damit ein Lauf nicht ewig dauert

# Ordner, die nie durchsucht werden: eigene Ablage, Synology-Vorschaubilder/Papierkorb, Systemdateien
SKIP_DIRS = {DONE_DIR, ERROR_DIR, "@eaDir", "#recycle", "#snapshot", ".AppleDouble", "$RECYCLE.BIN"}


def is_ignored_name(name: str) -> bool:
    """Versteckte/temporaere Dateien von Scannern, Office, macOS und Windows."""
    lower = name.lower()
    return (
        name.startswith((".", "~$", "._"))
        or lower in {"thumbs.db", "desktop.ini", ".ds_store"}
        or lower.endswith((".tmp", ".part", ".crdownload", ".partial", ".filepart"))
    )


def candidates(root: Path) -> list[Path]:
    """Alle Dateien unterhalb von root (auch in Unterordnern), aelteste zuerst."""
    found: list[Path] = []
    if not root.is_dir():
        return found
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue  # nie Verweisen aus dem Scan-Ordner hinaus folgen
            if entry.is_dir():
                if entry.name not in SKIP_DIRS and not entry.name.startswith("."):
                    stack.append(entry)
            elif entry.is_file() and not is_ignored_name(entry.name):
                found.append(entry)
    return sorted(found, key=lambda p: (p.stat().st_mtime, str(p)))


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED


def is_settled(path: Path, now: float | None = None, min_age: float = MIN_AGE_SECONDS) -> bool:
    """Seit min_age Sekunden nicht mehr geaendert -> der Scanner ist (wohl) fertig."""
    now = time.time() if now is None else now
    try:
        return now - path.stat().st_mtime >= min_age
    except OSError:
        return False


def looks_complete(path: Path, content: bytes) -> str | None:
    """None = in Ordnung, sonst Grund. Faengt abgebrochene Uebertragungen ab."""
    if not content:
        return "Datei ist leer"
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if not content.startswith(b"%PDF"):
            return "keine gueltige PDF-Datei"
        if b"%%EOF" not in content[-2048:]:
            return "PDF unvollstaendig (wird evtl. noch geschrieben)"
    elif suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif"}:
        try:
            from io import BytesIO

            from PIL import Image

            try:
                import pillow_heif

                pillow_heif.register_heif_opener()
            except ImportError:  # pragma: no cover
                pass
            with Image.open(BytesIO(content)) as img:
                img.load()  # liest die ganzen Bilddaten - abgeschnittene Dateien scheitern hier
        except Exception as exc:  # noqa: BLE001 - jede Art von defektem Bild
            return f"Bild nicht lesbar ({exc.__class__.__name__})"
    return None


def destination(base: Path, name: str) -> Path:
    """Freier Dateiname im Zielordner ("Scan.pdf", "Scan (2).pdf", ...)."""
    target = base / name
    n = 2
    while target.exists():
        target = base / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return target


def title_from_filename(name: str) -> str:
    """"Scan_2026-10-02_0815.pdf" -> "Scan_2026-10-02_0815" (vorlaeufig, bis die KI benennt)."""
    return Path(name).stem[:300] or "Scan"
