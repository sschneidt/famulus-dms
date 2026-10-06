"""HTTP-Seite neben HTTPS (Port 8000): Umleitung, Zertifikat-Hilfe, Healthcheck.

- /zertifikat: Anleitung, wie ein neues Geraet der Famulus-DMS-Zertifizierungsstelle vertraut
  (iPhone, Android, Windows, Mac, Linux), mit QR-Code fuer das Handy und Fingerabdruck zum
  Vergleichen. Danach laeuft alles ueber https://<server>:8443 ohne Warnung.
- /homedms-ca.crt: das CA-Zertifikat (oeffentlich - der private Schluessel verlaesst nie den Server).
- /health: fuer den Docker-Healthcheck.
- alles andere: Umleitung auf dieselbe Adresse per HTTPS.

Ueber diese Seite laufen keine Daten: kein Login, keine Dokumente - nur Umleitung und Hilfe.
"""
import html

import segno
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from homedms import i18n
from homedms.cert_page_text import BODIES, HEAD, TITLES
from homedms.core import tls
from homedms.i18n import _

PAGE_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


def _host(request: Request) -> str:
    host = request.headers.get("host", "localhost")
    if host.startswith("["):  # IPv6 [::1]:8000
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def build_redirect_app(https_port: int, files: "tls.TlsFiles | None") -> ASGIApp:
    def https_url(request: Request, path: str | None = None) -> str:
        port = "" if https_port == 443 else f":{https_port}"
        query = f"?{request.url.query}" if request.url.query and path is None else ""
        return f"https://{_host(request)}{port}{path if path is not None else request.url.path}{query}"

    async def health(_request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    async def ca_certificate(_request: Request) -> Response:
        if files is None:
            return Response(_("Kein eigenes Zertifikat - Famulus DMS nutzt ein offizielles."), status_code=404)
        return Response(files.ca_cert.read_bytes(), media_type="application/x-x509-ca-cert", headers={
            "Content-Disposition": 'attachment; filename="homedms-ca.crt"', "Cache-Control": "no-store",
        })

    async def page(request: Request) -> Response:
        if files is None:
            return RedirectResponse(https_url(request, "/"), status_code=308)
        port = request.url.port or 80
        download = f"http://{_host(request)}{'' if port == 80 else f':{port}'}/homedms-ca.crt"
        qr = segno.make(download, error="m").svg_data_uri(scale=4, border=2)
        # Sprache: ?lang=.. (Umschalter auf der Seite), sonst die des Browsers (LanguageMiddleware)
        lang = i18n.normalize(request.query_params.get("lang") or i18n.current())
        languages = " ".join(
            f'<a href="?lang={code}">{label}</a>' if code != lang else f"<b>{label}</b>"
            for code, label in (("de", "Deutsch"), ("en", "English"), ("ru", "Русский"))
        )
        body = (HEAD + BODIES[lang]).format(
            lang=lang, title=html.escape(TITLES[lang]), languages=languages, qr=qr,
            fingerprint=html.escape(files.fingerprint), target=html.escape(https_url(request, "/")),
            names=html.escape(", ".join(files.names)),
        )
        return HTMLResponse(body, headers={"Content-Security-Policy": PAGE_CSP, "Cache-Control": "no-store",
                                           "X-Content-Type-Options": "nosniff"})

    async def redirect(request: Request) -> Response:
        return RedirectResponse(https_url(request), status_code=308)

    return i18n.LanguageMiddleware(Starlette(routes=[
        Route("/health", health),
        Route("/homedms-ca.crt", ca_certificate),
        Route("/zertifikat", page),
        Route("/{path:path}", redirect, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]),
    ]))


class HostTracker:
    """Merkt sich Adressen, unter denen Famulus DMS aufgerufen wird, die das Zertifikat nicht abdeckt
    (-> Browser-Warnung). Die Diagnose zeigt sie mit dem Hinweis, TLS_HOSTNAMES zu ergaenzen."""

    def __init__(self, app: ASGIApp, names: tuple[str, ...]) -> None:
        self.app, self.names = app, {n.lower() for n in names}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            host = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1").lower()
            host = host.split("]")[0].lstrip("[") if host.startswith("[") else host.rsplit(":", 1)[0]
            if host and host not in self.names and len(tls.UNCOVERED) < 20:
                tls.UNCOVERED.add(host)
        await self.app(scope, receive, send)
