"""Schutz gegen Passwort-Raten.

- Je Konto: Ab LOGIN_MAX_FAILURES Fehlversuchen in Folge ist die Anmeldung gesperrt - 1 Minute,
  bei jedem weiteren Fehlversuch doppelt so lange (hoechstens LOGIN_MAX_LOCK_MINUTES). Waehrend
  der Sperre wird das Passwort gar nicht erst geprueft. Erfolg setzt den Zaehler zurueck.
- Je Adresse (IP): hoechstens IP_MAX_FAILURES Fehlversuche in IP_WINDOW - fuer Versuche mit
  unbekannten E-Mail-Adressen und gegen das Durchprobieren vieler Konten.
- Unbekannte E-Mail kostet genauso lange wie ein falsches Passwort (keine Rueckschluesse ueber
  die Antwortzeit, welche Adressen es gibt).
"""
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from homedms.config import get_settings
from homedms.core.security import hash_password, verify_password
from homedms.models.tenant import User

IP_MAX_FAILURES = 20
IP_WINDOW = 15 * 60  # Sekunden

_ip_failures: dict[str, deque] = defaultdict(deque)
_dummy_hash: str | None = None


def _wait_text(until: datetime) -> str:
    seconds = max(1, int((until - datetime.now(timezone.utc)).total_seconds()))
    return f"{seconds} Sekunden" if seconds < 90 else f"{(seconds + 59) // 60} Minuten"


def check_ip(ip: str) -> None:
    attempts = _ip_failures[ip]
    now = time.monotonic()
    while attempts and attempts[0] < now - IP_WINDOW:
        attempts.popleft()
    if len(attempts) >= IP_MAX_FAILURES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Zu viele Fehlversuche von diesem Gerät - bitte in einigen Minuten erneut versuchen")


def record_ip_failure(ip: str) -> None:
    _ip_failures[ip].append(time.monotonic())


def reset_ip(ip: str) -> None:
    _ip_failures.pop(ip, None)


def check_locked(user: User) -> None:
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Zu viele Fehlversuche - Anmeldung in {_wait_text(user.locked_until)} wieder möglich")


def record_failure(user: User) -> None:
    settings = get_settings()
    user.failed_logins = (user.failed_logins or 0) + 1
    over = user.failed_logins - settings.login_max_failures
    if over >= 0:
        minutes = min(2 ** over, settings.login_max_lock_minutes)
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)


def record_success(user: User) -> None:
    user.failed_logins = 0
    user.locked_until = None


def burn_time(password: str) -> None:
    """Gleich teure Pruefung fuer unbekannte Konten."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("homedms-gibt-es-nicht")
    verify_password(password, _dummy_hash)
