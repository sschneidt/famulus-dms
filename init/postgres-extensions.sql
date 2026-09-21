-- Wird beim allerersten Start des db-Containers automatisch ausgeführt
-- (Postgres-Image führt alles in /docker-entrypoint-initdb.d/ genau einmal aus,
-- beim ersten Anlegen des Datenverzeichnisses).

CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector: Klassifikations-Exemplare (Datenmodell 3.7)
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- Fallback-/Ergänzungs-Volltextsuche (Anforderungsdokument 4.4)
