# Docker-Compose-Entwurf: HomeDMS

Stand: 10.09.2026 · Version 0.1 · Basis: `Anforderungsdokument.md`, `Datenmodell.md`, `API-Design.md`

Dieses Dokument erklärt die Container-Struktur (`docker-compose.yml`, `.env.example`, `init/postgres-extensions.sql` – alle drei Dateien liegen daneben) und löst dabei den letzten offenen Punkt aus dem Anforderungsdokument (Abschnitt 7): die Wahl der Job-Queue-Technologie.

## 1. Container-Übersicht

| Container | Zweck | Läuft dauerhaft? | Nach außen sichtbar? |
|---|---|---|---|
| `db` | PostgreSQL + `pgvector` + `pg_trgm` | ja, leichtgewichtig | nein, nur intern |
| `meilisearch` | Volltextsuche | ja, leichtgewichtig | nein, nur intern |
| `ollama` | Lokales KI-Modell (Server-Prozess) | ja, leichtgewichtig; Modell selbst nur bei Bedarf im RAM | nein, nur intern |
| `ollama-init` | Lädt beim ersten Start die konfigurierten Modelle herunter, beendet sich danach | nein, einmalig | nein |
| `app-api` | FastAPI-Backend + ausgelieferte PWA-Frontend-Dateien | ja, leichtgewichtig | **ja**, einziger veröffentlichter Port |
| `app-worker` | OCR, Klassifikation, Extraktion, Wiedervorlage-Wiederholungen, Benachrichtigungs-Versand | ja, aber rechenintensive Arbeit nur on-demand | nein |

Das sind 5 dauerhafte Container plus ein einmaliger Init-Job – passend zum in 4.7 festgelegten Ressourcenschema: alles außer `app-worker`s tatsächlicher Verarbeitung und `ollama`s Modell-Inferenz ist im Leerlauf minimal.

**Warum kein separater Frontend-Container?** Die gebaute PWA (React/Vue) wird als statische Dateien direkt vom `app-api`-Container mitausgeliefert (FastAPI `StaticFiles`) – ein Container weniger, ohne Funktionalität zu verlieren.

**Warum kein Reverse-Proxy-Container im Standard-Setup?** Nur `app-api` veröffentlicht einen Port zum NAS-Host. Da auf dem NAS bereits Docker/Container Manager läuft (Anforderungsdokument 2), zeigt Synologys **eigener, bereits vorhandener Reverse Proxy** (DSM-Systemsteuerung → Anmeldeportal → Erweiterter Reverse Proxy) auf diesen Port und übernimmt HTTPS/TLS – kostet keinen zusätzlichen Container und nutzt vorhandene NAS-Bordmittel. Für Nutzer ohne Synology (oder ohne Lust auf DSM-Klicks) ließe sich optional ein Caddy-Container als eigenes Compose-Profil ergänzen; im Basis-Setup bewusst weggelassen.

## 2. Die Job-Queue-Entscheidung (offener Punkt aus Anforderungsdokument 7)

Statt Celery/RQ mit zusätzlichem Redis-Container läuft die Job-Queue **direkt über PostgreSQL** (z. B. mit der Python-Bibliothek `Procrastinate`, die genau dafür gebaut ist: Jobs liegen in einer normalen Tabelle, `SELECT … FOR UPDATE SKIP LOCKED` verteilt sie sicher an `app-worker`). Bei dem geplanten Volumen (< 50 Dokumente/Monat) ist die Zusatzlast auf der ohnehin vorhandenen Datenbank vernachlässigbar, und es entfällt ein kompletter Dienst samt eigenem Volume und Betriebsaufwand. Damit sind es 5 statt 6 dauerhafte Container.

## 3. `app-api` und `app-worker`: ein Image, zwei Rollen

