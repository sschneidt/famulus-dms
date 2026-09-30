"""FastAPI-Entrypoint (APP_ROLE=api). Liefert zusaetzlich die gebaute Weboberflaeche aus
(homedms/frontend.py, docs/Docker-Compose-Entwurf.md Abschnitt 1).
"""
from fastapi import FastAPI

from homedms.api.router import api_router
from homedms.api.routes.health import router as health_router
from homedms.config import get_settings
from homedms.frontend import mount_frontend

app = FastAPI(title="HomeDMS API", version="0.1.0")

app.include_router(health_router)  # /health bewusst ausserhalb von /api/v1
app.include_router(api_router)
mount_frontend(app, get_settings().frontend_dist)  # zuletzt: Catch-all fuer die App
