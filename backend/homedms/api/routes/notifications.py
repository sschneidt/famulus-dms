"""Benachrichtigungen - docs/API-Design.md Abschnitt 9 (Anforderungsdokument 4.5).

- Benachrichtigungscenter (Glocke): eigene Eintraege lesen, als gelesen markieren
- eigene Einstellungen: E-Mail/Push an/aus, Uhrzeit der taeglichen Zusammenfassung, Testnachricht
- Push-Abos der eigenen Geraete
- E-Mail-Versand des Haushalts (nur Admin): SMTP-Zugang, Testmail
"""
import uuid
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.i18n import _, _n
from homedms.api.deps import get_current_user, require_admin
from homedms.api.routes.auth import device_name
from homedms.config import get_settings
from homedms.core import mailer, notifications, webpush
from homedms.core.reminders import ReminderItem, note_label, when
from homedms.db import get_db
from homedms.models.ops import Notification, PushSubscription
from homedms.models.tenant import Tenant, User
from homedms.schemas.notification import (
    MailSettings,
    MailSettingsUpdate,
    NotificationItem,
    NotificationList,
    NotificationSettings,
    NotificationSettingsUpdate,
    PushDevice,
    PushSubscriptionCreate,
    TestRequest,
    TestResult,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])
mail_router = APIRouter(prefix="/tenant/mail", tags=["notifications"])

# Nur an die bekannten Push-Dienste der Browser senden - nie an beliebige Adressen im Netz
PUSH_HOST_SUFFIXES = (".googleapis.com", ".push.apple.com", ".push.services.mozilla.com", ".notify.windows.com")
MAX_DEVICES = 10


def today() -> date:
    return notifications.local_now().date()


def render(note: Notification) -> NotificationItem:
    p = note.payload or {}
    if note.type == "wiedervorlage_due":
        due = date.fromisoformat(p["due_date"])
        item = ReminderItem(p.get("wiedervorlage_id", ""), p.get("document_id", ""), p.get("document_title", ""),
                            p.get("note", ""), due, (due - today()).days, p.get("stage", 0))
        title, url = note_label(item.note), f"/dokumente/{item.document_id}"
        body = f"{item.document_title or _('Dokument')}: {when(item)}"
    elif note.type == "wiedervorlage_vorschlag":
        n = p.get("count", 0)
        title = _n("Neuer Fristvorschlag", "Neue Fristvorschläge", n)
        body, url = _n("Die KI hat {count} Frist erkannt – bitte bestätigen.",
                       "Die KI hat {count} Fristen erkannt – bitte bestätigen.", n), "/termine"
    elif note.type == "needs_review":
        n = p.get("count", 0)
        title, url = _("Kategorie prüfen"), "/pruefen"
        body = _n("{count} neues Dokument wartet auf eine Einordnung.", "{count} neue Dokumente warten auf eine Einordnung.", n)
    elif note.type == "new_document":
        n = p.get("count", 0)
        title, url = _("Neue Dokumente"), "/"
        body = _n("{count} Dokument ist über den Scan-Ordner eingegangen.",
                  "{count} Dokumente sind über den Scan-Ordner eingegangen.", n)
    else:
        title, body, url = p.get("title", "HomeDMS"), p.get("body", ""), p.get("url", "/")
    return NotificationItem(id=note.id, type=note.type, title=title, body=body, url=url,
                            read=note.status == "read", created_at=note.created_at)


# --- Benachrichtigungscenter ---------------------------------------------------------------------

@router.get("", response_model=NotificationList)
async def list_notifications(
    limit: int = Query(30, ge=1, le=100), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> NotificationList:
    base = (Notification.user_id == user.id, Notification.channel == "in_app")
    rows = (await db.execute(
        select(Notification).where(*base).order_by(Notification.created_at.desc(), Notification.id).limit(limit)
    )).scalars().all()
    unread = await db.scalar(select(func.count()).where(*base, Notification.status == "unread"))
    return NotificationList(items=[render(n) for n in rows], unread=unread or 0)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    note = await db.get(Notification, notification_id)
    if note is None or note.user_id != user.id or note.channel != "in_app":
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Benachrichtigung nicht gefunden"))
    note.status = "read"
    await db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await db.execute(update(Notification).where(
        Notification.user_id == user.id, Notification.channel == "in_app", Notification.status == "unread"
    ).values(status="read"))
    await db.commit()


# --- eigene Einstellungen ------------------------------------------------------------------------

async def _settings(db: AsyncSession, user: User) -> NotificationSettings:
    tenant = await db.get(Tenant, user.tenant_id)
    subs = (await db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user.id).order_by(PushSubscription.created_at)
    )).scalars().all()
    wanted = notifications.channels(user)
    vapid = await webpush.get_vapid(db)
    return NotificationSettings(
        email=wanted["email"], push=wanted["push"], digest_hour=user.digest_hour, email_address=user.email,
        email_available=mailer.is_configured(tenant.mail_settings), push_public_key=vapid.public_key,
        push_devices=[PushDevice(id=s.id, name=device_name(s.user_agent), endpoint=s.endpoint, created_at=s.created_at,
                                 last_success_at=s.last_success_at, last_error=s.last_error) for s in subs],
        timezone=get_settings().tz,
    )


@router.get("/settings", response_model=NotificationSettings)
async def get_notification_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> NotificationSettings:
    return await _settings(db, user)


