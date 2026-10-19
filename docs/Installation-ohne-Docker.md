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
| Meilisearch (optional) | tippfehlertolerante Suche | `-WithSearch` (deutsch: `-MitSuche`) | Standard (aus mit `--ohne-suche`) |

Bewusst **nicht** mehr nötig: die PostgreSQL-Erweiterung `pgvector`. Sie gibt es für Windows nicht als fertiges Paket; die Ähnlichkeit der Kategorie-Beispiele rechnet Famulus DMS seit Migration 0010 selbst (bei einem Haushalt Bruchteile einer Sekunde). Ohne Meilisearch sucht Famulus DMS direkt in der Datenbank (Teilwörter, ohne Tippfehler-Toleranz).

## Windows

1. Famulus-DMS-Ordner auf den PC kopieren, z. B. nach `C:\Famulus`.
2. PowerShell **als Administrator** öffnen:
   ```powershell
   cd C:\Famulus
   powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.de.ps1
   ```
   Die Installation läuft in der Sprache des Skripts: `install-windows.de.ps1` (Deutsch), `install-windows.en.ps1` (English) und `install-windows.ru.ps1` (Русский). `install-windows.ps1` wählt die Sprache nach der Windows-Anzeigesprache (Englisch, wenn es keine Übersetzung gibt); mit `-Language de|en|ru` legst du sie fest. Die Texte stehen in `scripts\lang\install-windows.<Sprache>.msg`.
   Beim ersten Lauf fragt das Skript, **wo Dokumente, Scan-Ordner und Protokolle liegen sollen** (Vorschlag `C:\Famulus-Data`, Enter übernimmt ihn). Bei einem erneuten Lauf übernimmt es den bisherigen Ordner.

   Optionen im deutschen Skript: `-DatenOrdner D:\Famulus-Data` (ohne Rückfrage), `-Port 8000`, `-HttpsPort 8443`, `-OhneKI`, `-MitSuche`. Die Skripte `.en` und `.ru` und `install-windows.ps1` heißen die Optionen `-DataFolder`, `-NoAI`, `-WithSearch` (die deutschen Namen gelten dort als Alias).
3. Am Ende öffnet sich der Browser mit `https://localhost:8443`. Der Einrichtungsassistent legt Haushalt und Admin-Konto an; den nötigen **Einrichtungscode** zeigt das Skript am Ende an.
4. Handy und andere PCs: einmal `http://<PC>:8000/zertifikat` öffnen und dem Famulus-DMS-Zertifikat vertrauen (Anleitung auf der Seite). Danach `https://<PC>:8443`.

> **Läuft Famulus DMS auf diesem PC schon in Docker?** Dann zuerst im Projektordner `docker compose stop` ausführen. Das Skript richtet ein eigenes PostgreSQL auf Port 5432 ein, und die Ports 8000 und 8443 kann nur eine der beiden Varianten belegen. Die Windows-Installation ist eine **zweite, getrennte Instanz** mit eigener Datenbank und eigenem Datenordner; Daten aus Docker werden nicht übernommen.

Was das Skript einrichtet:
- **Autostart:** geplante Aufgabe „Famulus DMS“ (Aufgabenplanung). Sie startet beim Hochfahren, auch ohne Anmeldung, als Konto SYSTEM, und startet nach einem Absturz neu.
- **Firewall:** Ports 8000 (Umleitung + Zertifikat-Hilfe) und 8443 (Famulus DMS per HTTPS) für das private Netzwerk.
- **Verschlüsselung:** eigene Zertifizierungsstelle in `C:\Famulus-Data\tls` (nur Admins + SYSTEM); auf dem Server-PC selbst trägt das Skript sie als vertrauenswürdig ein. Details: `Sicherheitskonzept.md`.
- **Einstellungen:** `C:\Famulus\homedms.env`, nur für Administratoren lesbar.
- **Daten:** im gewählten Datenordner (hier der Vorschlag `C:\Famulus-Data`): `documents` (Ablage), `scan` (Scan-Ordner) und `logs` (Protokolle). Die folgenden Pfade gelten für diesen Vorschlag.
- **Datenbank-Admin-Passwort:** `C:\Famulus-Data\postgres-admin-password.txt` (frühere Installationen: `…-passwort.txt`, wird weiter gefunden). Das gilt nur, wenn PostgreSQL neu installiert wurde. Bei einem schon vorhandenen PostgreSQL fragt das Skript nach dem Passwort.

Hinweise:
- **Ollama:** Unter Windows läuft Ollama im angemeldeten Benutzer (Symbol im Infobereich). Nach einem Neustart rechnet die KI deshalb erst nach der Anmeldung. Bis dahin hochgeladene Dokumente landen unter „Prüfen“ und lassen sich mit „Erneut analysieren“ nachholen.
- **Scanner:** Der Scan-Ordner `C:\Famulus-Data\scan` lässt sich im Explorer freigeben (Rechtsklick > Eigenschaften > Freigabe). Das Multifunktionsgerät legt dann per „Scan to Folder“ direkt dort ab.
- **Energiesparen:** Der PC sollte nicht in den Ruhezustand gehen, wenn das Handy jederzeit zugreifen soll.
- **Handy-App (PWA):** Sobald das Handy dem Famulus-DMS-Zertifikat vertraut, lässt sich Famulus DMS über „Zum Startbildschirm hinzufügen“ wie eine App installieren.

## Linux (Debian 12+, Ubuntu 22.04+)

