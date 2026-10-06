"""Sicherheits-Kopfzeilen fuer alle Antworten (docs/Sicherheitskonzept.md).

- Content-Security-Policy: Die Seite darf nur Skripte/Daten von Famulus DMS selbst laden - ein
  eingeschleustes Skript (z. B. ueber einen manipulierten Dateinamen) koennte nichts nachladen
  und nichts an fremde Server schicken. Inline-Styles braucht Mantine.
- frame-ancestors/X-Frame-Options: Famulus DMS laesst sich nicht in fremde Seiten einbetten
  (Schutz vor "Klick-Fallen").
- nosniff, Referrer-Policy, Permissions-Policy (Kamera nur fuer Famulus DMS selbst), COOP.
- Kein HSTS: Bei der eigenen Zertifizierungsstelle liefert Port 8000 bewusst HTTP (Umleitung +
  Zertifikat-Hilfe fuer neue Geraete) - HSTS wuerde genau diesen Weg im Browser sperren.
"""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "frame-src 'self' blob:",
    "object-src 'self' blob:",
    "media-src 'self' blob:",
    "manifest-src 'self'",
    "frame-ancestors 'self'",
    "base-uri 'self'",
    "form-action 'self'",
))

HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(self), microphone=(), geolocation=(), payment=(), usb=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [h for h in HEADERS if h[0] not in existing]
                # Dokumente, Vorschaubilder & Co. nie in fremden Zwischenspeichern ablegen
                if scope["path"].startswith("/api/") and b"cache-control" not in existing:
                    message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, send_with_headers)
