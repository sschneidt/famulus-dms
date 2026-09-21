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
# Bewusst kein getrenntes "COPY pyproject.toml/uv.lock zuerst" fuer besseres Layer-Caching -
# haette bei diesem kleinen Projekt kaum Vorteile, macht das Dockerfile aber komplizierter.
COPY . .
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:${PATH}"
ENV APP_ROLE=api

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
