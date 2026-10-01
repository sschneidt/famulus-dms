"""Automatische Benennung und Ablagepfade (Anforderungsdokument 4.4 "Ablage").

Reine Funktionen ohne Datenbank - getestet in tests/test_naming.py.

Namensmuster (mit dem Nutzer abgestimmt):
- Titel in der App:  "<Betreff> – <Absender>"      z. B. "Rechnung Wasserschaden-Reparatur – Sanitär Müller GmbH"
  (das Datum steht in der App ohnehin in einer eigenen Spalte)
- Dateiname:         "<JJJJ-MM-TT> <Absender> – <Betreff>.<ext>"  -> sortiert in File Station chronologisch
- Ordner:            "<Haushalt>/<Kategorie>/<Jahr>/"  bzw. "_Unsortiert" / "_Papierkorb";
                     bei Kategorien mit Objekt-Ordnern "<Haushalt>/<Kategorie>/<Ort Strasse Nr>/<Jahr>/"

Dateinamen muessen auf dem NAS (ext4/btrfs) UND fuer Windows-Clients ueber SMB gueltig sein -
deshalb die strengeren Windows-Regeln (keine <>:"/\\|?*, keine reservierten Namen wie CON,
kein Punkt/Leerzeichen am Ende).
"""
import re
import unicodedata
from datetime import date
from pathlib import PurePosixPath

DASH = " – "
MAX_SUBJECT = 80
MAX_BASENAME = 150  # Platz lassen fuer Ordner + " (2)" + Endung; Windows-Pfade max. ~260 Zeichen
UNSORTED = "_Unsortiert"
TRASH = "_Papierkorb"

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
_QUOTES = "\"'„“”‚‘’«»"


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _cut(value: str, limit: int) -> str:
    """Kuerzt an einer Wortgrenze, damit keine halben Woerter im Titel stehen."""
    if len(value) <= limit:
        return value
    cut = value[:limit].rsplit(" ", 1)[0]
    return (cut if len(cut) >= limit // 2 else value[:limit]).rstrip(" -–,;.")


def clean_subject(value: object) -> str | None:
    """Betreff aus der KI-Antwort bereinigen: Anfuehrungszeichen, Zeilenumbrueche, Laenge."""
    text = _squash(unicodedata.normalize("NFC", str(value or ""))).strip(_QUOTES + " .:-–")
    if len(text) < 3:
        return None
    return _cut(text, MAX_SUBJECT) or None


def auto_title(subject: str | None, issuer: str | None) -> str | None:
    """"Betreff – Absender". Steht der Absender schon im Betreff, nur der Betreff.
    Ohne Betreff und ohne Absender: None (dann bleibt der bisherige Titel)."""
    subject = _squash(subject or "")
    issuer = _squash(issuer or "")
    if subject and issuer and issuer.lower() not in subject.lower():
        return f"{subject}{DASH}{issuer}"
    return subject or issuer or None


def safe_part(value: str, fallback: str = "Dokument") -> str:
    """Ein Datei- oder Ordnername, der unter Linux und Windows (SMB) gueltig ist."""
    text = unicodedata.normalize("NFC", value)
    text = _FORBIDDEN.sub(" ", text)
    text = _squash(text).strip(". ")  # kein Punkt vorn (versteckte Datei) oder hinten (Windows)
    if not text:
        return fallback
    if _RESERVED.match(text):
        text = f"_{text}"
    return text


def file_basename(document_date: date | None, issuer: str | None, subject: str | None, title: str) -> str:
    """"JJJJ-MM-TT Absender – Betreff" - fehlende Teile fallen weg, notfalls der Titel."""
    issuer = _squash(issuer or "")
    subject = _squash(subject or "")
    if issuer and subject and issuer.lower() not in subject.lower():
        name = f"{issuer}{DASH}{subject}"
    else:
        name = subject or issuer or _strip_extension(_squash(title))
    if document_date:
        name = f"{document_date.isoformat()} {name}".strip()
    return _cut(safe_part(name), MAX_BASENAME)


def _strip_extension(title: str) -> str:
    """Titel wie "ScannedDocument1.pdf" (Upload-Dateiname) ohne Endung - die kommt separat dazu."""
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", title)


def relative_path(
    household: str,
    category: str | None,
    year: int,
    basename: str,
    suffix: str,
    *,
    page: int = 1,
    trashed: bool = False,
    subfolder: str | None = None,
) -> PurePosixPath:
    """Pfad relativ zum Dokumente-Ordner (DOCUMENTS_PATH). subfolder: Objekt-Ordner (z. B.
    "Stuttgart Musterstraße 5") zwischen Kategorie und Jahr."""
    name = basename if page == 1 else f"{basename} - Seite {page}"
    filename = f"{name}{suffix.lower()}"
    root = PurePosixPath(safe_part(household, "Haushalt"))
    if trashed:
        return root / TRASH / filename
    if not category:
        return root / UNSORTED / str(year) / filename
    folder = root / safe_part(category, UNSORTED)
    if subfolder:
        folder = folder / safe_part(subfolder, "Objekt")
    return folder / str(year) / filename


def with_counter(path: PurePosixPath, n: int) -> PurePosixPath:
    """"Name.pdf" -> "Name (2).pdf" bei Namensgleichheit."""
    return path.with_name(f"{path.stem} ({n}){path.suffix}")


def refresh_title(document) -> bool:
    """Titel aus Betreff/Absender neu bilden - nur wenn der Nutzer keinen eigenen vergeben hat
    (document.title_locked). Liefert True, wenn sich der Titel geaendert hat."""
    if getattr(document, "title_locked", False):
        return False
    title = auto_title(getattr(document, "subject", None), getattr(document, "issuer", None))
    if not title or title == document.title:
        return False
    document.title = title[:300]
    return True
