# Famulus DMS

**Selbst gehostetes Dokumentenmanagementsystem (DMS) für den Haushalt.** Briefe, Rechnungen, Verträge
und Bescheide fotografieren oder scannen – Famulus DMS liest sie, ordnet sie mit einer lokalen KI ein,
erkennt Fristen und erinnert dich rechtzeitig. Alles läuft bei dir zu Hause, auf einem NAS, einem PC
oder einem Server. Deine Dokumente verlassen das Haus nicht.

> Frühe Version (0.x). Sie wird im Alltag genutzt, es kann aber noch Ecken und Kanten geben.
> Sichere deine Dokumente unabhängig davon regelmäßig (siehe [Updates](docs/Updates.md)).

## Was es kann

- **Import:** Handyfoto (mit automatischem Zuschnitt und Entzerren), Datei-Upload, mehrseitige Dokumente
  und ein überwachter Scan-Ordner, in den dein Multifunktionsgerät direkt ablegt.
- **Texterkennung (OCR)** mit Tesseract, auch für schiefe Handyfotos. Deutsch und Englisch sind dabei,
  weitere Sprachen lädt die App auf Wunsch nach.
- **Automatische Einordnung:** Ein lokales Sprachmodell (über [Ollama](https://ollama.com)) ordnet jedes
  Dokument einer Kategorie zu und liest Datum, Absender und Betrag aus. Es lernt aus deinen Korrekturen.
  Unsichere Fälle landen in einer Prüfliste, nichts wird stillschweigend falsch abgelegt.
- **Fristen und Erinnerungen:** Kündigungsfristen und Termine werden aus dem Text erkannt und als
  Wiedervorlage vorgeschlagen. Eine tägliche Zusammenfassung kommt per App, E-Mail und Push.
  Rechnungen haben einen Zahlungsstatus.
- **Lesbare Ablage:** Dateien liegen nach Kategorie, Objekt (z. B. Haus-Adresse) und Jahr sortiert und
  mit sprechenden Namen im Dateisystem – auch ohne die App auffindbar.
- **Suche** im gesamten Text, tolerant gegen Tippfehler (Meilisearch).
- **Mehrere Personen** pro Haushalt mit den Rollen Admin und Mitglied; Zwei-Faktor-Anmeldung.
- **Oberfläche** als App für Handy und Desktop (PWA) auf Deutsch, Englisch und Russisch.
- **HTTPS eingebaut**, mit eigener Zertifizierungsstelle für das Heimnetz. Kein Reverse Proxy nötig.

Den vollständigen Funktionsumfang und den Stand jeder Funktion beschreibt das
[Anforderungsdokument](docs/Anforderungsdokument.md).

## Installation mit Docker (empfohlen)

Voraussetzung: Docker mit Compose (Synology: *Container Manager*; Windows/Mac: Docker Desktop) und
mindestens 8 GB Arbeitsspeicher. Eine Grafikkarte ist nicht nötig.

1. **Herunterladen** (oder das Archiv der neuesten [Version](https://github.com/sschneidt/famulus-dms/releases) entpacken):

   ```bash
   git clone https://github.com/sschneidt/famulus-dms.git
   cd famulus-dms
   ```

2. **Einstellungen anlegen:** `.env.example` nach `.env` kopieren und die mit `<-` markierten Werte
   anpassen: Passwörter und Schlüssel (zum Beispiel mit `openssl rand -hex 32` erzeugen) und unter
   `TLS_HOSTNAMES` den Namen und die IP-Adresse deines Servers.

   ```bash
   cp .env.example .env
   ```

3. **Starten:**

   ```bash
   docker compose up -d
   ```

   Beim ersten Start lädt Docker das Image und das KI-Modell herunter. Das dauert einige Minuten.
   Solange noch keine Version veröffentlicht ist, baust du das Image selbst: `docker compose up -d --build`.

4. **Einrichten:** `https://<dein-server>:8443` im Browser öffnen. Der Einrichtungsassistent führt durch
   den Rest. Den Einrichtungscode zeigt das Protokoll:

   ```bash
   docker compose logs app-api
   ```

5. **Neue Geräte:** Das Zertifikat stammt aus deinem eigenen Heimnetz, deshalb warnt der Browser
   einmalig. Auf `http://<dein-server>:8000/zertifikat` steht eine Anleitung mit QR-Code für iPhone,
   Android, Windows und Mac.

Ohne Docker läuft Famulus DMS auch direkt auf einem Windows-PC oder Linux-Server:
[Installation ohne Docker](docs/Installation-ohne-Docker.md).

## Aktualisieren

```bash
./scripts/update.sh          # Linux / NAS
.\scripts\update.cmd         # Windows
```

Das Skript sichert zuerst die Datenbank, holt die neue Version und prüft, ob alles wieder läuft.
Was sich geändert hat, steht im [Änderungsprotokoll](CHANGELOG.md). Rückweg und Hintergründe:
[docs/Updates.md](docs/Updates.md).

## Für Entwickler

| | |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, PostgreSQL, Procrastinate (Job-Queue) – [backend/README.md](backend/README.md) |
| Oberfläche | React, Mantine, Vite – [frontend/README.md](frontend/README.md) |
| Architektur | [docs/](docs/): Anforderungen, Datenmodell, API, Docker-Compose-Entwurf, Sicherheitskonzept |
| Tests | `cd backend && uv run --extra dev pytest` |

Fehler und Wünsche gern als [Issue](https://github.com/sschneidt/famulus-dms/issues).

## Lizenz

[MIT](LICENSE)
