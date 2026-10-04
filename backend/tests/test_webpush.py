"""Web-Push-Verschluesselung (RFC 8291) und VAPID-Signatur (RFC 8292) - core/webpush.py.

Die Gegenseite (Entschluesselung wie im Browser) ist hier unabhaengig nachgebaut."""
import hashlib
import hmac
import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from homedms.core import webpush
from homedms.core.webpush import Vapid, b64url, b64url_decode


def _browser_keys():
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return key, b64url(public), b64url(b"0123456789abcdef")


def _hkdf(salt, ikm, info, length):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def _decrypt(body: bytes, ua_key, ua_public_b64: str, auth_b64: str) -> bytes:
    salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
    as_public = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    shared = ua_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ua_public = b64url_decode(ua_public_b64)
    ikm = _hkdf(b64url_decode(auth_b64), shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_encrypt_roundtrip():
    key, p256dh, auth = _browser_keys()
    body = webpush.encrypt("Kündigungsfrist morgen".encode(), p256dh, auth)
    assert _decrypt(body, key, p256dh, auth).decode() == "Kündigungsfrist morgen"


def test_encrypt_rejects_bad_keys():
    with pytest.raises(ValueError):
        webpush.encrypt(b"x", b64url(b"kurz"), b64url(b"0123456789abcdef"))


def test_long_message_is_shortened():
    data = webpush.encode_message({"title": "T", "body": "x" * 10000, "url": "/termine"})
    assert len(data) <= webpush.MAX_PAYLOAD
    assert json.loads(data)["url"] == "/termine"


def test_vapid_header():
    vapid = Vapid(ec.generate_private_key(ec.SECP256R1()))
    header = vapid.authorization("https://fcm.googleapis.com/fcm/send/abc", "mailto:admin@example.com")
    token = header.split("t=")[1].split(",")[0]
    assert header.endswith(f"k={vapid.public_key}")
    claims = jwt.decode(token, vapid.private_key.public_key(), algorithms=["ES256"], audience="https://fcm.googleapis.com")
    assert claims["sub"] == "mailto:admin@example.com"


async def test_send_status_handling():
    key, p256dh, auth = _browser_keys()
    vapid = Vapid(ec.generate_private_key(ec.SECP256R1()))
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["plain"] = _decrypt(request.content, key, p256dh, auth)
        return httpx.Response({"gone": 410, "fail": 500}.get(request.url.path.strip("/"), 201))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        keys = {"p256dh": p256dh, "auth": auth}
        await webpush.send(vapid, "https://fcm.googleapis.com/ok", keys, {"title": "Hallo"}, "mailto:a@b.de", client)
        assert json.loads(seen["plain"]) == {"title": "Hallo"}
        assert seen["headers"]["content-encoding"] == "aes128gcm"
        assert seen["headers"]["ttl"] == str(webpush.TTL_SECONDS)
        with pytest.raises(webpush.PushGone):
            await webpush.send(vapid, "https://fcm.googleapis.com/gone", keys, {}, "mailto:a@b.de", client)
        with pytest.raises(webpush.PushError, match="500"):
            await webpush.send(vapid, "https://fcm.googleapis.com/fail", keys, {}, "mailto:a@b.de", client)
