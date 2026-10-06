# Famulus DMS ohne Docker – Windows-PC oder Linux-Server

Famulus DMS läuft auf drei Wegen:

| Weg | Für wen | Aufwand |
|---|---|---|
| **Docker** (NAS, Linux, Windows mit Docker Desktop) | Synology-NAS und alle, die Docker schon nutzen | `docker compose up -d` – siehe `Docker-Compose-Entwurf.md` |
| **Windows nativ** | ein Windows-PC, der ohnehin läuft | ein Skript, ca. 15–30 Minuten (vor allem Downloads) |
| **Linux nativ** (Debian/Ubuntu) | Heimserver, Mini-PC, Raspberry Pi 5 | ein Skript |

Alle drei Wege nutzen denselben Programmcode und dieselbe Datenbankstruktur. Ein Umzug (z. B. vom PC auf die NAS) ist ein Datenbank-Export plus Kopie des Dokumente-Ordners.

## Was ohne Docker gebraucht wird

| Baustein | Wozu | Windows | Linux |
|---|---|---|---|
| PostgreSQL 14+ (mit `pg_trgm`, ist dabei) | Datenbank, Job-Warteschlange | winget `PostgreSQL.PostgreSQL.16` | `apt install postgresql` |
| Tesseract + Deutsch | Texterkennung | winget `UB-Mannheim.TesseractOCR` + Sprachdatei | `apt install tesseract-ocr-deu` |
| Ollama | lokale KI (Einordnung, Betreff, Fristen) | winget `Ollama.Ollama` | Installationsskript von ollama.com |
| Python 3.12 | Famulus DMS selbst | von `uv` in `.tools\python` | von `uv` in `.tools/python` |
| Node.js 22 | nur zum **Bauen** der Weboberfläche | in `.tools\node` | in `.tools/node` |
| Meilisearch (optional) | tippfehlertolerante Suche | `-MitSuche` | Standard (aus mit `--ohne-suche`) |

Bewusst **nicht** mehr nötig: die PostgreSQL-Erweiterung `pgvector`. Sie gibt es für Windows nicht als fertiges Paket; die Ähnlichkeit der Kategorie-Beispiele rechnet Famulus DMS seit Migration 0010 selbst (bei einem Haushalt Bruchteile einer Sekunde). Ohne Meilisearch sucht Famulus DMS direkt in der Datenbank (Teilwörter, ohne Tippfehler-Toleranz).

## Windows

1. Famulus-DMS-Ordner auf den PC kopieren, z. B. nach `C:\HomeDMS`.
2. PowerShell **als Administrator** öffnen:
   ```powershell
   cd C:\HomeDMS
   powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
   ```
   Optionen: `-DatenOrdner D:\HomeDMS-Daten` (Standard `C:\HomeDMS-Daten`), `-Port 8000`, `-HttpsPort 8443`, `-OhneKI`, `-MitSuche`.
3. Am Ende öffnet sich der Browser mit `https://localhost:8443`. Der Einrichtungsassistent legt Haushalt und Admin-Konto an; den nötigen **Einrichtungscode** zeigt das Skript am Ende an.
4. Handy und andere PCs: einmal `http://<PC>:8000/zertifikat` öffnen und dem Famulus-DMS-Zertifikat vertrauen (Anleitung auf der Seite). Danach `https://<PC>:8443`.

Was das Skript einrichtet:
- **Autostart:** geplante Aufgabe „Famulus DMS“ (Aufgabenplanung). Sie startet beim Hochfahren, auch ohne Anmeldung, als Konto SYSTEM, und startet nach einem Absturz neu.
- **Firewall:** Ports 8000 (Umleitung + Zertifikat-Hilfe) und 8443 (Famulus DMS per HTTPS) für das private Netzwerk.
- **Verschlüsselung:** eigene Zertifizierungsstelle in `C:\HomeDMS-Daten\tls` (nur Admins + SYSTEM); auf dem Server-PC selbst trägt das Skript sie als vertrauenswürdig ein. Details: `Sicherheitskonzept.md`.
- **Einstellungen:** `C:\HomeDMS\homedms.env`, nur für Administratoren lesbar.
- **Daten:** `C:\HomeDMS-Daten\documents` (Ablage), `scan` (Scan-Ordner) und `logs` (Protokolle).
- **Datenbank-Admin-Passwort:** `C:\HomeDMS-Daten\postgres-admin-passwort.txt`. Das gilt nur, wenn PostgreSQL neu installiert wurde. Bei einem schon vorhandenen PostgreSQL fragt das Skript nach dem Passwort.

Hinweise:
- **Ollama:** Unter Windows läuft Ollama im angemeldeten Benutzer (Symbol im Infobereich). Nach einem Neustart rechnet die KI deshalb erst nach der Anmeldung. Bis dahin hochgeladene Dokumente landen unter „Prüfen“ und lassen sich mit „Erneut analysieren“ nachholen.
- **Scanner:** Der Scan-Ordner `C:\HomeDMS-Daten\scan` lässt sich im Explorer freigeben (Rechtsklick > Eigenschaften > Freigabe). Das Multifunktionsgerät legt dann per „Scan to Folder“ direkt dort ab.
- **Energiesparen:** Der PC sollte nicht in den Ruhezustand gehen, wenn das Handy jederzeit zugreifen soll.
- **Handy-App (PWA):** Sobald das Handy dem Famulus-DMS-Zertifikat vertraut, lässt sich Famulus DMS über „Zum Startbildschirm hinzufügen“ wie eine App installieren.

