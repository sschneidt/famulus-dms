"""FastAPI-Entrypoint (APP_ROLE=api). Liefert spaeter zusaetzlich die gebaute PWA aus
(docs/Docker-Compose-Entwurf.md Abschnitt 1) - StaticFiles-Mount folgt, sobald das Frontend existiert.
"""
from fastapi import FastAPI

from homedms.api.router import api_router
from homedms.api.routes.health import router as health_router

app = FastAPI(title="HomeDMS API", version="0.1.0")

app.include_router(health_router)  # /health bewusst ausserhalb von /api/v1
app.include_router(api_router)
