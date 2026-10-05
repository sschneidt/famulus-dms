"""Benachrichtigungen: taegliche Zusammenfassung erstellen und verschicken (Anforderungsdokument 4.5).

Ablauf (tasks/notifications.py, alle 15 Minuten):
1. Fuer jede Person, deren Uhrzeit (digest_hour, Ortszeit TZ) heute erreicht ist und die heute noch
   keine Zusammenfassung bekommen hat, wird sie erstellt (create_digest):
   - Eintraege im Benachrichtigungscenter der App (Glocke) - immer
   - je eine wartende Nachricht fuer E-Mail und Push, falls eingeschaltet
   Wer nichts Anstehendes hat, bekommt nichts.
2. Wartende E-Mail/Push-Nachrichten werden verschickt (deliver_pending). Schlaegt der Versand
   fehl (Mailserver/Internet weg), wird es bei den naechsten Laeufen erneut versucht.

Empfaenger eines Termins: die zustaendige Person, sonst der Eigentuemer des Dokuments, sonst
(z. B. Scan-Ordner-Dokumente ohne Eigentuemer) alle Admins - jeweils nur, wenn sie das Dokument
sehen duerfen.
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.config import get_settings
from homedms.core import mailer, webpush
from homedms.core.reminders import Digest, ReminderItem, should_remind, stage_for
from homedms.core.visibility import visible_documents_expr
from homedms.i18n import _, use_language
from homedms.models.document import ClassificationStatus, Document, DocumentSource
from homedms.models.ops import Notification, PushSubscription
from homedms.models.tenant import Tenant, User, UserRole
from homedms.models.wiedervorlage import Wiedervorlage

logger = logging.getLogger("homedms.notifications")

MAX_ATTEMPTS = 6           # bei Fehlern: noch 5 weitere Versuche im 15-Minuten-Takt
GIVE_UP_AFTER = timedelta(days=2)
KEEP_IN_APP_DAYS = 60


def channels(user: User) -> dict:
    c = user.notification_channels or {}
    return {"in_app": True, "email": bool(c.get("email", True)), "push": bool(c.get("push", False))}


def local_now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    try:
        return now.astimezone(ZoneInfo(get_settings().tz))
    except Exception:  # noqa: BLE001 - unbekannte Zeitzone: lieber UTC als gar keine Erinnerung
        return now.astimezone(timezone.utc)


def is_due(user: User, local: datetime) -> bool:
    return local.hour >= (user.digest_hour or 0) and user.last_digest_on != local.date()


def _recipient_condition(user: User):
    recipient = func.coalesce(Wiedervorlage.assigned_user_id, Document.owner_user_id)
    is_admin = true() if user.role == UserRole.admin else false()
    return and_(or_(recipient == user.id, and_(recipient.is_(None), is_admin)), visible_documents_expr(user))


def _own_documents(user: User):
    is_admin = true() if user.role == UserRole.admin else false()
    return or_(Document.owner_user_id == user.id, and_(Document.owner_user_id.is_(None), is_admin))


async def collect(db: AsyncSession, user: User, today: date, since: datetime) -> tuple[Digest, list[tuple[Wiedervorlage, int]]]:
    """Was steht fuer diese Person an? Liefert die Zusammenfassung und die zu markierenden Termine."""
    digest = Digest()
    marks: list[tuple[Wiedervorlage, int]] = []
    rows = (await db.execute(
        select(Wiedervorlage, Document.title)
        .join(Document, Document.id == Wiedervorlage.document_id)
        .where(Wiedervorlage.tenant_id == user.tenant_id, Wiedervorlage.status == "offen",
               Document.deleted_at.is_(None), _recipient_condition(user))
        .order_by(Wiedervorlage.due_date)
    )).all()
    for wv, title in rows:
        days_left = (wv.due_date - today).days
        stage = stage_for(days_left, wv.reminder_lead_days)
        if should_remind(stage, wv.reminder_stage or 0, wv.reminded_on, today):
            digest.items.append(ReminderItem(str(wv.id), str(wv.document_id), title or "", wv.note or "",
                                             wv.due_date, days_left, stage))
            marks.append((wv, stage))

    proposals = (
        select(func.count(), func.count().filter(Wiedervorlage.created_at > since))
        .select_from(Wiedervorlage).join(Document, Document.id == Wiedervorlage.document_id)
        .where(Wiedervorlage.tenant_id == user.tenant_id, Wiedervorlage.status == "vorgeschlagen",
               Document.deleted_at.is_(None), _recipient_condition(user))
    )
    digest.open_proposals, digest.new_proposals = (await db.execute(proposals)).one()

    review = (
        select(func.count(), func.count().filter(Document.updated_at > since))
        .where(Document.tenant_id == user.tenant_id, Document.deleted_at.is_(None),
               Document.classification_status == ClassificationStatus.needs_review,
               _own_documents(user), visible_documents_expr(user))
    )
    digest.open_review, digest.new_review = (await db.execute(review)).one()

    if user.role == UserRole.admin:
        digest.new_imports = await db.scalar(
            select(func.count()).where(
                Document.tenant_id == user.tenant_id, Document.deleted_at.is_(None),
                Document.source == DocumentSource.nas_scan_folder, Document.owner_user_id.is_(None),
                Document.created_at > since)
        ) or 0
    return digest, marks


def _in_app(user: User, digest: Digest) -> list[Notification]:
    rows = [
        Notification(tenant_id=user.tenant_id, user_id=user.id, type="wiedervorlage_due", channel="in_app",
                     status="unread", payload={
                         "wiedervorlage_id": i.wiedervorlage_id, "document_id": i.document_id,
                         "document_title": i.document_title, "note": i.note,
                         "due_date": i.due_date.isoformat(), "days_left": i.days_left, "stage": i.stage})
        for i in digest.items
    ]
    if digest.new_proposals:
        rows.append(Notification(tenant_id=user.tenant_id, user_id=user.id, type="wiedervorlage_vorschlag",
                                 channel="in_app", status="unread",
                                 payload={"count": digest.new_proposals, "total": digest.open_proposals}))
    if digest.new_review:
        rows.append(Notification(tenant_id=user.tenant_id, user_id=user.id, type="needs_review",
                                 channel="in_app", status="unread",
                                 payload={"count": digest.new_review, "total": digest.open_review}))
    if digest.new_imports:
        rows.append(Notification(tenant_id=user.tenant_id, user_id=user.id, type="new_document",
                                 channel="in_app", status="unread", payload={"count": digest.new_imports}))
    return rows


async def create_digest(db: AsyncSession, user: User, tenant: Tenant, now: datetime | None = None) -> Digest:
    """Zusammenfassung fuer eine Person erstellen (ohne zu verschicken) und als erledigt markieren."""
    now = now or datetime.now(timezone.utc)
    local = local_now(now)
    since = user.last_digest_at or (now - timedelta(days=1))
    digest, marks = await collect(db, user, local.date(), since)
    with use_language(user.locale):  # E-Mail und Push in der Sprache der Person
        await _queue(db, user, tenant, digest)
    for wv, stage in marks:
        wv.reminder_stage = stage
        wv.reminded_on = local.date()
    user.last_digest_on = local.date()
    user.last_digest_at = now
    await db.commit()
    return digest


async def _queue(db: AsyncSession, user: User, tenant: Tenant, digest: Digest) -> None:
    """App-Eintraege anlegen und E-Mail/Push zum Versand vormerken (Texte fertig in der Sprache der Person)."""
    if not digest.is_empty:
        db.add_all(_in_app(user, digest))
        wanted = channels(user)
        mail = tenant.mail_settings or {}
        if wanted["email"] and mailer.is_configured(mail):
            app_url = (mail.get("app_url") or "").rstrip("/")
            db.add(Notification(tenant_id=user.tenant_id, user_id=user.id, type="digest", channel="email",
                                status="pending", payload={"subject": digest.subject(),
                                                           "text": digest.text(app_url), "html": digest.html(app_url)}))
        has_device = wanted["push"] and await db.scalar(
            select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id))
        if has_device:
            db.add(Notification(tenant_id=user.tenant_id, user_id=user.id, type="digest", channel="push",
                                status="pending", payload={"message": digest.push()}))


async def run_digests(db: AsyncSession, now: datetime | None = None) -> int:
    """Alle faelligen Zusammenfassungen erstellen. Rueckgabe: Anzahl nicht-leerer."""
    now = now or datetime.now(timezone.utc)
    local = local_now(now)
    users = (await db.execute(
        select(User).where(User.is_active.is_(True), User.digest_hour <= local.hour,
                           or_(User.last_digest_on.is_(None), User.last_digest_on != local.date()))
    )).scalars().all()
    created = 0
    for user in users:
        tenant = await db.get(Tenant, user.tenant_id)
        try:
            digest = await create_digest(db, user, tenant, now)
            created += not digest.is_empty
        except Exception:  # noqa: BLE001 - eine Person darf die anderen nicht blockieren
            await db.rollback()
            logger.exception("Zusammenfassung fuer %s fehlgeschlagen", user.email)
    return created


# --- Versand -------------------------------------------------------------------------------------

def push_subject(user: User) -> str:
    """VAPID-Kontakt: Apple verlangt eine echte mailto:-Adresse."""
    return f"mailto:{user.email}"


async def send_email(db: AsyncSession, user: User, subject: str, text: str, html: str | None) -> None:
    tenant = await db.get(Tenant, user.tenant_id)
    settings = tenant.mail_settings or {}
    try:
        await mailer.send(settings, user.email, subject, text, html)
    except mailer.MailError as exc:
        tenant.mail_settings = {**settings, "last_error": str(exc), "last_error_at": _now_iso()}
        raise
    tenant.mail_settings = {**settings, "last_error": None, "last_ok_at": _now_iso()}


async def send_push(db: AsyncSession, user: User, message: dict) -> int:
    """An alle Geraete der Person. Rueckgabe: erfolgreich erreichte Geraete. Wirft PushError, wenn
    kein Geraet erreicht wurde, aber es welche gibt."""
    subs = (await db.execute(select(PushSubscription).where(PushSubscription.user_id == user.id))).scalars().all()
    if not subs:
        raise webpush.PushError(_("Auf keinem Gerät ist Push eingeschaltet"))
    vapid = await webpush.get_vapid(db)
    ok, errors = 0, []
    for sub in subs:
        try:
            await webpush.send(vapid, sub.endpoint, sub.keys, message, push_subject(user))
        except webpush.PushGone:
            await db.delete(sub)
            continue
        except (webpush.PushError, ValueError) as exc:
            sub.last_error = str(exc)
            errors.append(str(exc))
            continue
        sub.last_success_at = datetime.now(timezone.utc)
        sub.last_error = None
        ok += 1
    if not ok:
        raise webpush.PushError(errors[0] if errors else _("Push wurde auf allen Geräten abbestellt"))
    return ok


async def deliver(db: AsyncSession, note: Notification) -> None:
    user = await db.get(User, note.user_id)
    with use_language(user.locale):  # Fehlermeldungen in der Sprache der Person
        await _deliver(db, user, note)


async def _deliver(db: AsyncSession, user: User, note: Notification) -> None:
    note.attempts = (note.attempts or 0) + 1
    try:
        if note.channel == "email":
            p = note.payload
            await send_email(db, user, p["subject"], p["text"], p.get("html"))
        else:
            await send_push(db, user, note.payload["message"])
    except (mailer.MailError, webpush.PushError) as exc:
        note.error = str(exc)
        too_old = note.created_at and datetime.now(timezone.utc) - note.created_at > GIVE_UP_AFTER
        if note.attempts >= MAX_ATTEMPTS or too_old:
            note.status = "failed"
        logger.warning("%s an %s fehlgeschlagen (Versuch %d): %s", note.channel, user.email, note.attempts, exc)
    else:
        note.status, note.sent_at, note.error = "sent", datetime.now(timezone.utc), None
    await db.commit()


async def deliver_pending(db: AsyncSession) -> int:
    ids = (await db.execute(
        select(Notification.id).where(Notification.status == "pending", Notification.channel.in_(("email", "push")))
        .order_by(Notification.created_at)
    )).scalars().all()
    for note_id in ids:
        note = await db.get(Notification, note_id)
        if note is not None and note.status == "pending":
            await deliver(db, note)
    return len(ids)


async def cleanup(db: AsyncSession) -> None:
    """Gelesene App-Benachrichtigungen und alte Versand-Protokolle nach 60 Tagen entfernen."""
    limit = datetime.now(timezone.utc) - timedelta(days=KEEP_IN_APP_DAYS)
    await db.execute(delete(Notification).where(Notification.created_at < limit, Notification.status != "unread"))
    await db.commit()


async def last_delivery(db: AsyncSession, tenant_id: uuid.UUID, channel: str) -> Notification | None:
    return await db.scalar(
        select(Notification).where(Notification.tenant_id == tenant_id, Notification.channel == channel,
                                   Notification.status.in_(("sent", "failed", "pending")))
        .order_by(Notification.created_at.desc()).limit(1)
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
