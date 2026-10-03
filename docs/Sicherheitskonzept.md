# Sicherheitskonzept HomeDMS

Stand: 03.10.2026. Grundlage: Anforderungsdokument Abschnitt 5 („HTTPS zwingend“) und der Nutzerwunsch: „Da es sich um sensible Dokumente handelt, ist die Sicherheit enorm wichtig.“ Fernzugriff ist per VPN geplant, nicht direkt über das Internet.

## 1. Bedrohungen, gegen die HomeDMS schützt

| Bedrohung | Schutz |
|---|---|
| Mitlesen im WLAN (Passwort, Anmeldung, Dokumente) | HTTPS für alles. HomeDMS bringt eine eigene, lokale Zertifizierungsstelle mit (Abschnitt 2). Port 8000 liefert nur eine Umleitung und eine Hilfeseite, nie Daten. |
| Passwort-Raten | Nach 5 Fehlversuchen in Folge wird das Konto gesperrt: 1 Minute, danach jeweils doppelt so lange, höchstens 60 Minuten. Während der Sperre wird das Passwort gar nicht geprüft. Zusätzlich gilt je Gerät/IP eine Grenze von 20 Fehlversuchen in 15 Minuten. Unbekannte E-Mail-Adressen sind an der Antwortzeit nicht erkennbar. |
| Gestohlenes Passwort | Zwei-Faktor-Anmeldung (TOTP) mit Wiederherstellungscodes, Abschnitt 4. |
| Gestohlene oder vergessene Sitzung (z. B. altes Handy) | „Angemeldete Geräte“: Jede Sitzung lässt sich einzeln beenden, die Wirkung ist sofort da. Passwortwechsel meldet alle anderen Geräte ab. Ein kopiertes Refresh-Token wird erkannt und beendet die ganze Sitzung. |
| Eingeschleuste Skripte (XSS) | Content-Security-Policy erlaubt nur Skripte von HomeDMS selbst. Die Anmeldung liegt als HttpOnly-Cookie vor, das kein Skript lesen kann. Das kurzlebige Zugangs-Token liegt nur im Arbeitsspeicher. |
| Einbetten in fremde Seiten (Klick-Fallen) | `frame-ancestors 'self'` und `X-Frame-Options: SAMEORIGIN`. |
| Übernahme einer frischen Installation | Die Ersteinrichtung braucht einen Einmal-Code, Abschnitt 5. |
| Ausspähen der Programmschnittstelle | Die API-Dokumentation (`/docs`) ist nur sichtbar, wenn `API_DOCS=true` gesetzt ist. |
| Zugriff auf Daten anderer Haushalte bzw. fremder Kategorien | Haushalt und Rechte werden bei jeder Datenbankabfrage geprüft (`core/visibility.py`). |
| Interne Dienste angreifen | Datenbank, Suche und KI sind nicht von außen erreichbar: Docker-internes Netz bzw. nur `localhost`. |
| Daten in fremden Händen | Alles läuft lokal, auch die KI. Es gibt keinen Cloud-Dienst und keine Telemetrie (Meilisearch mit `--no-analytics`). |

## 2. Verschlüsselung der Übertragung (HTTPS)

**Betriebsarten** (`TLS_MODE`):

