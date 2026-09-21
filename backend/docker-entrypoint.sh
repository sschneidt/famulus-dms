#!/bin/sh
# Startet je nach APP_ROLE entweder den API- oder den Worker-Prozess (docker-compose.yml).
set -e

# Migrationen nur aus der api-Rolle heraus, nicht zusaetzlich aus worker - sonst koennten beide
# Container beim gleichzeitigen Start gegeneinander migrieren. "worker" kommt erst wirklich zum
# Einsatz, sobald ueber die API ein Job erzeugt wurde, also nachdem "api" laengst migriert hat.
# Anforderungsdokument 4.7: Migrationen laufen automatisch und verlustfrei beim Start.
if [ "$APP_ROLE" = "api" ]; then
  echo "Fuehre Datenbank-Migrationen aus (alembic upgrade head)..."
  alembic upgrade head
fi

case "$APP_ROLE" in
  api)
    exec uvicorn homedms.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec python -m homedms.worker
    ;;
  *)
    echo "Unbekannte APP_ROLE: '$APP_ROLE' (erwartet: api oder worker)" >&2
    exit 1
    ;;
esac