@router.patch("/settings", response_model=NotificationSettings)
async def update_notification_settings(
    payload: NotificationSettingsUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> NotificationSettings:
    wanted = notifications.channels(user)
    if payload.email is not None:
        wanted["email"] = payload.email
    if payload.push is not None:
        wanted["push"] = payload.push
    user.notification_channels = wanted
    if payload.digest_hour is not None:
        user.digest_hour = payload.digest_hour
    await db.commit()
    return await _settings(db, user)


@router.post("/test", response_model=TestResult)
async def send_test(payload: TestRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TestResult:
    """Testnachricht sofort verschicken - zeigt den echten Fehler, falls es nicht klappt."""
    note = Notification(tenant_id=user.tenant_id, user_id=user.id, type="test", channel=payload.channel,
                        status="pending", attempts=1, payload={})
    try:
        if payload.channel == "email":
            await notifications.send_email(
                db, user, _("HomeDMS: Testnachricht"),
                _("Hallo,") + "\n\n" + _("diese Testnachricht zeigt: Der E-Mail-Versand von HomeDMS funktioniert.") + "\n"
                + _("Erinnerungen kommen ab jetzt einmal täglich, wenn etwas ansteht.") + "\n", None)
            message = _("Test-E-Mail an {email} verschickt.", email=user.email)
        else:
            count = await notifications.send_push(db, user, {
                "title": _("HomeDMS: Testnachricht"), "body": _("Push funktioniert auf diesem Gerät."), "url": "/konto",
                "tag": "homedms-test"})
            message = _n("Testnachricht an {count} Gerät geschickt.", "Testnachricht an {count} Geräte geschickt.", count)
    except (mailer.MailError, webpush.PushError) as exc:
        note.status, note.error = "failed", str(exc)
        db.add(note)
        await db.commit()
        return TestResult(ok=False, message=str(exc))
    note.status, note.sent_at = "sent", datetime.now(timezone.utc)
    db.add(note)
    await db.commit()
    return TestResult(ok=True, message=message)


# --- Push-Abos der eigenen Geraete ---------------------------------------------------------------

def _check_endpoint(endpoint: str) -> None:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not any(host.endswith(s) or host == s[1:] for s in PUSH_HOST_SUFFIXES):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Unbekannter Push-Dienst"))


@router.post("/push-subscriptions", response_model=NotificationSettings, status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    payload: PushSubscriptionCreate, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> NotificationSettings:
    """Dieses Geraet fuer Push anmelden (und Push fuer die Person einschalten)."""
    _check_endpoint(payload.endpoint)
    try:
        webpush.encrypt(b"x", payload.keys.p256dh, payload.keys.auth)  # Schluessel brauchbar?
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Ungültige Push-Schlüssel")) from exc
    sub = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if sub is not None and sub.user_id != user.id:
        await db.delete(sub)  # Geraet wechselt die Person (Abmelden/Anmelden im selben Browser)
        await db.flush()
        sub = None
    if sub is None:
        count = await db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id))
        if count >= MAX_DEVICES:
            raise HTTPException(status.HTTP_409_CONFLICT, _("Höchstens {count} Geräte - bitte zuerst eines entfernen", count=MAX_DEVICES))
        sub = PushSubscription(user_id=user.id, endpoint=payload.endpoint)
        db.add(sub)
    sub.keys = payload.keys.model_dump()
    sub.user_agent = (request.headers.get("user-agent") or "")[:300]
    sub.last_error = None
    user.notification_channels = {**notifications.channels(user), "push": True}
    await db.commit()
    return await _settings(db, user)


@router.delete("/push-subscriptions/{subscription_id}", response_model=NotificationSettings)
async def unsubscribe_push(
    subscription_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> NotificationSettings:
    sub = await db.get(PushSubscription, subscription_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _("Gerät nicht gefunden"))
    await db.delete(sub)
    await db.flush()
    left = await db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id))
    if not left:
        user.notification_channels = {**notifications.channels(user), "push": False}
    await db.commit()
    return await _settings(db, user)


# --- E-Mail-Versand des Haushalts (Admin) --------------------------------------------------------

def _mail_view(settings: dict | None) -> MailSettings:
    s = settings or {}
    return MailSettings(
        configured=mailer.is_configured(s), host=s.get("host", ""), port=int(s.get("port") or 587),
        security=s.get("security") or "starttls", username=s.get("username", ""), password_set=bool(s.get("password")),
        sender=s.get("sender", ""), app_url=s.get("app_url", ""), last_ok_at=s.get("last_ok_at"),
        last_error=s.get("last_error"),
    )


@mail_router.get("", response_model=MailSettings)
async def get_mail_settings(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> MailSettings:
    tenant = await db.get(Tenant, user.tenant_id)
    return _mail_view(tenant.mail_settings)


@mail_router.put("", response_model=MailSettings)
async def save_mail_settings(
    payload: MailSettingsUpdate, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
) -> MailSettings:
    app_url = payload.app_url.strip().rstrip("/")
    if app_url and urlsplit(app_url).scheme not in ("http", "https"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _("Adresse der App muss mit https:// beginnen"))
    tenant = await db.get(Tenant, user.tenant_id)
    old = tenant.mail_settings or {}
    if payload.password is None:
        password = old.get("password")
    else:
        password = mailer.encrypt_password(payload.password) if payload.password else None
    tenant.mail_settings = {
        "host": payload.host.strip(), "port": payload.port, "security": payload.security,
        "username": payload.username.strip(), "password": password, "sender": str(payload.sender),
        "app_url": app_url, "last_ok_at": None, "last_error": None,
    }
    await db.commit()
    return _mail_view(tenant.mail_settings)


@mail_router.delete("", response_model=MailSettings)
async def delete_mail_settings(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> MailSettings:
    tenant = await db.get(Tenant, user.tenant_id)
    tenant.mail_settings = None
    await db.commit()
    return _mail_view(None)
