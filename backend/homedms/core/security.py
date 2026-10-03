"""Passwort-Hashing (Argon2) + JWT (Datenmodell Abschnitt 4: Access+Refresh, kein OAuth2-Server noetig)."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from homedms.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str, session_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "sid": str(session_id),  # Sitzung - beendete Sitzungen sperren sofort (api/deps.py)
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_challenge_token(user_id: uuid.UUID) -> str:
    """Zwischenschritt der Zwei-Faktor-Anmeldung: Passwort war richtig, Code fehlt noch."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": "2fa", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Wirft jwt.InvalidTokenError (u.a. ExpiredSignatureError) bei ungueltigem Token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def new_refresh_token_plaintext() -> str:
    """Rohes, dem Client ausgehaendigtes Refresh-Token (nur der Hash landet in der DB)."""
    import secrets

    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # Fuer ein zufaelliges 64-Zeichen-Token reicht ein einfacher, schneller Hash (kein Passwort).
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()