```bash
sudo mv famulus-dms /opt/homedms        # (Name des geklonten Ordners) muss für den Dienst-Benutzer lesbar sein
cd /opt/homedms
sudo bash scripts/install-linux.de.sh  # Optionen: --ohne-ki, --ohne-suche, --ohne-dienst
```

Auch die Linux-Installation läuft in der Sprache des Skripts: `install-linux.de.sh` (Deutsch), `install-linux.en.sh` (English) und `install-linux.ru.sh` (Русский). `install-linux.sh` wählt sie nach der Systemsprache (`LANG`); mit `--lang de|en|ru` legst du sie fest. Die englischen Optionen heißen `--no-ai`, `--no-search`, `--no-service` (die deutschen gelten weiter). Die Texte stehen in `scripts/lang/install-linux.<Sprache>.msg`.

Die erzeugte Einstellungsdatei `homedms.env` entsteht aus der Vorlage in der Sprache der Installation (`homedms.env.de.example`, `homedms.env.ru.example`, sonst `homedms.env.example` auf Englisch). Die Werte sind in allen Vorlagen gleich, nur die Kommentare unterscheiden sich. Wer die Datei von Hand anlegt, kopiert die Vorlage seiner Sprache nach `homedms.env`.

Was das Skript einrichtet:
- **Adresse:** `https://<server>:8443`; neue Geräte vertrauen dem Zertifikat einmal über `http://<server>:8000/zertifikat`. Den Einrichtungscode zeigt das Skript am Ende an.
- **Dienst:** `homedms` (systemd) läuft als eigener Benutzer `homedms`. Er startet beim Hochfahren und nach einem Absturz neu: `systemctl status homedms`.
- **Daten:** `/var/lib/homedms/{documents,scan,logs,meilisearch,tls}`. Das Verzeichnis lässt sich mit `HOMEDMS_DATA=/pfad` vor dem Aufruf ändern.
- **Ollama:** läuft als eigener Dienst und rechnet sofort nach dem Hochfahren.
- **Scanner:** den Scan-Ordner per Samba freigeben, z. B. `[scan] path = /var/lib/homedms/scan`. Die Schreibrechte für den Freigabe-Benutzer stellt man mit `chgrp`/`chmod g+w` ein.

## Deinstallation

### Windows

PowerShell **als Administrator** im Famulus-DMS-Ordner:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.de.ps1
```

Wie bei der Installation gibt es je Sprache ein Skript (`uninstall-windows.de.ps1`, `.en.ps1`, `.ru.ps1`); `uninstall-windows.ps1` wählt die Sprache nach der Windows-Anzeigesprache.

**Ablauf:** Das Skript schaut zuerst, was installiert ist, und fragt dann nach, was weg soll. Erst danach zeigt es einen Plan und fragt noch einmal. Erst dann ändert es etwas:

1. Famulus DMS stoppen, Autostart-Aufgabe, Firewall-Regel und Zertifikat entfernen (wird immer zuerst gefragt; wer Nein sagt, bricht ab).
2. Die Programmdateien im Famulus-DMS-Ordner löschen (`homedms.env`, `.tools`, `backend\.venv`, `frontend\node_modules`, `frontend\dist`). Der Quellcode bleibt, alles lässt sich neu erzeugen.
3. Die Datenbank `homedms` und ihren Benutzer aus PostgreSQL löschen.
4. Den **Datenordner mit allen Dokumenten** löschen. Dafür musst du ein Bestätigungswort eintippen. Vor Schritt 3 und 4 bietet das Skript ein Backup an: Dokumente, Scan-Ordner, Zertifikate und ein Datenbank-Dump. Schlägt das Backup fehl, wird nichts gelöscht.
5. PostgreSQL, Tesseract und Ollama per winget deinstallieren (jedes einzeln gefragt, nur mit Ja, wenn du sie nicht anderweitig brauchst) und ihre Reste löschen (Datenbankdateien, Ollama-Modelle).

**Sicherheit:** Schritte 3 bis 5 sind nie voreingestellt und werden auch von `-Ja` nicht automatisch bejaht. Ein Ordner wird nur gelöscht, wenn er wie ein Famulus-DMS-Datenordner aussieht (mit `documents` und `tls`), nie ein ganzes Laufwerk, ein Systemordner oder der Programmordner. Ein Docker-Betrieb von Famulus DMS und der Quellcode werden nie angefasst.

**Probelauf:** Mit `-Testlauf` zeigt das Skript alle Schritte, ohne etwas zu verändern, und braucht keine Administratorrechte. Mit `-Testlauf -Ja` beantwortet es dabei alle Fragen mit Ja, so siehst du den vollständigen Plan. Ist der Datenordner nicht lesbar (ohne Administratorrechte), gibst du ihn mit `-DatenOrdner I:\Famulus-Data` an.

Handys und andere PCs, die dem Zertifikat vertraut haben, behalten es; dort entfernst du es von Hand.

### Linux

Dafür gibt es noch kein Skript. Von Hand (der Datenordner enthält deine Dokumente, vorher sichern):

```bash
sudo systemctl disable --now homedms
sudo rm /etc/systemd/system/homedms.service
sudo systemctl daemon-reload
sudo -u postgres psql -c "DROP DATABASE homedms" -c "DROP ROLE homedms"
sudo rm -r /var/lib/homedms
sudo userdel homedms
```

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
- **Meilisearch unter Windows:** Der Hersteller unterstützt Windows 10/11 nur eingeschränkt. Deshalb ist die Suche dort optional (`-WithSearch`, deutsch `-MitSuche`).
