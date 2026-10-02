# HomeDMS Backend

FastAPI-Backend (Rolle `api`) und Hintergrund-Worker (Rolle `worker`) für HomeDMS -
siehe `/docs` im Repo-Root für die Architektur- und Anforderungsdokumente
(`Anforderungsdokument.md`, `Datenmodell.md`, `API-Design.md`, `Docker-Compose-Entwurf.md`).

Beide Rollen nutzen **dasselbe Image/denselben Code**, gesteuert über die Umgebungsvariable
`APP_ROLE` (`api` startet `uvicorn homedms.main:app`, `worker` startet `python -m homedms.worker`)
- siehe `docker-compose.yml` im Repo-Root.

## Weboberfläche

Die Oberfläche liegt in `../frontend` (React + Mantine, installierbar als App auf Handy und
Desktop). Das Docker-Image baut sie mit (mehrstufiges `Dockerfile`, Build-Kontext ist das
Repo-Wurzelverzeichnis) und dieses Backend liefert sie unter `/` aus (`homedms/frontend.py`):
nach `docker compose up -d --build` einfach `http://<nas>:8000` im Browser öffnen.

Ohne Docker sucht das Backend den Build unter `FRONTEND_DIST` (Standard `../frontend/dist`,
also nach `npm run build` im Frontend-Ordner). Fehlt er, läuft nur die API. Für die
Frontend-Entwicklung mit Live-Reload siehe `../frontend/README.md`.

## Ablage auf dem NAS

Dateien liegen im Dokumente-Ordner (`DOCUMENTS_PATH`) lesbar sortiert, z. B. für File Station:

```
Familie Muster/
  Haus & Reparaturen/
    Stuttgart Musterstraße 5/        <- ein Ordner je Objekt (Adresse)
      2026/
        2026-09-12 Sanitär Müller GmbH – Rechnung Wasserschaden-Reparatur.pdf
  Steuern/
    2026/
      2026-03-01 Finanzamt Stuttgart – Einkommensteuerbescheid 2025.pdf
  _Unsortiert/2026/   (noch keine Kategorie)
  _Papierkorb/
```

- **Titel in der App:** „Betreff – Absender“; ein selbst vergebener Titel wird nie überschrieben
  (in der App über den Zauberstab wieder auf automatisch umstellbar).
- **Dateiname:** „JJJJ-MM-TT Absender – Betreff“, bei Namensgleichheit „ (2)“.
- **Objekt-Ordner** für „Haus & Reparaturen“, „Wohnen & Nebenkosten“ und Gebäude-/Hausrat-
  Versicherungen (`categories.property_mode`). Objekte legt HomeDMS aus erkannten Adressen selbst an
  (Absenderadressen aus Briefkopf/Fußzeile werden verworfen); umbenennen/zusammenführen unter
  „Objekte“ in der App.
- Die Datenbank bleibt führend; die Ordner werden bei jeder Änderung vom Worker nachgezogen
  (`homedms/core/filing.py`). Beim Start des API-Containers wird die Ablage für alle Dokumente
  einmal eingereiht, manuell: `docker compose exec app-api python -m homedms.cli refile`.
- **Bitte Dateien nicht direkt in File Station umbenennen oder verschieben** – HomeDMS findet sie
  sonst nicht mehr. Änderungen immer über die App.

## Scan-Ordner

Der Worker holt jede Minute neue Dateien aus `SCAN_FOLDER_PATH` ab (PDF, JPG, PNG, TIFF, HEIC,
.eml; auch aus Unterordnern) und importiert sie als Dokumente des Haushalts. Halb geschriebene
Dateien werden abgewartet, doppelte Inhalte nicht erneut importiert. Originale landen danach in
`_importiert/JJJJ-MM/`, Unbrauchbares in `_fehler/JJJJ-MM/`. Logik: `homedms/core/scanfolder.py`,
Job: `homedms/tasks/scanfolder.py`, Verwaltung: `/api/v1/import-sources` bzw. „Scan-Ordner“ in der App.

## Lokale Entwicklung

