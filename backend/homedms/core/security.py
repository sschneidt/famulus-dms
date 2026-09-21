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


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Wirft jwt.InvalidTokenError (u.a. ExpiredSignatureError) bei ungueltigem Token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def new_refresh_token_plaintext() -> str:
    """Rohes, dem Client ausgehaendigtes Refresh-Token (nur der Hash landet in der DB)."""
    return uuid.uuid4().hex + uuid.uuid4().hex


def hash_refresh_token(token: str) -> str:
    # Fuer ein zufaelliges 64-Zeichen-Token reicht ein einfacher, schneller Hash (kein Passwort).
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()
