"""POST /setup/bootstrap, GET /setup/status - Anforderungsdokument 4.7 (Einrichtungsassistent, erster Schritt).

Legt einmalig Tenant + ersten Admin-User + Basis-Kategorien-Set an. Danach uebernimmt der
Web-Einrichtungsassistent (separates Frontend-Kapitel) die weiteren inhaltlichen Schritte.
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.i18n import _
from homedms.config import get_settings
from homedms.core import login_guard, ocr_languages, setup_code
from homedms.core.security import hash_password
from homedms.db import get_db
from homedms.models.document import Category
from homedms.models.tenant import Tenant, User, UserRole
from homedms.schemas.setup import DEFAULT_CATEGORIES, PROPERTY_MODES, BootstrapRequest, BootstrapResponse

router = APIRouter(prefix="/setup", tags=["setup"])
logger = logging.getLogger("homedms.setup")


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Oeffentlich (vor der Anmeldung): eingerichtet? und Verbindungsdaten fuer die Zertifikat-Hilfe."""
    tenant_count = await db.scalar(select(func.count()).select_from(Tenant))
    settings = get_settings()
    bootstrapped = (tenant_count or 0) > 0
    extra = {}
    if not bootstrapped:  # fuer die Ersteinrichtung: welche Sprachpakete gibt es, welche sind schon da
        have = ocr_languages.installed()
        extra["ocr_languages"] = [{"code": c, "name": n, "installed": c in have} for c, n in ocr_languages.CATALOG.items()]
    return extra | {
        "bootstrapped": bootstrapped,
        "tls": settings.tls_mode == "auto",  # eigene Zertifizierungsstelle -> Geraete muessen ihr vertrauen
        "http_port": int(os.environ.get("PORT", "8000")),
        "https_port": settings.https_port,
    }


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap(payload: BootstrapRequest, request: Request, db: AsyncSession = Depends(get_db)) -> BootstrapResponse:
    """Nur erlaubt, solange noch kein Tenant existiert (einmaliger Ersteinrichtungs-Schritt) - und nur
    mit dem Einrichtungscode, den der Server beim Start ins Protokoll schreibt (core/setup_code.py)."""
    ip = request.client.host if request.client else "?"
    login_guard.check_ip(ip)
    if not setup_code.matches(payload.setup_code):
        login_guard.record_ip_failure(ip)
        raise HTTPException(status.HTTP_403_FORBIDDEN, _("Der Einrichtungscode stimmt nicht - er steht im Protokoll des "
                                                          "Servers und in der Datei .einrichtungscode im Dokumente-Ordner"))
    existing = await db.scalar(select(func.count()).select_from(Tenant))
    if (existing or 0) > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            _("Es existiert bereits ein Haushalt - Ersteinrichtung ist nur einmal moeglich."),
        )

    unknown = [c for c in payload.ocr_languages if c not in ocr_languages.CATALOG]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Unbekanntes Sprachpaket: {code}", code=", ".join(unknown)))
    tenant = Tenant(name=payload.household_name, default_language=payload.default_language,
                    ocr_languages=list(dict.fromkeys(payload.ocr_languages)) or None)
    db.add(tenant)
    await db.flush()  # tenant.id verfuegbar machen, ohne schon zu committen

    admin = User(
        tenant_id=tenant.id,
        email=payload.admin_email,
        password_hash=hash_password(payload.admin_password),
        display_name=payload.admin_display_name,
        role=UserRole.admin,
        locale=payload.default_language,
        notification_channels={"in_app": True, "email": True, "push": False},
    )
    db.add(admin)

    for name, description in DEFAULT_CATEGORIES:
        db.add(
            Category(
                tenant_id=tenant.id,
                name=name,
                description=description,
                is_system_default=True,
                is_restricted=False,
                property_mode=PROPERTY_MODES.get(name, "none"),
            )
        )

    await db.commit()
    setup_code.remove()  # einmalig - danach nicht mehr noetig
    try:  # fehlende Sprachpakete im Hintergrund nachladen
        await ocr_languages.request_installs(db, await ocr_languages.missing(db, tenant.id))
    except Exception as exc:  # noqa: BLE001 - die Einrichtung selbst ist erfolgreich
        logger.warning("Sprachpakete nicht angefordert: %s", exc)

    return BootstrapResponse(
        tenant_id=str(tenant.id),
        admin_user_id=str(admin.id),
        categories_created=len(DEFAULT_CATEGORIES),
    )
