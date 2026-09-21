"""Speicherort fuer Dokument-Dateien - siehe docs/Docker-Compose-Entwurf.md Abschnitt 4
(DOCUMENTS_PATH) und docs/Anforderungsdokument.md 4.4.

Aktuell: chronologische Ablage `<tenant_id>/<jahr>/<dokument_id>/page-NNN.<ext>`. Die im
Anforderungsdokument 4.4 zusaetzlich beschriebene Ablage "nach Kategorie" folgt als spaeterer
Verschiebe-Schritt, sobald die Klassifikation feststeht (siehe backend/README.md "Was noch fehlt") -
Umbenennen/Verschieben nach Kategorie waere vor der ersten Klassifikation ohnehin nicht sinnvoll,
da die Kategorie zum Upload-Zeitpunkt meist noch nicht bekannt ist.
"""
import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from homedms.config import get_settings

settings = get_settings()


def _sanitize_suffix(filename: str) -> str:
    """Nur die Dateiendung wird aus dem Originalnamen uebernommen (z. B. gegen Pfad-Traversal
    ueber manipulierte Upload-Dateinamen) - der Rest des Namens wird durch page-NNN ersetzt."""
    suffix = Path(filename).suffix
    normalized = unicodedata.normalize("NFKD", suffix).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9.]+", "", normalized)
    return normalized if normalized.startswith(".") and len(normalized) <= 10 else ""


def document_directory(tenant_id: uuid.UUID, document_id: uuid.UUID) -> Path:
    year = datetime.now(timezone.utc).year
    return Path(settings.documents_path) / str(tenant_id) / str(year) / str(document_id)


def document_file_path(
    tenant_id: uuid.UUID, document_id: uuid.UUID, page_number: int, original_filename: str
) -> Path:
    suffix = _sanitize_suffix(original_filename)
    return document_directory(tenant_id, document_id) / f"page-{page_number:03d}{suffix}"


def save_upload(path: Path, content: bytes) -> str:
    """Schreibt den Datei-Inhalt und liefert die SHA-256-Pruefsumme (DocumentFile.checksum)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()
