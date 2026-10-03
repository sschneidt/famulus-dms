"""HTTP-Seite neben HTTPS (Port 8000): Umleitung, Zertifikat-Hilfe, Healthcheck.

- /zertifikat: Anleitung, wie ein neues Geraet der HomeDMS-Zertifizierungsstelle vertraut
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

from homedms.core import tls

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
            return Response("Kein eigenes Zertifikat - HomeDMS nutzt ein offizielles.", status_code=404)
        return Response(files.ca_cert.read_bytes(), media_type="application/x-x509-ca-cert", headers={
            "Content-Disposition": 'attachment; filename="homedms-ca.crt"', "Cache-Control": "no-store",
        })

    async def page(request: Request) -> Response:
        if files is None:
            return RedirectResponse(https_url(request, "/"), status_code=308)
        port = request.url.port or 80
        download = f"http://{_host(request)}{'' if port == 80 else f':{port}'}/homedms-ca.crt"
        qr = segno.make(download, error="m").svg_data_uri(scale=4, border=2)
        body = PAGE.format(
            download=html.escape(download), qr=qr, fingerprint=html.escape(files.fingerprint),
            target=html.escape(https_url(request, "/")), names=html.escape(", ".join(files.names)),
        )
        return HTMLResponse(body, headers={"Content-Security-Policy": PAGE_CSP, "Cache-Control": "no-store",
                                           "X-Content-Type-Options": "nosniff"})

    async def redirect(request: Request) -> Response:
        return RedirectResponse(https_url(request), status_code=308)

    return Starlette(routes=[
        Route("/health", health),
        Route("/homedms-ca.crt", ca_certificate),
        Route("/zertifikat", page),
        Route("/{path:path}", redirect, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]),
    ])


class HostTracker:
    """Merkt sich Adressen, unter denen HomeDMS aufgerufen wird, die das Zertifikat nicht abdeckt
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


PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HomeDMS – diesem Gerät die Verbindung erlauben</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:0 auto;padding:16px;line-height:1.5;color:#1a1b1e;background:#f8f9fa}}
h1{{font-size:1.5rem}} h2{{font-size:1.1rem;margin-top:1.6em}} .card{{background:#fff;border:1px solid #dee2e6;border-radius:10px;padding:16px;margin:12px 0}}
a.btn{{display:inline-block;background:#228be6;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600}}
code{{font-size:.85em;word-break:break-all;background:#f1f3f5;padding:2px 4px;border-radius:4px}} .qr{{float:right;margin:0 0 8px 16px}}
details{{background:#fff;border:1px solid #dee2e6;border-radius:10px;padding:10px 14px;margin:8px 0}} summary{{font-weight:600;cursor:pointer}}
@media (prefers-color-scheme:dark){{body{{background:#1a1b1e;color:#e9ecef}}.card,details{{background:#25262b;border-color:#373a40}}code{{background:#373a40}}}}
</style></head><body>
<h1>HomeDMS sicher verbinden</h1>
<p>HomeDMS verschlüsselt alle Verbindungen. Damit dein Gerät der Verschlüsselung vertraut (und keine Warnung zeigt),
installierst du <b>einmal pro Gerät</b> das Zertifikat deiner HomeDMS-Installation.</p>
<div class="card"><img class="qr" src="{qr}" alt="QR-Code zum Herunterladen" width="140" height="140">
<p><b>1. Zertifikat laden</b><br>Am Handy: QR-Code scannen. Am PC: Knopf drücken.</p>
<p><a class="btn" href="/homedms-ca.crt">Zertifikat herunterladen</a></p>
<p style="clear:both;font-size:.9em">Fingerabdruck zum Vergleichen (SHA-256):<br><code>{fingerprint}</code></p></div>
<p><b>2. Installieren und vertrauen</b> – je nach Gerät:</p>
<details><summary>iPhone / iPad</summary><ol>
<li>In <b>Safari</b> öffnen und „Zertifikat herunterladen“ antippen, „Zulassen“.</li>
<li><b>Einstellungen</b> → oben „Profil geladen“ → <b>Installieren</b> (Code eingeben).</li>
<li><b>Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen</b> → „HomeDMS lokale Zertifizierungsstelle“ einschalten.</li></ol></details>
<details><summary>Android</summary><ol>
<li>Zertifikat herunterladen.</li>
<li><b>Einstellungen → Sicherheit → Weitere Sicherheitseinstellungen → Verschlüsselung &amp; Anmeldedaten → Zertifikat installieren → CA-Zertifikat</b>
(je nach Hersteller leicht anders benannt – in den Einstellungen nach „CA-Zertifikat“ suchen).</li>
<li>„Trotzdem installieren“ bestätigen und die Datei <code>homedms-ca.crt</code> wählen.</li></ol></details>
<details><summary>Windows</summary><ol>
<li>Zertifikat herunterladen, Datei doppelklicken → <b>Zertifikat installieren</b>.</li>
<li><b>Lokaler Computer</b> → „Alle Zertifikate in folgendem Speicher speichern“ → <b>Vertrauenswürdige Stammzertifizierungsstellen</b> → Fertig stellen.</li>
<li>Browser neu starten. (Firefox übernimmt das automatisch, sonst: Einstellungen → Datenschutz &amp; Sicherheit → Zertifikate → Importieren.)</li></ol></details>
<details><summary>Mac</summary><ol>
<li>Zertifikat herunterladen und doppelklicken – es öffnet sich die Schlüsselbundverwaltung (Schlüsselbund „System“).</li>
<li>Eintrag „HomeDMS lokale Zertifizierungsstelle“ doppelklicken → <b>Vertrauen → Immer vertrauen</b>.</li></ol></details>
<details><summary>Linux</summary><p><code>sudo cp homedms-ca.crt /usr/local/share/ca-certificates/ &amp;&amp; sudo update-ca-certificates</code><br>
Firefox/Chrome: in den Browser-Einstellungen unter „Zertifikate“ importieren und „Websites vertrauen“ ankreuzen.</p></details>
<p><b>3. Fertig:</b> <a class="btn" href="{target}">Weiter zu HomeDMS</a></p>
<p style="font-size:.85em;color:#868e96">Sicherheit: Diese Zertifizierungsstelle darf nur Adressen im Heimnetz bestätigen
(private Adressen, .local, .lan …) – sie kann keine fremden Webseiten (z. B. deiner Bank) vortäuschen.
Abgedeckt: {names}. Für Zugriff von unterwegs: per VPN ins Heimnetz.</p>
</body></html>"""
