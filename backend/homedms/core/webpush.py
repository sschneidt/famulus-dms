"""Web-Push aufs Handy/den PC (Anforderungsdokument 4.5) - ohne Zusatzbibliothek.

Ablauf: Der Browser meldet sich bei seinem Push-Dienst an (Google, Apple, Mozilla) und gibt
Famulus DMS eine Adresse (endpoint) plus Schluessel. Famulus DMS verschluesselt jede Nachricht fuer genau
dieses Geraet (RFC 8291, aes128gcm) und schickt sie an den Push-Dienst, signiert mit dem eigenen
VAPID-Schluessel (RFC 8292). Der Push-Dienst sieht nur verschluesselte Bytes.

Der VAPID-Schluessel liegt in der Datenbank (app_settings) - er muss gleich bleiben, sonst
verwerfen die Push-Dienste die Nachrichten an bereits angemeldete Geraete.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.i18n import _
from homedms.models.ops import AppSetting

VAPID_KEY = "vapid"
RECORD_SIZE = 4096
MAX_PAYLOAD = 3000  # Push-Dienste nehmen hoechstens ~4 KB verschluesselt an
TTL_SECONDS = 24 * 3600  # Handy aus? Der Push-Dienst haelt die Nachricht einen Tag lang


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


@dataclass
class Vapid:
    private_key: ec.EllipticCurvePrivateKey

    @property
    def public_key(self) -> str:
        """applicationServerKey fuer pushManager.subscribe() im Browser."""
        return b64url(_public_bytes(self.private_key.public_key()))

    def authorization(self, endpoint: str, subject: str) -> str:
        parts = urlsplit(endpoint)
        claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": subject}
        token = jwt.encode(claims, self.private_key, algorithm="ES256", headers={"typ": "JWT"})
        return f"vapid t={token}, k={self.public_key}"


async def get_vapid(db: AsyncSession) -> Vapid:
    """VAPID-Schluessel laden - beim ersten Mal erzeugen (auch bei zwei Prozessen gleichzeitig nur einmal)."""
    row = await db.get(AppSetting, VAPID_KEY)
    if row is None:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
        await db.execute(insert(AppSetting).values(key=VAPID_KEY, value={"private_pem": pem})
                         .on_conflict_do_nothing(index_elements=["key"]))
        await db.commit()
        row = await db.get(AppSetting, VAPID_KEY)
    key = serialization.load_pem_private_key(row.value["private_pem"].encode(), password=None)
    return Vapid(key)


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def encrypt(payload: bytes, p256dh: str, auth: str, *, salt: bytes | None = None,
            server_key: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """RFC 8291: Nachricht fuer genau ein Geraet verschluesseln (ein Datensatz, aes128gcm)."""
    ua_public = b64url_decode(p256dh)
    auth_secret = b64url_decode(auth)
    if len(ua_public) != 65 or len(auth_secret) < 16:
        raise ValueError(_("ungültige Push-Schlüssel des Geräts"))
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(server_key.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = server_key.exchange(ec.ECDH(), ua_key)

    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # \x02 = letzter Datensatz
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + ciphertext


class PushGone(Exception):
    """Geraet hat Push abbestellt (App entfernt, Berechtigung entzogen) - Abo loeschen."""


class PushError(Exception):
    pass


def encode_message(message: dict) -> bytes:
    data = json.dumps(message, ensure_ascii=False).encode()
    if len(data) > MAX_PAYLOAD:  # zu lang: Text kuerzen, Link bleibt
        body = message.get("body", "")
        cut = max(0, len(body) - (len(data) - MAX_PAYLOAD) - 3)
        data = json.dumps({**message, "body": body[:cut] + "…"}, ensure_ascii=False).encode()
    return data


async def send(vapid: Vapid, subscription_endpoint: str, keys: dict, message: dict, subject: str,
               client: httpx.AsyncClient | None = None) -> None:
    body = encrypt(encode_message(message), keys["p256dh"], keys["auth"])
    headers = {
        "Authorization": vapid.authorization(subscription_endpoint, subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SECONDS),
        "Urgency": "normal",
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        response = await client.post(subscription_endpoint, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise PushError(_("Push-Dienst nicht erreichbar ({error}) - hat der Server Internetzugang?", error=exc.__class__.__name__)) from exc
    finally:
        if own:
            await client.aclose()
    if response.status_code in (404, 410):
        raise PushGone()
    if response.status_code >= 400:
        raise PushError(_("Push-Dienst meldet {status}: {text}", status=response.status_code, text=response.text[:200]))
