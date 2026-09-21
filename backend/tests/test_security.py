"""Passwort-Hashing (Argon2) und JWT-Erzeugung/-Pruefung - homedms/core/security.py.
Reine In-Memory-Logik, keine DB noetig.
"""
import uuid

import jwt
import pytest

from homedms.core import security


def test_password_hash_roundtrip():
    hashed = security.hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert security.verify_password("correct horse battery staple", hashed)
    assert not security.verify_password("wrong password", hashed)


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    token = security.create_access_token(user_id=user_id, tenant_id=tenant_id, role="admin")

    payload = security.decode_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_decode_token_rejects_tampered_token():
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    token = security.create_access_token(user_id=user_id, tenant_id=tenant_id, role="member")

    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(jwt.InvalidTokenError):
        security.decode_token(tampered)


def test_refresh_token_is_random_and_hash_is_deterministic():
    token_a = security.new_refresh_token_plaintext()
    token_b = security.new_refresh_token_plaintext()

    assert token_a != token_b
    assert len(token_a) == 64  # zwei uuid4().hex à 32 Zeichen

    # Derselbe Klartext -> immer derselbe Hash (fuer den DB-Lookup beim Refresh noetig)
    assert security.hash_refresh_token(token_a) == security.hash_refresh_token(token_a)
    assert security.hash_refresh_token(token_a) != security.hash_refresh_token(token_b)
    assert security.hash_refresh_token(token_a) != token_a
