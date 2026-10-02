"""Import-Quellen (Scan-Ordner) - docs/API-Design.md Abschnitt 8, nur Admin.

Bei einem einzigen Haushalt richtet sich der Scan-Ordner beim ersten Durchlauf selbst ein
(tasks/scanfolder.py). Teilen sich mehrere Haushalte eine Installation, bekommt jeder einen
eigenen Unterordner - Ueberschneidungen sind ausgeschlossen, damit nie Dateien eines Haushalts
bei einem anderen landen.
"""
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import require_admin
from homedms.db import get_db
from homedms.jobs import app as jobs_app
from homedms.models.ops import ImportSource
from homedms.models.tenant import User
from homedms.schemas.import_source import ImportSourceCreate, ImportSourceResponse, ImportSourceUpdate
from homedms.tasks.scanfolder import request_scan

router = APIRouter(prefix="/import-sources", tags=["import-sources"])


def normalize_path(raw: str) -> str:
    """Unterordner relativ zum Scan-Ordner: "Familie/Scans" - kein "..", kein absoluter Pfad."""
    parts = [p for p in PurePosixPath(raw.replace("\\", "/").strip()).parts if p not in ("", ".", "/")]
    if any(p == ".." or p.startswith("_") or p.startswith("@") or p.startswith("#") for p in parts):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ungueltiger Ordnername")
    return "/".join(parts)


def overlaps(a: str, b: str) -> bool:
    """"" ueberschneidet sich mit allem, "a" mit "a/b"."""
    pa, pb = PurePosixPath(a) if a else None, PurePosixPath(b) if b else None
    if pa is None or pb is None:
        return True
    return pa == pb or pa in pb.parents or pb in pa.parents


async def _check_overlap(db: AsyncSession, path: str, exclude: uuid.UUID | None = None) -> None:
    others = (await db.execute(select(ImportSource).where(ImportSource.type == "nas_watch_folder"))).scalars().all()
    for other in others:
        if other.id != exclude and overlaps(path, (other.config or {}).get("path", "")):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Dieser Ordner ueberschneidet sich mit einem bereits eingerichteten Scan-Ordner",
            )


def _response(source: ImportSource) -> ImportSourceResponse:
    config = source.config or {}
    state = config.get("status") or {}
    return ImportSourceResponse(
        id=source.id, type=source.type, path=config.get("path", ""), is_active=source.is_active,
        last_scanned_at=source.last_scanned_at, waiting=state.get("waiting", 0), error=state.get("error"),
        recent=source.recent or [],
    )


async def _get(db: AsyncSession, user: User, source_id: uuid.UUID) -> ImportSource:
    source = await db.get(ImportSource, source_id)
    if source is None or source.tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import-Quelle nicht gefunden")
    return source


@router.get("", response_model=list[ImportSourceResponse])
async def list_sources(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> list[ImportSourceResponse]:
    sources = (await db.execute(
        select(ImportSource).where(ImportSource.tenant_id == user.tenant_id).order_by(ImportSource.id)
    )).scalars().all()
    return [_response(s) for s in sources]


@router.post("", response_model=ImportSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: ImportSourceCreate, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> ImportSourceResponse:
    path = normalize_path(payload.path)
    await _check_overlap(db, path)
    source = ImportSource(tenant_id=user.tenant_id, type="nas_watch_folder", config={"path": path}, is_active=True, recent=[])
    db.add(source)
    await db.commit()
    return _response(source)


@router.patch("/{source_id}", response_model=ImportSourceResponse)
async def update_source(
    source_id: uuid.UUID, payload: ImportSourceUpdate,
    user: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
) -> ImportSourceResponse:
    source = await _get(db, user, source_id)
    if payload.path is not None:
        path = normalize_path(payload.path)
        await _check_overlap(db, path, exclude=source.id)
        source.config = {**(source.config or {}), "path": path, "status": {}}
    if payload.is_active is not None:
        source.is_active = payload.is_active
    await db.commit()
    return _response(source)


@router.post("/{source_id}/scan-now", status_code=status.HTTP_202_ACCEPTED)
async def scan_now(
    source_id: uuid.UUID, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    """Ordner sofort pruefen statt beim naechsten Minuten-Takt."""
    await _get(db, user, source_id)
    async with jobs_app.open_async():
        queued = await request_scan()
    return {"queued": queued}
