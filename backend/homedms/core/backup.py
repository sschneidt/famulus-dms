"""Datenbanksicherung aus der Anwendung heraus (Seite "Diagnose").

Eine Sicherung ist ein Abzug der PostgreSQL-Datenbank mit pg_dump im Format "custom" (.dump) - dasselbe,
was die Update-Skripte (scripts/update.sh) anlegen. Wiederherstellen: docs/Updates.md. Die Dokument-
Dateien liegen im Dokumente-Ordner und gehoeren NICHT zur Sicherung; sie sichert man als Ordner.

Der Ordner (BACKUP_PATH) liegt bewusst ausserhalb des Dokumente-Ordners.
"""
import asyncio
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from homedms import __version__
from homedms.config import get_settings
from homedms.i18n import _

logger = logging.getLogger("homedms.backup")

PREFIX = "homedms-"
SUFFIX = ".dump"
NAME = re.compile(r"^homedms-[A-Za-z0-9._-]+\.dump$")  # nur solche Dateien werden angezeigt/geloescht/geladen
MIN_SIZE = 1024  # kleiner kann ein echter Abzug nicht sein


class BackupError(Exception):
    """Mit einer Meldung, die der Anwender lesen darf."""


@dataclass(frozen=True)
class BackupFile:
    name: str
    size: int
    created: datetime


def backup_dir() -> Path:
    return Path(get_settings().backup_path)


def find_pg_dump() -> str | None:
    """pg_dump aus der Einstellung, dem PATH oder (Windows) dem Installationsordner von PostgreSQL."""
    configured = get_settings().pg_dump_cmd.strip()
    if configured:
        return configured if Path(configured).is_file() else shutil.which(configured)
    found = shutil.which("pg_dump")
    if found:
        return found
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            if base:
                candidates = sorted(Path(base).glob("PostgreSQL/*/bin/pg_dump.exe"), reverse=True)
                if candidates:
                    return str(candidates[0])
    return None


def available() -> bool:
    return find_pg_dump() is not None


def _connection() -> tuple[list[str], dict[str, str]]:
    """Verbindungsangaben fuer pg_dump als Argumente + Umgebung (das Passwort bleibt aus der Prozessliste)."""
    url = urlsplit(get_settings().procrastinate_database_url)
    args = ["-h", url.hostname or "localhost", "-p", str(url.port or 5432), "-d", (url.path or "/").lstrip("/")]
    if url.username:
        args += ["-U", unquote(url.username)]
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = unquote(url.password)
    return args, env


def _is_dump_name(name: str) -> bool:
    return bool(NAME.match(name)) and "/" not in name and "\\" not in name


def list_backups() -> list[BackupFile]:
    """Vorhandene Sicherungen, neueste zuerst."""
    directory = backup_dir()
    if not directory.is_dir():
        return []
    result = []
    for path in directory.iterdir():
        if path.is_file() and _is_dump_name(path.name):
            stat = path.stat()
            result.append(BackupFile(path.name, stat.st_size, datetime.fromtimestamp(stat.st_mtime, timezone.utc)))
    return sorted(result, key=lambda b: (b.created, b.name), reverse=True)


def path_of(name: str) -> Path:
    """Pfad einer vorhandenen Sicherung; unzulaessige Namen und Unbekanntes gelten als "nicht gefunden"."""
    path = backup_dir() / name
    if not _is_dump_name(name) or not path.is_file():
        raise FileNotFoundError(name)
    return path


def delete(name: str) -> None:
    path_of(name).unlink()


def prune(keep: int | None = None) -> int:
    """Behaelt nur die neuesten Sicherungen; gibt zurueck, wie viele geloescht wurden."""
    keep = max(1, get_settings().backup_keep if keep is None else keep)
    old = list_backups()[keep:]
    for item in old:
        try:
            (backup_dir() / item.name).unlink()
        except OSError as exc:
            logger.warning("Alte Sicherung %s konnte nicht geloescht werden: %s", item.name, exc)
    return len(old)


async def create() -> BackupFile:
    """Legt eine neue Sicherung an und raeumt danach alte auf. Wirft BackupError mit lesbarer Meldung."""
    exe = find_pg_dump()
    if not exe:
        raise BackupError(_("pg_dump wurde nicht gefunden - die Sicherung aus der Anwendung ist hier nicht möglich."))
    directory = backup_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(_("Der Sicherungsordner {folder} ist nicht beschreibbar ({reason}).", folder=directory, reason=exc)) from exc

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    final = directory / f"{PREFIX}{__version__}-{stamp}{SUFFIX}"
    partial = final.with_name(final.name + ".part")
    args, env = _connection()
    try:
        proc = await asyncio.create_subprocess_exec(
            exe, "-Fc", "-f", str(partial), *args, env=env,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _stdout, err = await proc.communicate()
    except OSError as exc:
        raise BackupError(_("pg_dump konnte nicht gestartet werden ({reason}).", reason=exc)) from exc
    if proc.returncode != 0:
        partial.unlink(missing_ok=True)
        message = err.decode("utf-8", "replace").strip().splitlines()
        logger.error("pg_dump fehlgeschlagen: %s", " | ".join(message))
        raise BackupError(_("Die Sicherung ist fehlgeschlagen: {reason}", reason=message[-1] if message else f"pg_dump Code {proc.returncode}"))
    if not partial.is_file() or partial.stat().st_size < MIN_SIZE:
        partial.unlink(missing_ok=True)
        raise BackupError(_("Die Sicherung ist unvollständig (Datei zu klein)."))
    partial.replace(final)
    removed = prune()
    logger.info("Datenbanksicherung %s angelegt (%d alte entfernt)", final.name, removed)
    stat = final.stat()
    return BackupFile(final.name, stat.st_size, datetime.fromtimestamp(stat.st_mtime, timezone.utc))
