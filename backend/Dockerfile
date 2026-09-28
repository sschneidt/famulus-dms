# Ein Image fuer beide Rollen (api/worker), siehe docs/Docker-Compose-Entwurf.md Abschnitt 3 -
# der Start-Befehl unterscheidet sich nur ueber APP_ROLE (docker-entrypoint.sh). Kein
# Multi-Stage-Build noetig, solange es noch kein PWA-Frontend zum Bauen gibt (README "Was noch
# fehlt").
FROM python:3.12-slim-bookworm

# Tesseract + Sprachpakete (Anforderungsdokument 4.2: Primaersprachen Deutsch + Englisch,
# weitere Sprachen als Module nachruestbar - einfach hier ergaenzen). PyMuPDF, Pillow und
# psycopg[binary] brauchen dagegen KEINE weiteren System-Pakete (reine/vorkompilierte Wheels) -
# genau deshalb wurden sie so gewaehlt (Anforderungsdokument 4.7: "einfach installierbar").
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      tesseract-ocr-deu \
      tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
ENV UV_HTTP_TIMEOUT=120

# 1) Nur die Abhaengigkeiten - aendern sich selten. Docker verwendet diese Schicht wieder, solange
#    pyproject.toml und uv.lock gleich bleiben: Code-Aenderungen bauen dann in Sekunden, statt jedes
#    Mal alle Pakete neu herunterzuladen. Installiert wird ueber die festen Download-Adressen aus
#    uv.lock, das Projekt selbst NICHT als Paket (sonst wuerde uv das Build-Werkzeug "hatchling"
#    live bei pypi.org nachschlagen - eine unnoetige Fehlerquelle bei wackliger Verbindung).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 2) Der Code - wird ueber PYTHONPATH gefunden.
COPY . .

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONPATH=/app
ENV APP_ROLE=api

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