## Linux (Debian 12+, Ubuntu 22.04+)

```bash
sudo mv Famulus DMS /opt/homedms        # Ordner muss für den Dienst-Benutzer lesbar sein
cd /opt/homedms
sudo bash scripts/install-linux.sh  # Optionen: --ohne-ki, --ohne-suche, --ohne-dienst
```

Was das Skript einrichtet:
- **Adresse:** `https://<server>:8443`; neue Geräte vertrauen dem Zertifikat einmal über `http://<server>:8000/zertifikat`. Den Einrichtungscode zeigt das Skript am Ende an.
- **Dienst:** `homedms` (systemd) läuft als eigener Benutzer `homedms`. Er startet beim Hochfahren und nach einem Absturz neu: `systemctl status homedms`.
- **Daten:** `/var/lib/homedms/{documents,scan,logs,meilisearch,tls}`. Das Verzeichnis lässt sich mit `HOMEDMS_DATA=/pfad` vor dem Aufruf ändern.
- **Ollama:** läuft als eigener Dienst und rechnet sofort nach dem Hochfahren.
- **Scanner:** den Scan-Ordner per Samba freigeben, z. B. `[scan] path = /var/lib/homedms/scan`. Die Schreibrechte für den Freigabe-Benutzer stellt man mit `chgrp`/`chmod g+w` ein.

## Update

1. Neuen Stand des Famulus-DMS-Ordners einspielen (z. B. `git pull` oder Ordner ersetzen; `homedms.env` bleibt).
2. Das Installationsskript erneut starten. Es aktualisiert die Python-Pakete, baut die Oberfläche neu und startet Famulus DMS neu.
3. Datenbank-Änderungen laufen beim Start automatisch (`alembic upgrade head`).

## Von Hand starten (ohne Skript, z. B. zur Fehlersuche)

```bash
cd backend
uv sync --frozen --no-dev
uv run python -m homedms.server          # liest ../homedms.env
```

Der Starter `python -m homedms.server` macht, was sonst `docker-compose.yml` erledigt:
1. Einstellungen laden.
2. Datenbank migrieren.
3. Meilisearch mitstarten, sofern `MEILISEARCH_BINARY` gesetzt ist.
4. Den Worker als zweiten Prozess starten und bei einem Absturz neu starten.
5. Weboberfläche und API auf `HOST:PORT` bereitstellen.

Strg+C beendet alles.

## Datensicherung

Zu sichern sind drei Dinge:
- der Dokumente-Ordner (`DOCUMENTS_PATH`),
- die Datenbank (`pg_dump -U homedms homedms > homedms.sql`),
- die Datei `homedms.env`.

Unter Windows eignen sich der Dateiversionsverlauf oder eine Aufgabe mit `pg_dump`, unter Linux z. B. `restic`/`borg` plus `pg_dump` per Cron.

## Sprachen der Texterkennung

Famulus DMS legt einen eigenen Ordner für Tesseract-Sprachpakete an (`TESSDATA_DIR` in `homedms.env`; die Skripte setzen ihn auf `<Datenordner>/tessdata`). Beim Start werden die Pakete der Tesseract-Installation dorthin verlinkt (unter Windows ohne Symlink-Recht kopiert). Weitere Sprachen wählt der Admin auf der Seite „Sprachen“ oder bei der Ersteinrichtung; der Worker lädt sie dann aus dem offiziellen Tesseract-Repository (`tessdata_fast` auf GitHub) – dafür braucht der Server ausgehenden Internetzugang. Ohne Internet: die Datei `<code>.traineddata` von Hand in diesen Ordner legen.

## Erinnerungen (E-Mail/Push)

Die Uhrzeit der täglichen Zusammenfassung richtet sich nach `TZ` in `homedms.env` (Standard `Europe/Berlin`). Für Push braucht der Server ausgehenden Internetzugang (zu den Push-Diensten von Google, Apple, Mozilla bzw. Microsoft), für E-Mail Zugang zum Mailserver (Port 587 oder 465).

## Stand und Grenzen (03.10.2026)

- **Linux:** Getestet ist der Starter selbst mit frischer Datenbank ohne pgvector: Upload, Texterkennung, Ablage, Suche, Worker-Neustart, Meilisearch als Hilfsprozess und Beenden. Das Installationsskript ist nur statisch geprüft (`bash -n`, shellcheck).
- **Windows:** Das Skript ist bisher nur auf Syntax geprüft. Der erste echte Lauf findet auf dem PC des Nutzers statt. Windows-Besonderheiten im Code:
  - Selector-Event-Loop für psycopg,
  - Signale ohne `add_signal_handler`,
  - Tesseract-Pfad,
  - Job-Objekt, damit Worker und Meilisearch mit dem Starter enden.

  Diese Stellen sind eingebaut, auf echtem Windows aber noch nicht gelaufen.
- **Meilisearch unter Windows:** Der Hersteller unterstützt Windows 10/11 nur eingeschränkt. Deshalb ist die Suche dort optional (`-MitSuche`).
