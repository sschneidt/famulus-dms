"""GET /health - siehe docs/API-Design.md Abschnitt 12. Bewusst ausserhalb von /api/v1 (Docker Healthcheck)."""
from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
