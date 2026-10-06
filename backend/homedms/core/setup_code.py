"""Einmal-Code fuer die Ersteinrichtung.

Ohne Code koennte sich, wer eine frische Installation zuerst aufruft (z. B. ein Mitbewohner oder
ein fremdes Geraet im WLAN), zum Admin machen. Der Code steht nur dort, wo der Besitzer hinkommt:
im Protokoll des Servers (docker compose logs app-api), in der Datei .einrichtungscode im
Dokumente-Ordner bzw. - bei den Installationsskripten - in der Ausgabe am Ende.
"""
import logging
import secrets
from pathlib import Path

from homedms.config import get_settings

logger = logging.getLogger("homedms.setup")

FILE_NAME = ".einrichtungscode"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _file() -> Path:
    return Path(get_settings().documents_path) / FILE_NAME


def get_or_create() -> str:
    configured = get_settings().setup_code.strip()
    if configured:
        return configured
    path = _file()
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    code = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError as exc:
        logger.warning("Einrichtungscode konnte nicht gespeichert werden (%s) - er gilt bis zum Neustart", exc)
        get_settings().setup_code = code
    return code


def matches(code: str) -> bool:
    return secrets.compare_digest(code.strip().upper(), get_or_create().upper())


def announce() -> None:
    code = get_or_create()
    bar = "=" * 64
    logger.warning("\n%s\n  Famulus DMS ist noch nicht eingerichtet.\n  Einrichtungscode: %s\n"
                   "  (steht auch in %s)\n%s", bar, code, _file(), bar)


def remove() -> None:
    try:
        _file().unlink(missing_ok=True)
    except OSError:
        pass
