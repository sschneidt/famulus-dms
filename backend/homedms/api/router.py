"""Aggregiert alle Routen unter /api/v1 - siehe docs/API-Design.md.

Weitere Ressourcen (documents, wiedervorlagen, tags, ...) werden hier ergaenzt, sobald
ihre Routen implementiert sind (siehe README "Was ist implementiert / was fehlt noch").
"""
from fastapi import APIRouter

from homedms.api.routes import (
    auth,
    categories,
    documents,
    household,
    import_sources,
    pages,
    properties,
    retention_rules,
    setup,
    wiedervorlagen,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(household.router)
api_router.include_router(setup.router)
api_router.include_router(categories.router)
api_router.include_router(documents.router)
api_router.include_router(pages.router)
api_router.include_router(pages.photos_router)
api_router.include_router(wiedervorlagen.router)
api_router.include_router(retention_rules.router)
api_router.include_router(properties.router)
api_router.include_router(import_sources.router)
