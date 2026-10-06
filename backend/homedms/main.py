"""FastAPI-Entrypoint (APP_ROLE=api). Liefert zusaetzlich die gebaute Weboberflaeche aus
(homedms/frontend.py, docs/Docker-Compose-Entwurf.md Abschnitt 1).

Sicherheit (docs/Sicherheitskonzept.md): Sicherheits-Kopfzeilen fuer alle Antworten, die
API-Dokumentation (/docs) nur bei API_DOCS=true, Einrichtungscode im Protokoll solange Famulus DMS
noch nicht eingerichtet ist.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import func, select

from homedms import __version__
from homedms.api.router import api_router
from homedms.api.routes.health import router as health_router
from homedms.config import get_settings
from homedms.frontend import mount_frontend
from homedms.i18n import LanguageMiddleware, translate_stored
from homedms.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("homedms.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:  # Sprachpakete der Texterkennung (fuer Anzeige und Diagnose)
        from homedms.core import ocr_languages

        ocr_languages.prepare()
    except OSError as exc:
        logger.warning("Sprachpakete nicht vorbereitet: %s", exc)
    try:
        from homedms.core import setup_code
        from homedms.db import async_session_factory
        from homedms.models.tenant import Tenant

        async with async_session_factory() as db:
            if not await db.scalar(select(func.count()).select_from(Tenant)):
                setup_code.announce()
    except Exception as exc:  # noqa: BLE001 - z. B. Datenbank noch nicht bereit: Start nicht verhindern
        logger.warning("Einrichtungsstatus nicht pruefbar: %s", exc)
    yield


settings = get_settings()
docs = settings.api_docs
app = FastAPI(
    title="Famulus DMS API", version=__version__, lifespan=lifespan,
    docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LanguageMiddleware)  # Sprache der Meldungen je Anfrage (Accept-Language)


@app.exception_handler(StarletteHTTPException)
async def translated_http_exception(request: Request, exc: StarletteHTTPException):
    """Meldungen, die (noch) nicht mit _() markiert sind, ueber den Katalog uebersetzen."""
    if isinstance(exc.detail, str):
        exc.detail = translate_stored(exc.detail)
    return await http_exception_handler(request, exc)


app.include_router(health_router)  # /health bewusst ausserhalb von /api/v1
app.include_router(api_router)
mount_frontend(app, settings.frontend_dist)  # zuletzt: Catch-all fuer die App
