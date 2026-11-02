# Ein Image fuer beide Rollen (api/worker), siehe docs/Docker-Compose-Entwurf.md Abschnitt 3 -
# der Start-Befehl unterscheidet sich nur ueber APP_ROLE (docker-entrypoint.sh).
#
# Build-Kontext ist das Repo-Wurzelverzeichnis (docker-compose.yml: context: .), damit auch die
# Weboberflaeche (frontend/) mitgebaut werden kann. Was NICHT ins Image darf (data/, .env, .git,
# node_modules ...), regelt die .dockerignore im Wurzelverzeichnis.

# --- Stufe 1: Weboberflaeche bauen (Node wird nur hier gebraucht, nicht im fertigen Image) -------
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
# Abhaengigkeiten zuerst (eigene Schicht, bleibt gecacht solange package-lock.json gleich ist)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stufe 2: Backend -----------------------------------------------------------------------
FROM python:3.12-slim-bookworm

# Tesseract + Sprachpakete fuer die drei Oberflaechensprachen (Deutsch, Englisch, Russisch).
# Weitere Sprachen laedt Famulus DMS bei Bedarf selbst nach (Seite "Sprachen", Volume tessdata). PyMuPDF, Pillow und
# psycopg[binary] brauchen dagegen KEINE weiteren System-Pakete (reine/vorkompilierte Wheels) -
# genau deshalb wurden sie so gewaehlt (Anforderungsdokument 4.7: "einfach installierbar").
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      tesseract-ocr-deu \
      tesseract-ocr-eng \
      tesseract-ocr-rus \
      tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/*

# pg_dump fuer die Datenbanksicherung aus der Anwendung (Seite "Diagnose"). Es muss mindestens so neu sein wie
# der Datenbankserver (pgvector/pgvector:pg16) - das Debian-Paket ist aelter, deshalb das offizielle PostgreSQL-
# Paketarchiv. Wer eine neuere Datenbank-Version einsetzt, erhoeht hier die Nummer.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -d /usr/share/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
ENV UV_HTTP_TIMEOUT=120

# 1) Nur die Abhaengigkeiten - aendern sich selten. Docker verwendet diese Schicht wieder, solange
#    pyproject.toml und uv.lock gleich bleiben: Code-Aenderungen bauen dann in Sekunden, statt jedes
#    Mal alle Pakete neu herunterzuladen. Installiert wird ueber die festen Download-Adressen aus
#    uv.lock, das Projekt selbst NICHT als Paket (sonst wuerde uv das Build-Werkzeug "hatchling"
#    live bei pypi.org nachschlagen - eine unnoetige Fehlerquelle bei wackliger Verbindung).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project

# 2) Der Code - wird ueber PYTHONPATH gefunden.
COPY backend/ ./

# 3) Die gebaute Weboberflaeche - FastAPI liefert sie unter / aus (homedms/frontend.py).
COPY --from=frontend /frontend/dist /app/frontend
ENV FRONTEND_DIST=/app/frontend

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONPATH=/app
ENV APP_ROLE=api

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
