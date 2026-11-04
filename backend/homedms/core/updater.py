"""Update aus der Anwendung anstossen (Seite "Diagnose", Knopf "Jetzt aktualisieren").

Die Anwendung hat KEINEN Zugriff auf Docker. Sie spricht mit dem Update-Helfer (scripts/update-agent.sh, laeuft als
Aufgabe auf der Synology oder als eigener Container) nur ueber Dateien im Sicherungsordner (BACKUP_PATH):

  update-agent.txt     Lebenszeichen des Helfers (Unix-Zeit), vom Helfer geschrieben
  update-request.txt   Anforderung "version=X.Y.Z", von hier geschrieben, vom Helfer abgeholt und geloescht
  update-status.json   Fortschritt des Helfers: state, version, detail, at

Ohne Lebenszeichen gilt kein Helfer als vorhanden und die Oberflaeche zeigt keinen Aktualisieren-Knopf. Vor jeder
Anforderung wird die Datenbank gesichert; der Helfer selbst sichert nichts.
"""
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from homedms import __version__
from homedms.core import backup, updates
from homedms.i18n import _

logger = logging.getLogger("homedms.updater")

REQUEST = "update-request.txt"
STATUS = "update-status.json"
HEARTBEAT = "update-agent.txt"
HEARTBEAT_MAX_AGE = 150  # Sekunden; die Synology-Aufgabe laeuft jede Minute, der Container alle 10 Sekunden
REQUEST_MAX_AGE = 300  # eine Anforderung, die so lange liegt, wurde nicht abgeholt
STATES = {"checking", "pulling", "restarting", "health", "done", "failed", "rolled_back"}
ACTIVE = {"requested", "checking", "pulling", "restarting", "health"}
_VERSION = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")


class UpdaterError(Exception):
    """Mit einer Meldung, die der Anwender lesen darf."""


@dataclass(frozen=True)
class AgentStatus:
    available: bool  # ein Update-Helfer ist erreichbar
    state: str | None  # None, requested oder ein Zustand aus STATES
    version: str | None
    detail: str


def _dir() -> Path:
    return backup.backup_dir()


def _read(name: str) -> str | None:
    path = _dir() / name
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def agent_alive(now: float | None = None) -> bool:
    text = _read(HEARTBEAT)
    try:
        beat = int((text or "").strip())
    except ValueError:
        return False
    return 0 <= (now or time.time()) - beat <= HEARTBEAT_MAX_AGE


def status(now: float | None = None) -> AgentStatus:
    now = now or time.time()
    alive = agent_alive(now)
    request_path = _dir() / REQUEST
    if request_path.is_file():
        try:
            age = now - request_path.stat().st_mtime
        except OSError:
            age = 0
        requested = _read(REQUEST) or ""
        match = re.search(r"^version=(\S+)", requested, re.MULTILINE)
        version = match[1] if match else None
        if alive and age <= REQUEST_MAX_AGE:
            return AgentStatus(True, "requested", version, "")
        return AgentStatus(alive, "failed", version, "not_picked_up")

    raw = _read(STATUS)
    if raw:
        try:
            data = json.loads(raw)
            state = data.get("state")
            if state in STATES:
                version = data.get("version")
                return AgentStatus(
                    alive or state in ACTIVE, state, version if isinstance(version, str) and version else None,
                    str(data.get("detail") or "")[:200],
                )
        except (ValueError, AttributeError):
            logger.warning("update-status.json ist nicht lesbar")
    return AgentStatus(alive, None, None, "")


async def request(version: str) -> AgentStatus:
    """Sichert die Datenbank und legt die Anforderung ab. Wirft UpdaterError mit lesbarer Meldung."""
    if not _VERSION.match(version):
        raise UpdaterError(_("Ungültige Versionsnummer."))
    if not updates.is_newer(version, __version__):
        raise UpdaterError(_("Version {version} ist nicht neuer als die installierte {current}.", version=version, current=__version__))
    current = status()
    if not current.available:
        raise UpdaterError(_("Es läuft kein Update-Helfer. Siehe Installationsanleitung, Abschnitt „Aktualisieren aus der Anwendung“."))
    if current.state in ACTIVE:
        raise UpdaterError(_("Ein Update läuft bereits."))
    if not backup.available():
        raise UpdaterError(_("Ohne Datenbanksicherung wird nicht aktualisiert, und pg_dump wurde nicht gefunden."))
    try:
        await backup.create()
    except backup.BackupError as exc:
        raise UpdaterError(_("Vor dem Update konnte die Datenbank nicht gesichert werden: {reason}", reason=exc)) from exc

    directory = _dir()
    (directory / STATUS).unlink(missing_ok=True)
    tmp = directory / f".{REQUEST}.{os.getpid()}"
    try:
        tmp.write_text(f"version={version}\n", encoding="utf-8")
        tmp.replace(directory / REQUEST)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise UpdaterError(_("Der Sicherungsordner ist nicht beschreibbar ({reason}).", reason=exc)) from exc
    logger.info("Update auf %s angefordert", version)
    return status()
