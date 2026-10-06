"""Zwei-Faktor-Anmeldung mit Einmal-Codes aus einer Authenticator-App (TOTP, RFC 6238).

Funktioniert mit jeder ueblichen App (Google/Microsoft Authenticator, Aegis, 2FAS, 1Password ...).
- Einrichten: Geheimnis erzeugen -> QR-Code scannen -> ersten Code eingeben (erst dann aktiv).
- Anmelden: nach dem Passwort ein 6-stelliger Code; jeder Code gilt nur einmal (totp_last_step).
- Wiederherstellungscodes: 10 Stueck, je einmal nutzbar, falls das Handy weg ist. Gespeichert
  werden nur Hashes. Ein Admin kann die Zwei-Faktor-Anmeldung eines Mitglieds zuruecksetzen.
"""
import hashlib
import secrets
import time

import pyotp
import segno

ISSUER = "Famulus DMS"
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
RECOVERY_COUNT = 10
INTERVAL = 30


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    """QR-Code als SVG (dunkel auf transparent) - wird in der Oberflaeche direkt angezeigt."""
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#111", light="#fff")


def verify(secret: str, code: str, last_step: int | None, now: float | None = None) -> int | None:
    """Gueltiger Code -> sein Zeitschritt (zum Merken); sonst None. Erlaubt +-1 Schritt Uhrabweichung,
    aber nie einen schon benutzten oder aelteren Schritt (abgefangene Codes sind wertlos)."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != 6:
        return None
    now = time.time() if now is None else now
    totp = pyotp.TOTP(secret, interval=INTERVAL)
    current = int(now // INTERVAL)
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if secrets.compare_digest(totp.at(step * INTERVAL), code):
            return step
    return None


def _hash(code: str) -> str:
    normalized = "".join(ch for ch in code.lower() if ch.isalnum())
    return hashlib.sha256(normalized.encode()).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """(Codes zum Anzeigen, Hashes zum Speichern) - Format "abcd-efgh"."""
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes, [_hash(c) for c in codes]


def use_recovery_code(hashes: list[str] | None, code: str) -> list[str] | None:
    """Passender Code -> verbleibende Hashes (der benutzte ist entfernt); sonst None."""
    if not hashes:
        return None
    wanted = _hash(code)
    for stored in hashes:
        if secrets.compare_digest(stored, wanted):
            return [h for h in hashes if h != stored]
    return None
