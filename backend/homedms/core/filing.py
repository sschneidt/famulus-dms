"""Ablage der Dateien auf dem NAS: "<Haushalt>/<Kategorie>/<Jahr>/<JJJJ-MM-TT Absender – Betreff>.pdf"
(Anforderungsdokument 4.4 - nachvollziehbar, auch direkt ueber Synology File Station einsehbar).

Die Datenbank bleibt die fuehrende Quelle (DocumentFile.file_path); die Ordnerstruktur wird bei
jeder relevanten Aenderung (Kategorie, Datum, Absender, Betreff, Titel, Papierkorb) nachgezogen.

Verschieben ohne Luecke: Erst wird unter dem neuen Namen ein Hardlink angelegt (auf demselben
Dateisystem sofort und ohne Kopie; sonst eine Kopie), dann der neue Pfad gespeichert und erst
danach der alte Name entfernt. Ein Download waehrend des Verschiebens findet die Datei also
immer - und scheitert das Speichern, wird der neue Name wieder entfernt.

Namens- und Pfadregeln: homedms/core/naming.py.
"""
import logging
import mimetypes
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.config import get_settings
from homedms.core.addresses import NO_ADDRESS_FOLDER, uses_property_folder
from homedms.core.naming import file_basename, relative_path, safe_part, with_counter
from homedms.models.document import Category, Document, DocumentFile, Property
from homedms.models.tenant import Tenant

logger = logging.getLogger("homedms.core.filing")


@dataclass
class Move:
    file: DocumentFile
    old: Path
    new: Path


def documents_root() -> Path:
    return Path(get_settings().documents_path)


async def household_folder(db: AsyncSession, tenant_id: uuid.UUID) -> str:
    """Ordnername des Haushalts. Heissen zwei Haushalte gleich, bekommt der spaeter angelegte eine
    Kurz-ID angehaengt - der aeltere behaelt seinen Ordner (keine Wanderbewegung bestehender Dateien)."""
    tenants = (await db.execute(select(Tenant.id, Tenant.name, Tenant.created_at))).all()
    me = next(t for t in tenants if t.id == tenant_id)
    name = safe_part(me.name, "Haushalt")
    earlier_same_name = [
        t for t in tenants
        if t.id != tenant_id
        and safe_part(t.name, "Haushalt").lower() == name.lower()
        and (t.created_at, str(t.id)) < (me.created_at, str(me.id))
    ]
    return f"{name} ({str(tenant_id)[:8]})" if earlier_same_name else name


def _suffix(file: DocumentFile) -> str:
    suffix = Path(file.file_path).suffix
    if suffix:
        return suffix
    return mimetypes.guess_extension(file.mime_type or "") or ""


def _free_path(root: Path, rel, current: Path, taken: set[Path]) -> Path:
    n = 1
    while True:
        candidate = root / (rel if n == 1 else with_counter(rel, n))
        if candidate == current:
            return candidate
        if candidate not in taken and not candidate.exists():
            return candidate
        n += 1


async def plan(db: AsyncSession, document: Document) -> list[Move]:
    """Welche Dateien muessen wohin? Leere Liste = alles liegt schon richtig."""
    root = documents_root()
    household = await household_folder(db, document.tenant_id)
    category = await db.get(Category, document.category_id) if document.category_id else None
    subfolder = None
    if category and uses_property_folder(category.property_mode, document.ocr_text):
        prop = await db.get(Property, document.property_id) if document.property_id else None
        subfolder = prop.name if prop else NO_ADDRESS_FOLDER
    year = (document.document_date or document.created_at.date()).year
    base = file_basename(document.document_date, document.issuer, document.subject, document.title)

    moves: list[Move] = []
    taken: set[Path] = set()
    for file in sorted(document.files, key=lambda f: f.page_number):
        current = Path(file.file_path)
        rel = relative_path(
            household, category.name if category else None, year, base, _suffix(file),
            page=file.page_number, trashed=document.deleted_at is not None, subfolder=subfolder,
        )
        target = _free_path(root, rel, current, taken)
        taken.add(target)
        if target != current:
            moves.append(Move(file, current, target))
    return moves


def _link_or_copy(old: Path, new: Path) -> None:
    new.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(old, new)
    except OSError:  # anderes Dateisystem oder keine Hardlinks moeglich
        shutil.copy2(old, new)


def _prune_empty_dirs(directory: Path, root: Path) -> None:
    """Leer gewordene Ordner (z. B. altes Jahr/alte Kategorie) aufraeumen - nie ueber root hinaus."""
    root = root.resolve()
    current = directory.resolve()
    while current != root and root in current.parents:
        try:
            current.rmdir()  # klappt nur, wenn leer
        except OSError:
            return
        current = current.parent


async def refile(db: AsyncSession, document: Document) -> int:
    """Dateien an ihren Soll-Ort bringen und die Pfade speichern (commit). Liefert die Anzahl
    verschobener Dateien."""
    moves = await plan(db, document)
    done: list[Move] = []
    try:
        for move in moves:
            if not move.old.exists():
                logger.warning("Datei fehlt, kann nicht abgelegt werden: %s", move.old)
                continue
            _link_or_copy(move.old, move.new)
            done.append(move)
            move.file.file_path = str(move.new)
        if done:
            await db.commit()
    except BaseException:
        for move in done:
            move.new.unlink(missing_ok=True)
        raise
    root = documents_root()
    for move in done:
        move.old.unlink(missing_ok=True)
        _prune_empty_dirs(move.old.parent, root)
        logger.info("Abgelegt: %s -> %s", move.old, move.new)
    return len(done)


def relative_to_root(path: str) -> str:
    """Pfad relativ zum Dokumente-Ordner - fuer die Anzeige (ohne interne Container-Pfade)."""
    try:
        return Path(path).relative_to(documents_root()).as_posix()
    except ValueError:
        return Path(path).name
