"""Gemeinsame FastAPI-Dependencies: DB-Session, aktueller Nutzer, Rollen-Check.

tenant_id kommt immer aus dem JWT, nie aus der URL - siehe docs/API-Design.md Abschnitt 1.
"""
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.core.security import decode_token
from homedms.db import get_db
from homedms.models.tenant import RefreshToken, User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungueltiges oder abgelaufenes Token")
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falscher Token-Typ")

    user_id = uuid.UUID(payload["sub"])
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nutzer nicht gefunden")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Dieses Konto ist deaktiviert")
    # Sitzung noch gueltig? Abmelden, "Geraet abmelden", Passwortwechsel, Deaktivieren wirken
    # damit sofort - nicht erst, wenn das Access-Token nach 15 Minuten ablaeuft.
    try:
        session_id = uuid.UUID(payload.get("sid", ""))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bitte neu anmelden")
    active = await db.scalar(select(RefreshToken.id).where(
        RefreshToken.session_id == session_id,
        RefreshToken.user_id == user.id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > datetime.now(timezone.utc),
    ).limit(1))
    if active is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung beendet - bitte neu anmelden")
    request.state.session_id = session_id
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur fuer Admins")
    return user
