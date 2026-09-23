# HomeDMS Backend

FastAPI-Backend (Rolle `api`) und Hintergrund-Worker (Rolle `worker`) für HomeDMS -
siehe `/docs` im Repo-Root für die Architektur- und Anforderungsdokumente
(`Anforderungsdokument.md`, `Datenmodell.md`, `API-Design.md`, `Docker-Compose-Entwurf.md`).

Beide Rollen nutzen **dasselbe Image/denselben Code**, gesteuert über die Umgebungsvariable
`APP_ROLE` (`api` startet `uvicorn homedms.main:app`, `worker` startet `python -m homedms.worker`)
- siehe `docker-compose.yml` im Repo-Root.

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
  /documents/{id}/files*`), Tag-Zuordnung beim Update, Volltextsuche (`q`-Parameter, Meilisearch-
  Anbindung), Scan-Ordner-Import (Agent, siehe Anforderungsdokument 4.1).
- **Klassifikation:** zweistufige Pipeline (Stufe 1 Embedding/pgvector, Stufe 2
  Ollama-LLM als Zweitmeinung) inkl. Konfidenz-Schwellen aus `AIModelConfig` und
  Feedback-Loop bei Unsicherheit. `POST /documents/{id}/category` (manuelle Korrektur/Bestätigung)
  und `GET /documents/{id}/classification-history` fehlen noch.
- **Massen-Umkategorisierung** (`POST /documents/bulk-reclassify`) und Zugriffs-Ausnahmen verwalten
  (`GET/PUT /documents/{id}/access`) - Modelle (`DocumentAccessOverride`) existieren bereits, nur
  die Endpunkte dafür fehlen noch.
- **Metadaten-/Fristen-Extraktion** (LLM-Extraktion pro Dokument, Wiedervorlage-Vorschläge).
- **Wiedervorlagen/Termine** inkl. Wiederholungslogik und Zuweisung an Haushaltsmitglieder.
- **Aufbewahrungsregeln** (`RetentionRule`).
- **Import-Quellen** (Scan-Ordner-Überwachung, Konfiguration).
- **Benachrichtigungen** (In-App, E-Mail, Web-Push) inkl. `PushSubscription`-Verwaltung.
- **KI-Chat-Assistent** (`ChatSession`/`ChatMessage`, Bibliotheks-weite Fragen +
  Massen-Umkategorisierung).
- **KI-Konfiguration** (`/ai-config/*`, inkl. Modell-Download-Status für den
  Einrichtungsassistenten).
- **Rechte-Feinsteuerung:** `CategoryAccess`/`DocumentAccessOverride` sind im Datenmodell
  vorhanden, aber noch nicht in den Endpunkten/der Zugriffsprüfung verdrahtet.
- **Frontend-Ausgabe:** `StaticFiles`-Mount für die gebaute PWA (sobald das Frontend existiert).
- **Einrichtungsassistent im Detail** (Schrittfolge/Felder über `POST /setup/bootstrap`
  hinaus, siehe `docs/Anforderungsdokument.md` 4.7 - noch offen).
- **Row-Level-Security** in Postgres als zweite Absicherung der Mandantentrennung (die
  Trennung auf API-Ebene ist durch die Integrationstests abgedeckt).

## Bekannter Punkt zur lokalen Entwicklungsumgebung

Falls beim lokalen `uv sync` Probleme mit einem bereits vorhandenen, unvollständigen
`.venv`-Ordner auftreten: einfach `backend/.venv` löschen und `uv sync --extra dev` erneut
laufen lassen - `uv` legt das virtuelle Environment dann sauber neu an
(`UV_PROJECT_ENVIRONMENT` kann optional gesetzt werden, um den venv-Pfad zu steuern).
