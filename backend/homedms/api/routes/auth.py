"""POST /auth/login, /auth/refresh, /auth/logout, GET/PATCH /auth/me, PUT /auth/password - API-Design.md 2."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user
from homedms.config import get_settings
from homedms.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token_plaintext,
    verify_password,
)
from homedms.db import get_db
from homedms.models.tenant import RefreshToken, Tenant, User
from homedms.schemas.auth import (
    LoginRequest,
    MeResponse,
    PasswordChange,
    ProfileUpdate,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


async def _issue_tokens(user: User, db: AsyncSession) -> TokenResponse:
    access_token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role.value)

    refresh_plain = new_refresh_token_plaintext()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_plain),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_ttl_days),
        )
    )
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_plain)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    # Gross-/Kleinschreibung der E-Mail egal (beim Anlegen wird sie ebenso verglichen, routes/users.py)
    result = await db.execute(select(User).where(func.lower(User.email) == payload.email.lower()))
    user = result.scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-Mail oder Passwort falsch")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Dieses Konto ist deaktiviert - bitte an den Admin wenden")

    user.last_login_at = datetime.now(timezone.utc)
    return await _issue_tokens(user, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if stored is None or stored.revoked_at is not None or stored.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh-Token ungueltig oder abgelaufen")

    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nutzer nicht gefunden oder deaktiviert")

    # Rotation: altes Refresh-Token widerrufen, neues ausstellen
    stored.revoked_at = now
    return await _issue_tokens(user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def _me(user: User, db: AsyncSession) -> MeResponse:
    tenant = await db.get(Tenant, user.tenant_id)
    return MeResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        locale=user.locale,
        household_name=tenant.name if tenant else "",
    )


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeResponse:
    return await _me(user, db)


@router.patch("/me", response_model=MeResponse)
async def update_me(
    payload: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    """Eigenen Anzeigenamen aendern (E-Mail und Rolle aendert nur ein Admin)."""
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bitte einen Namen angeben")
    user.display_name = name
    await db.commit()
    return await _me(user, db)


async def revoke_refresh_tokens(db: AsyncSession, user_id, keep_current: bool = False) -> None:
    """Alle Anmeldungen eines Nutzers beenden (Refresh-Tokens widerrufen). Laufende Access-Tokens
    laufen nach wenigen Minuten ab; bei deaktivierten Nutzern greift zusaetzlich deps.get_current_user."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    """Eigenes Passwort aendern. Andere Geraete werden dabei abgemeldet."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das bisherige Passwort stimmt nicht")
    user.password_hash = hash_password(payload.new_password)
    await revoke_refresh_tokens(db, user.id)
    await db.commit()