| Modus | Wann | Verhalten |
|---|---|---|
| `auto` (Standard) | Heimnetz bzw. VPN | Eigene Zertifizierungsstelle (CA). HTTPS auf `HTTPS_PORT` (8443). Port 8000 leitet um und zeigt unter `/zertifikat` die Hilfeseite für neue Geräte. |
| `off` | hinter einem Reverse Proxy, der HTTPS macht (z. B. Synology) | HomeDMS spricht nur HTTP. Dann `APP_BIND=127.0.0.1` setzen, damit niemand am Proxy vorbei zugreift. |
| `custom` | eigenes Zertifikat (z. B. Let's Encrypt über eine eigene Domain) | `TLS_CERT_FILE` und `TLS_KEY_FILE` angeben. |

**Eigene Zertifizierungsstelle** (`core/tls.py`):
- **Schlüssel:** Die CA nutzt einen ECDSA-P-256-Schlüssel und ist 10 Jahre gültig. Er liegt in `TLS_DIR`, mit Rechten 600 bzw. Windows-ACL „nur Admins und SYSTEM“, und bewusst nicht im Dokumente-Ordner.
- **Namensbeschränkung (Name Constraints, kritisch):** Die CA darf nur Zertifikate ausstellen für:
  - private IP-Bereiche (10/8, 172.16/12, 192.168/16, 100.64/10 für Tailscale, Loopback),
  - Heimnetz-Endungen (`.local`, `.lan`, `.home`, `.home.arpa`, `.internal`, `.fritz.box`, `.ts.net`),
  - den Rechnernamen.

  Selbst mit gestohlenem CA-Schlüssel lässt sich damit keine fremde Webseite fälschen, etwa die der eigenen Bank. Das ist mit OpenSSL geprüft (`tests/test_security_hardening.py`).
- **Server-Zertifikat:** 397 Tage gültig, das entspricht der Vorgabe der Browser. Es wird beim Start automatisch erneuert, wenn es in weniger als 30 Tagen abläuft oder ein Name bzw. eine Adresse fehlt. Die CA bleibt dabei gleich, Geräte müssen also nichts neu installieren.
- **Namen:** Rechnername, `name.local`, die eigenen IP-Adressen und `TLS_HOSTNAMES`. Im Docker-Betrieb kennt der Container den NAS-Namen nicht, deshalb `TLS_HOSTNAMES` in der `.env` setzen. Wird HomeDMS unter einer nicht abgedeckten Adresse aufgerufen, zeigt die Diagnose das an.
- **Neues Gerät:** einmal `http://<server>:8000/zertifikat` öffnen. Die Seite hat einen QR-Code für das Handy, den Fingerabdruck zum Vergleichen und Anleitungen für iPhone/iPad, Android, Windows, Mac und Linux. Das Windows-Installationsskript trägt die CA auf dem Server-PC selbst automatisch ein.
- **Kein HSTS:** HSTS würde Port 8000, also den Weg für neue Geräte, im Browser sperren. Die Umleitung von HTTP auf HTTPS übernimmt stattdessen Port 8000.

## 3. Anmeldung und Sitzungen

- **Passwörter:** Argon2. Mindestens 8 Zeichen; die Oberfläche empfiehlt einen ganzen Satz.
- **Tokens:**
  - Das Access-Token (JWT, HS256, 15 Minuten) enthält die Sitzungs-ID. Bei jeder Anfrage wird geprüft, ob die Sitzung noch aktiv ist (`api/deps.py`). Abmelden, „Gerät abmelden“, Deaktivieren und Passwortwechsel wirken deshalb sofort.
  - Das Refresh-Token ist 30 Tage gültig, zufällig und wird nur als SHA-256-Hash gespeichert. Die Weboberfläche erhält es als Cookie (`HttpOnly`, `SameSite=Strict`, `Secure` bei HTTPS, Pfad `/api/v1/auth`). Andere Clients ohne die Kopfzeile `X-HomeDMS-Session: cookie` bekommen es im Antworttext.
- **Rotation:** Jede Erneuerung erzeugt ein neues Refresh-Token und markiert das alte als „rotiert“. Taucht ein rotiertes Token nach mehr als 60 Sekunden wieder auf, wurde es kopiert: Die ganze Sitzung wird beendet. Die 60 Sekunden decken zwei Tabs ab, die gleichzeitig erneuern.
- **Geräteliste:** zeigt Gerät und Browser (aus dem User-Agent), IP-Adresse und letzte Nutzung. Einzelne Geräte lassen sich abmelden, ebenso „überall sonst“.

## 4. Zwei-Faktor-Anmeldung (TOTP, RFC 6238)

- **Einrichten:** unter „Konto & Sicherheit“. Nach der Passwort-Bestätigung erscheint ein QR-Code; das Geheimnis wird erst aktiv, wenn der erste Code aus der App bestätigt ist.
- **Codes:** Jeder Code gilt nur einmal, auch ein abgefangener Code ist danach wertlos. Erlaubt ist eine Uhrabweichung von ±30 Sekunden.
- **Wiederherstellungscodes:** 10 Stück, je einmal nutzbar, gespeichert nur als Hashes. Sie werden einmal angezeigt und lassen sich neu erzeugen, wobei die alten verfallen.
- **Anmelden:** Passwort, dann eine 5 Minuten gültige „challenge“, dann der Code. Falsche Codes zählen zur Sperre nach Fehlversuchen.
- **Handy verloren:**
  - Ein Admin setzt die Zwei-Faktor-Anmeldung eines Mitglieds unter „Benutzer“ zurück; das Mitglied wird dabei abgemeldet.
  - Für den einzigen Admin gibt es den Befehl `python -m homedms.cli reset-2fa <email>` auf dem Server.
- **Hinweis für Admins:** In der Benutzerliste sind Admins ohne Zwei-Faktor-Anmeldung markiert.

## 5. Ersteinrichtung

Solange kein Haushalt existiert, erzeugt HomeDMS einen Einmal-Code. Er steht:
- im Protokoll (`docker compose logs app-api`),
- in `<Dokumente-Ordner>/.einrichtungscode`,
- bei den Installationsskripten in der Ausgabe am Ende (`SETUP_CODE` in `homedms.env`).

Ohne den Code lässt sich kein Admin anlegen. Nach der Einrichtung wird die Datei gelöscht.

## 6. Kopfzeilen (`security_headers.py`)

- `Content-Security-Policy`:
  - `default-src 'self'`, `script-src 'self'` (keine Inline-Skripte),
  - `style-src 'self' 'unsafe-inline'` (für Mantine),
  - `img-src 'self' data: blob:`,
  - `frame-src`/`object-src 'self' blob:` (PDF-Vorschau),
  - `frame-ancestors 'self'`, `base-uri`/`form-action 'self'`.
- Weitere Kopfzeilen:
  - `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: same-origin`,
  - `Permissions-Policy: camera=(self)`, Mikrofon, Ort usw. aus,
  - `Cross-Origin-Opener-Policy: same-origin`.
- `Cache-Control: no-store` für alle API-Antworten, damit Dokumente nicht in fremden Zwischenspeichern landen.

Die gebaute Oberfläche ist gegen diese Richtlinie geprüft: keine Verstöße auf Konto-Seite, Zwei-Faktor-Einrichtung, Dokument mit PDF-Vorschau und Anmeldung.

## 7. Gespeicherte Daten

HomeDMS speichert Dokumente unverschlüsselt im Dateisystem. Das ist nötig, damit Texterkennung, Suche und das Öffnen per Netzwerkfreigabe funktionieren. Den Schutz im Ruhezustand übernimmt die Verschlüsselung des Speichers:

| Plattform | Empfehlung |
|---|---|
| Synology | verschlüsseltes Volume oder verschlüsselter freigegebener Ordner (DSM) |
| Windows | BitLocker |
| Linux | LUKS |
| Datensicherung | Hyper Backup mit Client-seitiger Verschlüsselung bzw. `restic`/`borg` (verschlüsselt) |

`homedms.env` bzw. `.env` enthalten Geheimnisse (Datenbank-Passwort, JWT-Schlüssel): Sie sind nur für Admins lesbar und nie im Git-Repository. TOTP-Geheimnisse liegen in der Datenbank. Wer die Datenbank liest, hat ohnehin Zugriff auf alles, deshalb sind sie dort nicht gesondert verschlüsselt.

## 8. Zugriff von unterwegs

Empfohlen: **VPN**, also Synology VPN Server, WireGuard (z. B. in der FRITZ!Box) oder Tailscale. HomeDMS bleibt von außen unsichtbar; über das VPN gilt das Heimnetz-Zertifikat. Tailscale-Adressen (100.64/10, `*.ts.net`) sind in der Namensbeschränkung enthalten.

Eine direkte Freigabe ins Internet ist nicht vorgesehen. Falls doch gewünscht: eigene Domain mit Let's Encrypt über den Synology-Reverse-Proxy (`TLS_MODE=off` + `APP_BIND=127.0.0.1`) und Zwei-Faktor-Anmeldung für alle Konten.

## 9. Offene Punkte

- **Windows-Skript und PowerShell 5.1:** Das Installationsskript für Windows und der Smoke-Test unter Windows PowerShell 5.1 (Zertifikatsprüfung per .NET) sind auf echtem Windows noch nicht gelaufen.
- **Pflicht zur Zwei-Faktor-Anmeldung:** Eine Einstellung „Zwei-Faktor für Admins Pflicht“ fehlt noch.
- **Protokoll sicherheitsrelevanter Ereignisse:** Anmeldungen, Sperren und Rechteänderungen werden noch nicht als Verlauf in der Oberfläche angezeigt.