Paketverwaltung über [`uv`](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync --extra dev
cp .env.example .env   # ggf. anpassen, falls DB/Meilisearch/Ollama nicht auf localhost laufen
```

Für Migrationen und den vollen Stack wird eine laufende Postgres-Instanz mit den Extensions
`vector` und `pg_trgm` benötigt (siehe `docker-compose.yml`/`init/postgres-extensions.sql`
im Repo-Root - am einfachsten testet man lokal mit `docker compose up -d db`).

**Wichtig:** `docker-compose.yml` veröffentlicht standardmäßig **keinen** Port für `db`
(nur `app-api` ist nach außen sichtbar, siehe `docs/Docker-Compose-Entwurf.md`). Für
Backend-Entwicklung direkt auf dem Host (Alembic/uvicorn/pytest außerhalb von Docker)
liegt im Repo-Root zusätzlich eine `docker-compose.override.yml`, die Postgres auf
`localhost:5432` veröffentlicht - Docker Compose lädt sie automatisch mit, kein
Extra-Flag nötig. Falls stattdessen der volle Stack per Compose läuft, wird sie nicht
gebraucht (dann läuft alles im selben Docker-Netzwerk).

```bash
uv run alembic upgrade head        # Schema anlegen
uv run uvicorn homedms.main:app --reload --port 8000
uv run python -m homedms.worker    # in einem zweiten Terminal, optional
```

`DATABASE_URL` darf wahlweise als `postgresql://...` oder `postgresql+asyncpg://...`
angegeben werden - `homedms.config.Settings` normalisiert intern automatisch auf den
jeweils passenden Treiber (`+asyncpg` für SQLAlchemy/Alembic, reines `postgresql://` für
Procrastinate/psycopg, siehe `sqlalchemy_database_url`/`procrastinate_database_url`).

## Smoke-Test: kompletter Ablauf mit einem Befehl (Windows)

Startet den Stack und prüft automatisch Anmeldung, Upload, Texterkennung (PDF und Scan),
Download und Papierkorb - mit einer OK/FEHLER-Übersicht am Ende. Aus dem Repo-Root:

```
.\scripts\smoke-test.cmd -Email du@example.com -Password "DeinPasswort123"
```

- Gibt es noch keinen Haushalt, legt das Skript ihn mit diesen Zugangsdaten an.
- Passwort vergessen: zusätzlich `-PasswortZuruecksetzen` angeben, dann wird es vorher gesetzt.
- `-OhneBuild` spart den Image-Neubau, `-DokumenteBehalten` lässt die Testdokumente stehen
  (sonst landen sie im Papierkorb), `-TimeoutSekunden 300` für langsame Rechner/NAS.
- Die `.cmd`-Datei ruft `scripts/smoke-test.ps1` auf und umgeht dabei die
  PowerShell-Ausführungsrichtlinie nur für diesen einen Aufruf.

## Verwaltung: Nutzer anzeigen, Passwort zurücksetzen

Für den Fall "Admin-Passwort vergessen" (es gibt noch keinen Reset per E-Mail):

```bash
docker compose exec app-api python -m homedms.cli users
docker compose exec app-api python -m homedms.cli reset-password <email>
```

`reset-password` fragt das neue Passwort verdeckt ab (mindestens 8 Zeichen) und beendet alle
bestehenden Anmeldungen dieses Nutzers. Lokal ohne Docker: `uv run python -m homedms.cli ...`.

## Tests

```bash
uv run pytest
```

**Unit-Tests** (`backend/tests/`) laufen ohne Datenbank: App-Aufbau/Routing, Sicherheits-
Bausteine (Passwort-Hashing, JWT), Sichtbarkeits-SQL, Dateiablage, Worker-Verkabelung und die
OCR-Extraktion (mit echtem Tesseract, siehe `tests/test_ocr.py`).

**Integrationstests** (`backend/tests/integration/`) laufen gegen eine echte PostgreSQL mit
`pgvector` + `pg_trgm` und spielen den kompletten Ablauf durch: Ersteinrichtung, Login, Upload,
OCR-Job in der Queue, Abarbeitung durch den Worker, Sichtbarkeitsregeln, Mandantentrennung,
Papierkorb und Download. Sie **leeren vorher alle Tabellen** der Zieldatenbank und laufen deshalb
nur, wenn man sie ausdrücklich einschaltet *und* der Datenbankname auf `_test` endet:

```bash
# einmalig eine eigene Test-Datenbank im laufenden db-Container anlegen
docker compose exec db createdb -U homedms homedms_test

# PowerShell
$env:HOMEDMS_INTEGRATION_TESTS="1"
$env:DATABASE_URL="postgresql://homedms:<POSTGRES_PASSWORD>@localhost:5432/homedms_test"
uv run pytest tests/integration
```

Das Schema legen die Tests selbst per `alembic upgrade head` an - sie prüfen damit also auch die
Migrationen.

## Migrationen

`alembic/versions/0001_initial.py` ist der eingefrorene Anfangsstand als explizite
Tabellendefinitionen. **Schema-Änderungen gehören ausschließlich in neue Migrationen**, am
einfachsten per `uv run alembic revision --autogenerate -m "..."` gegen eine Dev-Datenbank auf
dem aktuellen Stand, danach das Ergebnis prüfen. `0002` legt das Schema der Job-Queue
Procrastinate an (feste Kopie, deshalb ist Procrastinate auf 3.9.x gepinnt - beim Anheben der
Version eine neue Migration mit den Delta-Skripten aus `procrastinate/sql/migrations/`
ergänzen). `0003` stellt alle Zeitstempel auf "mit Zeitzone" um.

## Was ist implementiert

- **App-Grundgerüst:** FastAPI-App (`homedms/main.py`), Konfiguration über Env-Variablen
  (`homedms/config.py`), async SQLAlchemy-Engine (`homedms/db.py`).
- **Datenmodell:** alle 20 Tabellen aus `docs/Datenmodell.md` als SQLAlchemy-2.0-Modelle
  (`homedms/models/`), inkl. `pgvector`-Spalte für Klassifikations-Exemplare und
  Soft-Delete (`Document.deleted_at`).
- **Migrationen:** Alembic ist verkabelt (`alembic/`), drei Migrationen (Anfangsschema,
  Job-Queue-Schema, Zeitstempel-Korrektur) - siehe Abschnitt "Migrationen". Sie laufen beim Start
  des `app-api`-Containers automatisch (`docker-entrypoint.sh`).
- **Auth:** `POST /api/v1/auth/login`, `/auth/refresh` (mit Rotation der Refresh-Tokens),
  `/auth/logout`, `GET /auth/me` - JWT (Access+Refresh), Argon2-Passwort-Hashing,
  server-seitig widerrufbare Refresh-Tokens (`RefreshToken`-Tabelle).
- **Einrichtung:** `GET /api/v1/setup/status`, `POST /api/v1/setup/bootstrap` (legt
  einmalig Tenant + ersten Admin-User + das Basis-Kategorien-Set an, siehe
  `docs/Anforderungsdokument.md` 4.3).
- **Kategorien:** `GET/POST /api/v1/categories` als Referenz-Pattern für Tenant-gescopte
  CRUD-Endpunkte (weitere Ressourcen folgen nach demselben Muster).
- **Dokumente (Kernfunktionen):** `GET/POST /api/v1/documents` (Liste mit Pagination/Filtern
  `category_id`/`status`/`date_from`/`date_to`, sowie Multipart-Upload - deckt Foto-Import und
  manuellen Upload über denselben Endpunkt ab, siehe Anforderungsdokument 4.1), `GET/PATCH
  /documents/{id}`, `DELETE /documents/{id}` + `POST /documents/{id}/restore` (Soft-Delete/
  Papierkorb, Datenmodell 3.5), `GET /documents/trash`, `GET /documents/needs-review`, `GET
  /documents/{id}/download`. Dateien landen unter `DOCUMENTS_PATH/<tenant>/<jahr>/<dokument-id>/`
  (`homedms/core/storage.py`).
- **Sichtbarkeitsmodell:** `homedms/core/visibility.py` setzt die Rechte-Regeln aus Datenmodell 3.6
  um (Admin/Owner/`CategoryAccess`/`DocumentAccessOverride`) und wendet sie auf alle
  Dokumente-Endpunkte an (Listen werden gefiltert, direkter Zugriff per ID liefert `403`, siehe
  API-Design 1).
- **OCR-Pipeline** (`homedms/tasks/ocr.py`, Anforderungsdokument 4.2): Nach jedem Upload wird
  automatisch ein `ocr_document`-Job eingereiht (Procrastinate/`homedms/jobs.py`), den der
  `app-worker`-Prozess ausführt. Abgedeckt: PDF mit eingebettetem Text (direkte Extraktion, kein
  OCR nötig), gescanntes PDF (Rasterung + Tesseract), Bilder (JPG/PNG/TIFF/HEIC direkt per
  Tesseract), E-Mails (.eml, Klartext-Body). **Noch nicht abgedeckt:** Office-Dokumente
  (Word/Excel) und Outlook `.msg` - solche Uploads werden erkannt und explizit mit
  `ocr_status=failed` markiert statt stillschweigend leer zu bleiben.
- **Klassifikation** (Anforderungsdokument 4.3): Nach der Texterkennung ordnet
  `classify_document` (`homedms/tasks/classification.py`) jedes Dokument automatisch einer
  Kategorie zu. **Stufe 1** vergleicht den Text per Embedding (`nomic-embed-text`, pgvector) mit
  bestätigten Beispiel-Dokumenten; ab 5 Beispielen einer Kategorie und eindeutiger Ähnlichkeit
  entscheidet sie ohne Sprachmodell. Sonst entscheidet **Stufe 2**, das lokale Sprachmodell
  (Ollama), anhand der Kategorie-Beschreibungen. Ist es unsicher oder nicht erreichbar, landet
  das Dokument im **Feedback-Loop** (`GET /documents/needs-review`). Jede übernommene oder
  bestätigte Zuordnung wird sofort ein neues Lernbeispiel; Korrekturen ersetzen es.
  Schwellenwerte je nach `AI_CAUTION_LEVEL` (vorsichtig/normal/mutig) in `homedms/ai/classifier.py`.
  Endpunkte: `POST /documents/{id}/category` (manuell zuordnen/bestätigen),
  `GET /documents/{id}/classification-history` (alle Entscheidungen mit Begründung).
- **Metadaten und Fristen** (Anforderungsdokument 4.4a): `extract_metadata`
  (`homedms/tasks/extraction.py`) liest nach der Texterkennung per Sprachmodell Dokumentdatum,
  Absender und Betrag aus (füllt nur leere Felder, Korrekturen per `PATCH /documents/{id}`) und
  schlägt erkannte Fristen als Wiedervorlagen mit Status `vorgeschlagen` vor. Schutzregeln in
  `homedms/ai/extraction.py`: Konfidenz ≥ 50 %, die zitierte Textstelle muss im Dokument stehen,
  vergangene einmalige Termine entfallen, wiederkehrende rücken auf den nächsten Termin, keine
  Doppel-Vorschläge. Eigener Modell-Aufruf statt kombiniert mit der Klassifikation – kleine
  Modelle antworten mit einer Aufgabe je Aufruf zuverlässiger.
- **Wiedervorlagen** (Anforderungsdokument 4.4a): `GET /wiedervorlagen` (Übersicht, Filter
  `status`, `due_before`), `GET/POST /documents/{id}/wiedervorlagen`, `PATCH`/`DELETE
  /wiedervorlagen/{id}` (KI-Vorschläge lassen sich vor dem Bestätigen korrigieren),
  `POST .../confirm`, `/reject`, `/complete`. Beim Erledigen einer wiederkehrenden Wiedervorlage
  entsteht sofort der nächste Termin; wurde zu spät erledigt, der nächste in der Zukunft (keine
  Reihe verpasster Termine). Regeln in `homedms/core/wiedervorlage.py`.
- **Aufbewahrungsregeln** (`/retention-rules`, nur Admin, eine je Kategorie): erzeugen automatisch
  eine Wiedervorlage "Aufbewahrungsfrist endet", sobald ein Dokument Kategorie und Datum hat, und
  passen sie an, wenn sich Kategorie, Dokumentdatum oder Regel ändern (`homedms/core/retention.py`).
  Bewusst ohne vorbelegte Regeln – welche Fristen gelten, entscheidet der Haushalt.
- **`backend/Dockerfile` + `docker-entrypoint.sh`:** Ein Image für `app-api`/`app-worker`
  (unterscheidet sich nur über `APP_ROLE`, siehe Docker-Compose-Entwurf.md Abschnitt 3), inkl.
  Tesseract + Sprachpaketen (deu+eng). `docker-compose.yml` im Repo-Root nutzt jetzt `build:
  ./backend`, der volle Stack lässt sich also lokal mit `docker compose up -d` bauen und
  starten, nicht mehr nur `db` einzeln.
- **Worker-Grundgerüst:** `homedms/worker.py` mit einer Procrastinate-`App`
  (PostgreSQL-basierte Job-Queue, kein Redis nötig - siehe
  `docs/Docker-Compose-Entwurf.md` Abschnitt 2) und einem Platzhalter-Task (`ping`), der
  die Verkabelung (DB-Verbindung, Worker-Start) end-to-end beweist.
- **Tests:** siehe oben.

## Was noch fehlt (nächste Schritte)

Die übrigen Endpunkte aus `docs/API-Design.md` folgen schrittweise, u. a.:

- **Dokumente (Rest):** Mehrseiten-Dateien hinzufügen/entfernen (`POST/DELETE
  /documents/{id}/files*`), Tag-Zuordnung beim Update, optionaler Client-Agent für PC-Ordner
  (Anforderungsdokument 4.1).
- **KI (Rest):** KI-Einstellungen per API (`/ai-config`), Kalibrierung der Schwellenwerte an
  echten Dokumenten, erneute Verarbeitung auf Knopfdruck (z. B. nach einem KI-Ausfall), Ablage
  der Dateien nach Kategorie.
- **Erinnerungen:** fällige Wiedervorlagen (`reminder_lead_days` vorher) über Benachrichtigungen
  melden (In-App, E-Mail, Web-Push) - siehe Benachrichtigungen.
- **Massen-Umkategorisierung** (`POST /documents/bulk-reclassify`) und Zugriffs-Ausnahmen verwalten
  (`GET/PUT /documents/{id}/access`) - Modelle (`DocumentAccessOverride`) existieren bereits, nur
  die Endpunkte dafür fehlen noch.
- **Benachrichtigungen** (In-App, E-Mail, Web-Push) inkl. `PushSubscription`-Verwaltung.
- **KI-Chat-Assistent** (`ChatSession`/`ChatMessage`, Bibliotheks-weite Fragen +
  Massen-Umkategorisierung).
- **KI-Konfiguration** (`/ai-config/*`, inkl. Modell-Download-Status für den
  Einrichtungsassistenten).
- **Rechte-Feinsteuerung:** `CategoryAccess`/`DocumentAccessOverride` sind im Datenmodell
  vorhanden, aber noch nicht in den Endpunkten/der Zugriffsprüfung verdrahtet.
- **Einrichtungsassistent im Detail** (Schrittfolge/Felder über `POST /setup/bootstrap`
  hinaus, siehe `docs/Anforderungsdokument.md` 4.7 - noch offen).
- **Row-Level-Security** in Postgres als zweite Absicherung der Mandantentrennung (die
  Trennung auf API-Ebene ist durch die Integrationstests abgedeckt).

## Bekannter Punkt zur lokalen Entwicklungsumgebung

Falls beim lokalen `uv sync` Probleme mit einem bereits vorhandenen, unvollständigen
`.venv`-Ordner auftreten: einfach `backend/.venv` löschen und `uv sync --extra dev` erneut
laufen lassen - `uv` legt das virtuelle Environment dann sauber neu an
(`UV_PROJECT_ENVIRONMENT` kann optional gesetzt werden, um den venv-Pfad zu steuern).
