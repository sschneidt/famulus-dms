"""Sprachen der Texterkennung (Nutzerwunsch: abhaengig von der Oberflaechensprache, weitere
Sprachpakete nachinstallierbar) - core/ocr_languages.py."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import require_admin
from homedms.core import ocr_languages as ocr
from homedms.db import get_db
from homedms.i18n import _
from homedms.models.tenant import Tenant, User
from homedms.schemas.languages import OcrLanguage, OcrLanguagesResponse, OcrLanguagesUpdate

router = APIRouter(prefix="/ocr-languages", tags=["languages"])


async def overview(db: AsyncSession, tenant_id) -> OcrLanguagesResponse:
    tenant = await db.get(Tenant, tenant_id)
    selected = list(tenant.ocr_languages) if tenant.ocr_languages else ocr.configured_default()
    users = (await db.execute(
        select(User.display_name, User.locale).where(User.tenant_id == tenant_id, User.is_active.is_(True))
        .order_by(User.display_name)
    )).all()
    required: dict[str, list[str]] = {}
    for name, locale in users:
        code = ocr.UI_TO_OCR.get(locale or "")
        if code:
            required.setdefault(code, []).append(name)
    have = ocr.installed()
    states = await ocr.install_states(db)
    items = []
    for code, name in ocr.CATALOG.items():
        wanted = code in selected or code in required
        state = states.get(code) or {}
        if code in have:
            status_ = "installed"
        elif state.get("status") in ("installing", "failed"):
            status_ = state["status"]
        else:
            status_ = "missing" if wanted else "available"
        items.append(OcrLanguage(
            code=code, name=name, installed=code in have, selected=code in selected,
            required_by=required.get(code, []), active=wanted and code in have, status=status_,
            error=state.get("error") if status_ == "failed" else None,
        ))
    # Gewaehlte und gebrauchte zuerst, dann installierte, dann der Rest (Katalog-Reihenfolge)
    items.sort(key=lambda i: (not (i.selected or i.required_by), not i.installed))
    return OcrLanguagesResponse(languages=items, effective=await ocr.lang_for(db, tenant_id))


@router.get("", response_model=OcrLanguagesResponse)
async def get_languages(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> OcrLanguagesResponse:
    return await overview(db, user.tenant_id)


@router.put("", response_model=OcrLanguagesResponse)
async def save_languages(
    payload: OcrLanguagesUpdate, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
) -> OcrLanguagesResponse:
    """Auswahl speichern und fehlende Pakete im Hintergrund herunterladen."""
    codes = list(dict.fromkeys(payload.languages))
    unknown = [c for c in codes if c not in ocr.CATALOG]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Unbekanntes Sprachpaket: {code}", code=", ".join(unknown)))
    tenant = await db.get(Tenant, user.tenant_id)
    tenant.ocr_languages = codes
    await db.commit()
    await ocr.request_installs(db, await ocr.missing(db, user.tenant_id))
    return await overview(db, user.tenant_id)


@router.post("/install", response_model=OcrLanguagesResponse)
async def install_missing(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> OcrLanguagesResponse:
    """Fehlende (oder fehlgeschlagene) Pakete erneut herunterladen."""
    await ocr.request_installs(db, await ocr.missing(db, user.tenant_id))
    return await overview(db, user.tenant_id)
