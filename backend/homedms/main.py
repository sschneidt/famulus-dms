"""FastAPI-Entrypoint (APP_ROLE=api). Liefert zusaetzlich die gebaute Weboberflaeche aus
(homedms/frontend.py, docs/Docker-Compose-Entwurf.md Abschnitt 1).

Sicherheit (docs/Sicherheitskonzept.md): Sicherheits-Kopfzeilen fuer alle Antworten, die
API-Dokumentation (/docs) nur bei API_DOCS=true, Einrichtungscode im Protokoll solange HomeDMS
noch nicht eingerichtet ist.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select

from homedms.api.router import api_router
from homedms.api.routes.health import router as health_router
from homedms.config import get_settings
from homedms.frontend import mount_frontend
from homedms.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("homedms.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    title="HomeDMS API", version="0.1.0", lifespan=lifespan,
    docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None,
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health_router)  # /health bewusst ausserhalb von /api/v1
app.include_router(api_router)
mount_frontend(app, settings.frontend_dist)  # zuletzt: Catch-all fuer die App
