"""Haushaltsmitglieder verwalten - docs/API-Design.md Abschnitt 3.

Nur der Admin legt Mitglieder an, aendert Rollen, setzt Passwoerter zurueck und deaktiviert
Konten. Geloescht wird nie: Dokumente, Termine und Verlauf eines Mitglieds bleiben erhalten.
Es bleibt immer mindestens ein aktiver Admin, und niemand sperrt sich selbst aus.

E-Mail-Adressen sind in der ganzen Installation eindeutig (Gross-/Kleinschreibung egal), weil
die Anmeldung nur ueber E-Mail + Passwort laeuft - ohne Angabe des Haushalts.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.api.deps import get_current_user, require_admin
from homedms.api.routes.auth import clear_two_factor, revoke_refresh_tokens
from homedms.core.security import hash_password
from homedms.db import get_db
from homedms.models.tenant import User, UserRole
from homedms.schemas.user import PasswordReset, UserCreate, UserResponse, UserUpdate
from homedms.i18n import _

router = APIRouter(prefix="/users", tags=["users"])


async def _member(db: AsyncSession, admin: User, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != admin.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Nutzer nicht gefunden"))
    return user


async def _active_admins(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count()).select_from(User).where(
            User.tenant_id == tenant_id, User.role == UserRole.admin, User.is_active.is_(True)
        )
    ) or 0


@router.get("", response_model=list[UserResponse])
async def list_users(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[User]:
    """Alle Mitglieder des eigenen Haushalts (z. B. fuer "Termin zuweisen an")."""
    result = await db.execute(
        select(User).where(User.tenant_id == user.tenant_id).order_by(User.is_active.desc(), func.lower(User.display_name))
    )
    return list(result.scalars().all())


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> User:
    email = str(payload.email).strip()
    taken = await db.scalar(select(func.count()).select_from(User).where(func.lower(User.email) == email.lower()))
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Diese E-Mail-Adresse wird schon verwendet"))
    user = User(
        tenant_id=admin.tenant_id,
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role=UserRole(payload.role),
        locale=admin.locale,
        notification_channels={"in_app": True, "email": True, "push": False},
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> User:
    user = await _member(db, admin, user_id)
    if payload.display_name is not None:
        name = payload.display_name.strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Bitte einen Namen angeben"))
        user.display_name = name

    demote = payload.role == "member" and user.role == UserRole.admin
    deactivate = payload.is_active is False and user.is_active
    if (demote or deactivate) and user.id == admin.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, _("Die eigene Admin-Rolle bzw. das eigene Konto kann nur ein anderer Admin aendern")
        )
    if (demote or deactivate) and user.role == UserRole.admin and user.is_active:
        if await _active_admins(db, admin.tenant_id) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, _("Es muss mindestens ein aktiver Admin bleiben"))

    if payload.role is not None:
        user.role = UserRole(payload.role)
    if payload.reset_two_factor:
        if user.id == admin.id:
            raise HTTPException(status.HTTP_409_CONFLICT, _("Die eigene Zwei-Faktor-Anmeldung unter „Konto & Sicherheit“ ändern"))
        clear_two_factor(user)
        await revoke_refresh_tokens(db, user.id)
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            await revoke_refresh_tokens(db, user.id)  # sofort ueberall abmelden
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID, payload: PasswordReset, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> None:
    """Passwort eines Mitglieds neu setzen (z. B. vergessen). Das Mitglied wird ueberall abgemeldet."""
    user = await _member(db, admin, user_id)
    user.password_hash = hash_password(payload.password)
    user.failed_logins, user.locked_until = 0, None  # Sperre nach Fehlversuchen aufheben
    await revoke_refresh_tokens(db, user.id)
    await db.commit()
