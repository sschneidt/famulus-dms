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
im Repo-Root - am einfachsten testet man lokal mit `docker compose up db`).

```bash
uv run alembic upgrade head        # Schema anlegen
uv run uvicorn homedms.main:app --reload --port 8000
uv run python -m homedms.worker    # in einem zweiten Terminal, optional
```

`DATABASE_URL` darf wahlweise als `postgresql://...` oder `postgresql+asyncpg://...`
angegeben werden - `homedms.config.Settings` normalisiert intern automatisch auf den
jeweils passenden Treiber (`+asyncpg` für SQLAlchemy/Alembic, reines `postgresql://` für
Procrastinate/psycopg, siehe `sqlalchemy_database_url`/`procrastinate_database_url`).

## Tests

```bash
uv run pytest
```

Alle aktuell vorhandenen Tests (`backend/tests/`) laufen **ohne laufende Datenbank** - sie
prüfen App-Aufbau/Routing, die Sicherheits-Bausteine (Passwort-Hashing, JWT) sowie die
Worker-Verkabelung (Procrastinate-App, DATABASE_URL-Normalisierung). Endpunkte, die
tatsächlich eine DB-Session ausführen (`/setup/bootstrap`, `/auth/*`, `/categories`), sind
bewusst noch nicht getestet - das braucht eine echte Postgres-Verbindung (z. B.
`docker compose up db` + Alembic-Migration) und folgt in einer späteren Iteration
(Integrationstests mit `pytest-asyncio` + Test-DB/Testcontainers).

## Was ist implementiert

- **App-Grundgerüst:** FastAPI-App (`homedms/main.py`), Konfiguration über Env-Variablen
  (`homedms/config.py`), async SQLAlchemy-Engine (`homedms/db.py`).
- **Datenmodell:** alle 20 Tabellen aus `docs/Datenmodell.md` als SQLAlchemy-2.0-Modelle
  (`homedms/models/`), inkl. `pgvector`-Spalte für Klassifikations-Exemplare und
  Soft-Delete (`Document.deleted_at`).
- **Migrationen:** Alembic ist verkabelt (`alembic/`); die erste Migration (`0001_initial`)
  erzeugt die Extensions (`vector`, `pg_trgm`) und das komplette Schema über
  `Base.metadata.create_all()`. Das ist ein bewusster Kompromiss, weil in der
  Entwicklungsumgebung, in der dieses Grundgerüst entstanden ist, keine laufende
  Postgres-Instanz verfügbar war, um `alembic revision --autogenerate` gegen eine echte DB
  laufen zu lassen. **Vor dem ersten produktiven Einsatz:** einmal `alembic upgrade head`
  gegen eine echte Dev-Datenbank laufen lassen und prüfen, dass das Schema exakt
  `docs/Datenmodell.md` entspricht. Alle Migrationen danach sollten regulär per
  `alembic revision --autogenerate -m "..."` gegen eine laufende Dev-DB erzeugt werden.
- **Auth:** `POST /api/v1/auth/login`, `/auth/refresh` (mit Rotation der Refresh-Tokens),
  `/auth/logout`, `GET /auth/me` - JWT (Access+Refresh), Argon2-Passwort-Hashing,
  server-seitig widerrufbare Refresh-Tokens (`RefreshToken`-Tabelle).
- **Einrichtung:** `GET /api/v1/setup/status`, `POST /api/v1/setup/bootstrap` (legt
  einmalig Tenant + ersten Admin-User + das Basis-Kategorien-Set an, siehe
  `docs/Anforderungsdokument.md` 4.3).
- **Kategorien:** `GET/POST /api/v1/categories` als Referenz-Pattern für Tenant-gescopte
  CRUD-Endpunkte (weitere Ressourcen folgen nach demselben Muster).
- **Worker-Grundgerüst:** `homedms/worker.py` mit einer Procrastinate-`App`
  (PostgreSQL-basierte Job-Queue, kein Redis nötig - siehe
  `docs/Docker-Compose-Entwurf.md` Abschnitt 2) und einem Platzhalter-Task (`ping`), der
  die Verkabelung (DB-Verbindung, Worker-Start) end-to-end beweist.
- **Tests:** siehe oben.

## Was noch fehlt (nächste Schritte)

Die übrigen ca. 60 Endpunkte aus `docs/API-Design.md` folgen schrittweise, u. a.:

- **Dokumente:** Upload (App-Foto, manueller Upload, Scan-Ordner-Import), Abruf, Trash/Restore
  (`/documents/trash`, `/documents/{id}/restore`), Datei-Download.
- **OCR-Pipeline** (Hintergrund-Task im Worker, Tesseract).
- **Klassifikation:** zweistufige Pipeline (Stufe 1 Embedding/pgvector, Stufe 2
  Ollama-LLM als Zweitmeinung) inkl. Konfidenz-Schwellen aus `AIModelConfig` und
  Feedback-Loop bei Unsicherheit.
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
- **Integrationstests** gegen eine echte Postgres-Instanz (Setup/Bootstrap, Login-Flow,
  Tenant-Isolation, RLS).

## Bekannter Punkt zur lokalen Entwicklungsumgebung

Falls beim lokalen `uv sync` Probleme mit einem bereits vorhandenen, unvollständigen
`.venv`-Ordner auftreten: einfach `backend/.venv` löschen und `uv sync --extra dev` erneut
laufen lassen - `uv` legt das virtuelle Environment dann sauber neu an
(`UV_PROJECT_ENVIRONMENT` kann optional gesetzt werden, um den venv-Pfad zu steuern).
