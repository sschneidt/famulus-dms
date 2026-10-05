"""E-Mail-Versand ueber das Postfach des Haushalts (SMTP) - Anforderungsdokument 4.5.

Die Zugangsdaten traegt der Admin in der App ein (Seite "Benutzer" > "E-Mail-Versand"). Das
Passwort liegt verschluesselt in der Datenbank (Schluessel abgeleitet aus JWT_SECRET) - ein
Datenbank-Backup allein verraet es also nicht. Wird JWT_SECRET geaendert, muss das Passwort neu
eingegeben werden; die Diagnose-Seite sagt das.
"""
import asyncio
import base64
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from homedms.config import get_settings
from homedms.i18n import _

SECURITY_MODES = ("starttls", "ssl", "none")
TIMEOUT_SECONDS = 20


class MailError(Exception):
    """Fehler beim Versand - Text ist fuer Menschen gedacht (Anzeige in der App)."""


def _fernet() -> Fernet:
    secret = get_settings().jwt_secret.encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"homedms-mail", info=b"smtp-password").derive(secret)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_password(password: str) -> str:
    return _fernet().encrypt(password.encode()).decode()


def decrypt_password(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise MailError(_("Das gespeicherte Passwort lässt sich nicht mehr entschlüsseln "
                          "(JWT_SECRET geändert?) - bitte neu eingeben.")) from exc


def is_configured(settings: dict | None) -> bool:
    return bool(settings and settings.get("host") and settings.get("sender"))


def build_message(settings: dict, to: str, subject: str, text: str, html: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("HomeDMS", settings["sender"]))
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain=settings["sender"].rpartition("@")[2] or "homedms")
    msg["Auto-Submitted"] = "auto-generated"  # keine Abwesenheitsnotizen zurueck
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _send_sync(settings: dict, msg: EmailMessage) -> None:
    host, port = settings["host"], int(settings.get("port") or 587)
    security = settings.get("security") or "starttls"
    context = ssl.create_default_context()
    try:
        if security == "ssl":
            client = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SECONDS, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS)
        with client:
            client.ehlo()
            if security == "starttls":
                client.starttls(context=context)
                client.ehlo()
            if settings.get("username"):
                password = decrypt_password(settings["password"]) if settings.get("password") else ""
                client.login(settings["username"], password)
            client.send_message(msg)
    except MailError:
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(_("Anmeldung am Mailserver abgelehnt - Benutzername/Passwort prüfen (bei Gmail, GMX "
                          "u. a. ein App-Passwort verwenden).")) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError(_("Empfänger abgelehnt: {recipients}", recipients=", ".join(exc.recipients))) from exc
    except smtplib.SMTPSenderRefused as exc:
        raise MailError(_("Absender {sender} abgelehnt - muss meist zum Postfach passen.", sender=exc.sender)) from exc
    except ssl.SSLError as exc:
        raise MailError(_("Verschlüsselung fehlgeschlagen ({reason}) - passt die Einstellung "
                          "„Verschlüsselung“ zum Port (587 = STARTTLS, 465 = SSL)?", reason=exc.reason or exc)) from exc
    except (TimeoutError, OSError) as exc:
        raise MailError(_("Mailserver {host}:{port} nicht erreichbar ({error})", host=host, port=port,
                          error=f"{exc.__class__.__name__}: {exc}")) from exc
    except smtplib.SMTPException as exc:
        raise MailError(_("Mailserver meldet: {error}", error=exc)) from exc


async def send(settings: dict, to: str, subject: str, text: str, html: str | None = None) -> None:
    if not is_configured(settings):
        raise MailError(_("E-Mail-Versand ist nicht eingerichtet"))
    msg = build_message(settings, to, subject, text, html)
    await asyncio.to_thread(_send_sync, settings, msg)