Beide Container nutzen **dasselbe Docker-Image**, gesteuert über die Umgebungsvariable `APP_ROLE` (`api` vs. `worker`). Das bedeutet: ein Build, ein Versions-Tag, keine zwei Codebasen zu pflegen – nur der Start-Befehl im Image unterscheidet sich intern. Das hält auch spätere Updates einfach (siehe 5.).

## 4. Volumes & Speicherorte

| Volume/Pfad | Typ | Inhalt |
|---|---|---|
| `pgdata` | benanntes Docker-Volume | Datenbank (Dokumente-Metadaten, Kategorien, Wiedervorlagen, Klassifikations-Exemplare …) |
| `meilidata` | benanntes Docker-Volume | Such-Index |
| `ollama_models` | benanntes Docker-Volume | heruntergeladene KI-Modelle (Chat + Embedding) |
| `DOCUMENTS_PATH` (`.env`) | Bind-Mount auf NAS-Ordner | die eigentlichen Dokument-Dateien – bewusst ein normaler NAS-Ordner, nicht in einem Docker-Volume versteckt, damit er z. B. über Synology File Station einsehbar bleibt (Anforderungsdokument 4.4) und von Hyper Backup erfasst wird |
| `SCAN_FOLDER_PATH` (`.env`) | Bind-Mount auf NAS-Ordner, read-only | der überwachte Scan-Ordner (Anforderungsdokument 4.1) |

Für die geforderte Update-Sicherheit (Anforderungsdokument 4.7: "Daten, Archiv und Suchindex dürfen bei Updates nie verloren gehen") reicht es, dass ein `docker compose pull && docker compose up -d` diese Volumes/Bind-Mounts unangetastet lässt – ein Image-Update ersetzt nur die Container, nicht deren Daten. Nötige Datenbank-Schema-Migrationen laufen automatisch beim Start von `app-api` (z. B. per Alembic, siehe Datenmodell Abschnitt 6).

## 5. Erststart & Betrieb

1. `.env.example` nach `.env` kopieren, die mit `CHANGE_ME` markierten Werte setzen (Passwörter, Suche-Master-Key, JWT-Secret) sowie `DOCUMENTS_PATH`/`SCAN_FOLDER_PATH` auf echte NAS-Ordner zeigen lassen.
2. `docker compose up -d` – `ollama-init` lädt danach automatisch die konfigurierten Modelle herunter (Fortschritt einsehbar über `GET /ai-config/model-status`, siehe API-Design 10), alles andere ist sofort betriebsbereit.
3. Web-UI unter dem konfigurierten Port/der Domain öffnen → Einrichtungsassistent (`POST /setup/bootstrap`, siehe API-Design 2) übernimmt den Rest.
4. **Update:** `docker compose pull && docker compose up -d`. Volumes/Bind-Mounts bleiben unangetastet, Migrationen laufen automatisch.

## 6. Offene Punkte für die nächste Iteration

- ~~Konkrete Basis-Images für `app-api`/`app-worker`~~ – erledigt: `backend/Dockerfile`
  (Basis `python:3.12-slim-bookworm`, inkl. Tesseract + Sprachpaketen deu/eng für die
  OCR-Pipeline) + `backend/docker-entrypoint.sh` (verzweigt nach `APP_ROLE`). Noch offen: ein
  Multi-Stage-Build-Schritt fürs PWA-Frontend, sobald das existiert (aktuell nur Backend).
- Ressourcen-Limits (`mem_limit`/`cpus`) als optionale, aber empfohlene Werte pro Container – abhängig vom finalen Synology-Modell des Nutzers.
- Registry/Verteilung der fertigen Images (eigenes GHCR-Repository vs. lokal bauen) – `docker-compose.yml` hat jetzt `build: ./backend` neben `image:`, sodass `docker compose up` bis dahin lokal baut, ohne dass Endnutzer manuell etwas umstellen müssen.
- Automatisiertes Backup-Hook-Skript, das vor einem Update einen Datenbank-Dump zusätzlich zu Hyper Backup anlegt (zusätzliche Sicherheitsebene, nicht zwingend).
