"""Anmeldung, Sitzungen und Zwei-Faktor - docs/API-Design.md Abschnitt 2, Sicherheitskonzept.

Ablauf:
- POST /auth/login: E-Mail + Passwort. Mit Zwei-Faktor kommt zuerst nur eine "challenge",
  danach POST /auth/login/2fa mit dem Code aus der App (oder einem Wiederherstellungscode).
- Zugang: kurzlebiges Access-Token (15 Min.) + Refresh-Token. Die Weboberflaeche (Kopfzeile
  X-HomeDMS-Session: cookie) bekommt das Refresh-Token nur als HttpOnly-Cookie - fuer Skripte im
  Seitenquelltext nicht lesbar. Andere Clients bekommen es im Antworttext.
- Sitzung = eine Anmeldung auf einem Geraet. Bei jeder Erneuerung entsteht ein neues Refresh-Token
  derselben Sitzung; das alte wird "rotiert". Taucht ein rotiertes Token spaeter nochmal auf, wurde
  es kopiert -> die ganze Sitzung wird beendet. Beendete Sitzungen sperren sofort (api/deps.py).
- Anmeldeschutz (Sperrzeit nach Fehlversuchen): core/login_guard.py.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.i18n import _, _n
from homedms.api.deps import get_current_user
from homedms.config import get_settings
from homedms.core import login_guard, totp
from homedms.core.security import (
    create_access_token,
    create_challenge_token,
    decode_token,
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
    PasswordConfirm,
    ProfileUpdate,
    RecoveryCodes,
    RefreshRequest,
    SessionInfo,
    TokenResponse,
    TwoFactorCode,
    TwoFactorLogin,
    TwoFactorSetup,
    TwoFactorStatus,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

REFRESH_COOKIE = "homedms_refresh"
COOKIE_PATH = "/api/v1/auth"
ROTATION_GRACE = timedelta(seconds=60)  # zwei Tabs erneuern gleichzeitig - kein Diebstahl


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _cookie_mode(request: Request) -> bool:
    return request.headers.get("x-homedms-session") == "cookie" or REFRESH_COOKIE in request.cookies


def _set_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=settings.jwt_refresh_token_ttl_days * 86400, path=COOKIE_PATH,
        httponly=True, samesite="strict", secure=request.url.scheme == "https",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, httponly=True, samesite="strict")


async def _issue_tokens(
    user: User, db: AsyncSession, request: Request, response: Response,
    session_id: uuid.UUID | None = None, started: datetime | None = None, notice: str | None = None,
) -> TokenResponse:
    now = datetime.now(timezone.utc)
    session_id = session_id or uuid.uuid4()
    refresh_plain = new_refresh_token_plaintext()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_plain),
        expires_at=now + timedelta(days=settings.jwt_refresh_token_ttl_days),
        session_id=session_id,
        session_started_at=started or now,
        last_used_at=now,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        ip=client_ip(request)[:64],
    ))
    await db.commit()
    access = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role.value, session_id=session_id)
    if _cookie_mode(request):
        _set_cookie(request, response, refresh_plain)
        return TokenResponse(access_token=access, notice=notice)
    return TokenResponse(access_token=access, refresh_token=refresh_plain, notice=notice)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


async def _failed(db: AsyncSession, user: User, ip: str, detail: str) -> HTTPException:
    login_guard.record_failure(user)
    login_guard.record_ip_failure(ip)
    await db.commit()
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        minutes = round((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) or 1
        detail += f" - zu viele Fehlversuche, Anmeldung erst in {minutes} Minute(n) wieder möglich"
    return _unauthorized(detail)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    ip = client_ip(request)
    login_guard.check_ip(ip)
    # Gross-/Kleinschreibung der E-Mail egal (beim Anlegen wird sie ebenso verglichen, routes/users.py)
    user = (await db.execute(select(User).where(func.lower(User.email) == payload.email.lower()))).scalars().first()
    if user is None:
        login_guard.burn_time(payload.password)
        login_guard.record_ip_failure(ip)
        raise _unauthorized(_("E-Mail oder Passwort falsch"))
    login_guard.check_locked(user)
    if not verify_password(payload.password, user.password_hash):
        raise await _failed(db, user, ip, _("E-Mail oder Passwort falsch"))
    if not user.is_active:
        raise _unauthorized(_("Dieses Konto ist deaktiviert - bitte an den Admin wenden"))
    if user.two_factor_enabled:
        return TokenResponse(two_factor_required=True, challenge=create_challenge_token(user.id))
    return await _logged_in(db, user, ip, request, response)


async def _logged_in(db: AsyncSession, user: User, ip: str, request: Request, response: Response,
                     notice: str | None = None) -> TokenResponse:
    login_guard.record_success(user)
    login_guard.reset_ip(ip)
    user.last_login_at = datetime.now(timezone.utc)
    return await _issue_tokens(user, db, request, response, notice=notice)


@router.post("/login/2fa", response_model=TokenResponse)
async def login_two_factor(payload: TwoFactorLogin, request: Request, response: Response,
                           db: AsyncSession = Depends(get_db)) -> TokenResponse:
    ip = client_ip(request)
    login_guard.check_ip(ip)
    try:
        claims = decode_token(payload.challenge)
    except jwt.InvalidTokenError:
        raise _unauthorized(_("Die Anmeldung ist abgelaufen - bitte noch einmal mit dem Passwort beginnen"))
    if claims.get("type") != "2fa":
        raise _unauthorized(_("Ungültige Anmeldung"))
    user = await db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active or not user.two_factor_enabled:
        raise _unauthorized(_("Ungültige Anmeldung"))
    login_guard.check_locked(user)

    step = totp.verify(user.totp_secret, payload.code, user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        return await _logged_in(db, user, ip, request, response)
    remaining = totp.use_recovery_code(user.recovery_codes, payload.code)
    if remaining is not None:
        user.recovery_codes = remaining
        notice = _n("Wiederherstellungscode benutzt - noch {count} übrig.", "Wiederherstellungscode benutzt - noch {count} übrig.", len(remaining))
        return await _logged_in(db, user, ip, request, response, notice)
    raise await _failed(db, user, ip, _("Der Code stimmt nicht"))


def _token_from(request: Request, payload: RefreshRequest | None) -> str | None:
    return request.cookies.get(REFRESH_COOKIE) or (payload.refresh_token if payload else None)


async def _end_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID | None = None) -> None:
    query = update(RefreshToken).where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
    if user_id is not None:
        query = query.where(RefreshToken.user_id == user_id)
    await db.execute(query.values(revoked_at=datetime.now(timezone.utc)))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, payload: RefreshRequest | None = None,
                  db: AsyncSession = Depends(get_db)) -> TokenResponse:
    token = _token_from(request, payload)
    stored = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    )).scalar_one_or_none() if token else None
    now = datetime.now(timezone.utc)
    if stored is None or stored.revoked_at is not None or stored.expires_at < now:
        _clear_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _("Anmeldung abgelaufen"), headers=_clear_headers(response))
    if stored.rotated_at is not None and stored.rotated_at < now - ROTATION_GRACE:
        # Ein laengst ersetztes Token taucht wieder auf -> es wurde kopiert. Ganze Sitzung beenden.
        await _end_session(db, stored.session_id)
        await db.commit()
        _clear_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _("Sitzung aus Sicherheitsgründen beendet - bitte neu anmelden"),
                            headers=_clear_headers(response))
    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        _clear_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _("Nutzer nicht gefunden oder deaktiviert"), headers=_clear_headers(response))
    stored.rotated_at = stored.rotated_at or now
    return await _issue_tokens(user, db, request, response, stored.session_id, stored.session_started_at)


def _clear_headers(response: Response) -> dict[str, str]:
    """Set-Cookie auch bei Fehlerantworten mitschicken (HTTPException ersetzt die Antwort)."""
    cookie = response.headers.get("set-cookie")
    return {"set-cookie": cookie} if cookie else {}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, payload: RefreshRequest | None = None,
                 db: AsyncSession = Depends(get_db)) -> None:
    token = _token_from(request, payload)
    if token:
        stored = (await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
        )).scalar_one_or_none()
        if stored is not None:
            await _end_session(db, stored.session_id)
            await db.commit()
    _clear_cookie(response)


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
        two_factor_enabled=user.two_factor_enabled,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeResponse:
    return await _me(user, db)


@router.patch("/me", response_model=MeResponse)
async def update_me(
    payload: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    """Eigenen Anzeigenamen bzw. die eigene Sprache aendern (E-Mail und Rolle aendert nur ein Admin)."""
    if payload.display_name is not None:
        name = payload.display_name.strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Bitte einen Namen angeben"))
        user.display_name = name
    if payload.locale is not None:
        user.locale = payload.locale
    await db.commit()
    if payload.locale is not None:  # Texterkennung folgt der Oberflaechensprache - Paket ggf. nachladen
        from homedms.core import ocr_languages

        try:
            await ocr_languages.request_installs(db, await ocr_languages.missing(db, user.tenant_id))
        except Exception as exc:  # noqa: BLE001 - Sprache ist gespeichert, das Paket kommt spaeter
            logging.getLogger("homedms.auth").warning("Sprachpaket nicht angefordert: %s", exc)
    return await _me(user, db)


async def revoke_refresh_tokens(db: AsyncSession, user_id, except_session: uuid.UUID | None = None) -> None:
    """Alle Anmeldungen eines Nutzers beenden - wirkt sofort, auch fuer laufende Access-Tokens
    (api/deps.py prueft die Sitzung bei jeder Anfrage)."""
    query = update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    if except_session is not None:
        query = query.where(RefreshToken.session_id != except_session)
    await db.execute(query.values(revoked_at=datetime.now(timezone.utc)))


async def _confirm_password(db: AsyncSession, user: User, password: str, request: Request) -> None:
    login_guard.check_locked(user)
    if not verify_password(password, user.password_hash):
        login_guard.record_failure(user)
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _("Das Passwort stimmt nicht"))


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    """Eigenes Passwort aendern. Alle ANDEREN Geraete werden abgemeldet, dieses bleibt angemeldet."""
    login_guard.check_locked(user)
    if not verify_password(payload.current_password, user.password_hash):
        login_guard.record_failure(user)
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _("Das bisherige Passwort stimmt nicht"))
    user.password_hash = hash_password(payload.new_password)
    await revoke_refresh_tokens(db, user.id, except_session=getattr(request.state, "session_id", None))
    await db.commit()


# --- Angemeldete Geraete ---------------------------------------------------------------------


def device_name(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return _("Unbekanntes Gerät")
    system = next((name for key, name in (
        ("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"), ("windows", "Windows"),
        ("mac os", "Mac"), ("cros", "ChromeOS"), ("linux", "Linux"),
    ) if key in ua), None)
    browser = next((name for key, name in (
        ("edg/", "Edge"), ("samsungbrowser", "Samsung Internet"), ("firefox", "Firefox"), ("fxios", "Firefox"),
        ("crios", "Chrome"), ("chrome", "Chrome"), ("safari", "Safari"), ("python", _("Skript")),
        ("powershell", "PowerShell"), ("curl", "curl"),
    ) if key in ua), None)
    if browser and system:
        return _("{browser} auf {system}", browser=browser, system=system)
    return browser or system or _("Unbekanntes Gerät")


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[SessionInfo]:
    now = datetime.now(timezone.utc)
    tokens = (await db.execute(
        select(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > now)
        .order_by(RefreshToken.last_used_at.desc().nulls_last())
    )).scalars().all()
    current = getattr(request.state, "session_id", None)
    sessions: dict[uuid.UUID, SessionInfo] = {}
    for t in tokens:
        if t.session_id in sessions:
            continue
        sessions[t.session_id] = SessionInfo(
            id=t.session_id, device=device_name(t.user_agent), ip=t.ip,
            started_at=t.session_started_at or t.created_at, last_used_at=t.last_used_at, current=t.session_id == current,
        )
    return sorted(sessions.values(), key=lambda s: (not s.current, -(s.last_used_at or now).timestamp()))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await _end_session(db, session_id, user.id)
    await db.commit()


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def end_other_sessions(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    """Ueberall sonst abmelden."""
    await revoke_refresh_tokens(db, user.id, except_session=getattr(request.state, "session_id", None))
    await db.commit()


# --- Zwei-Faktor -------------------------------------------------------------------------------


@router.get("/2fa", response_model=TwoFactorStatus)
async def two_factor_status(user: User = Depends(get_current_user)) -> TwoFactorStatus:
    return TwoFactorStatus(enabled=user.two_factor_enabled, recovery_codes_left=len(user.recovery_codes or []))


@router.post("/2fa/setup", response_model=TwoFactorSetup)
async def two_factor_setup(payload: PasswordConfirm, request: Request, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)) -> TwoFactorSetup:
    """Schritt 1: Geheimnis erzeugen und als QR-Code zeigen - aktiv erst nach /2fa/enable."""
    await _confirm_password(db, user, payload.password, request)
    secret = totp.new_secret()
    user.totp_pending_secret = secret
    await db.commit()
    uri = totp.provisioning_uri(secret, user.email)
    return TwoFactorSetup(secret=secret, uri=uri, qr_svg=totp.qr_svg(uri))


@router.post("/2fa/enable", response_model=RecoveryCodes)
async def two_factor_enable(payload: TwoFactorCode, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)) -> RecoveryCodes:
    """Schritt 2: ersten Code aus der App bestaetigen -> aktiv; Wiederherstellungscodes einmal anzeigen."""
    if not user.totp_pending_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Bitte die Einrichtung neu beginnen"))
    step = totp.verify(user.totp_pending_secret, payload.code, None)
    if step is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _("Der Code stimmt nicht - Uhrzeit des Handys prüfen und den aktuellen Code eingeben"))
    codes, hashes = totp.new_recovery_codes()
    user.totp_secret, user.totp_pending_secret, user.totp_last_step = user.totp_pending_secret, None, step
    user.recovery_codes = hashes
    await db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def two_factor_disable(payload: PasswordConfirm, request: Request, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)) -> None:
    await _confirm_password(db, user, payload.password, request)
    clear_two_factor(user)
    await db.commit()


@router.post("/2fa/recovery-codes", response_model=RecoveryCodes)
async def new_recovery_codes(payload: PasswordConfirm, request: Request, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)) -> RecoveryCodes:
    await _confirm_password(db, user, payload.password, request)
    if not user.two_factor_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, _("Zwei-Faktor-Anmeldung ist nicht eingeschaltet"))
    codes, hashes = totp.new_recovery_codes()
    user.recovery_codes = hashes
    await db.commit()
    return RecoveryCodes(recovery_codes=codes)


def clear_two_factor(user: User) -> None:
    user.totp_secret = user.totp_pending_secret = None
    user.totp_last_step = None
    user.recovery_codes = None
