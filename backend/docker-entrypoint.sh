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
  # Dateien aus aelteren Versionen in die Ordnerstruktur Kategorie/Jahr bringen (nur Jobs einreihen,
  # der Worker verschiebt; bereits richtig abgelegte Dateien bleiben unberuehrt). Ein Fehler hier
  # darf den Start nicht verhindern.
  python -m homedms.cli refile || echo "Ablage konnte nicht eingereiht werden - weiter ohne."
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
