#!/usr/bin/env bash
# Famulus DMS aktualisieren (Docker, Linux/NAS): Datenbank sichern, neue Version holen, neu starten, pruefen.
#
#   ./scripts/update.sh                 vollstaendiges Update
#   ./scripts/update.sh --nur-sichern   nur die Datenbank sichern
#   ./scripts/update.sh --ohne-sicherung
#
# Woher die neue Version kommt, entscheidet APP_IMAGE in der .env: Registry-Image (z. B. ghcr.io/...)
# -> "docker compose pull"; sonst aus dem Ordner bauen (bei einem Git-Ordner vorher "git pull").
# Daten, Dokumente und Suchindex bleiben unberuehrt; Datenbank-Aenderungen laufen beim Start
# automatisch. Zurueckgehen und Wiederherstellen: docs/Updates.md.
set -u

BEHALTEN="${BEHALTEN:-5}"
TIMEOUT="${TIMEOUT:-300}"
NUR_SICHERN=0
OHNE_SICHERUNG=0
for arg in "$@"; do
  case "$arg" in
    --nur-sichern) NUR_SICHERN=1 ;;
    --ohne-sicherung) OHNE_SICHERUNG=1 ;;
    *) echo "Unbekannte Angabe: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

fail() { echo; echo "FEHLER: $1" >&2; exit 1; }
step() { echo; echo "==> $1"; }

env_value() {  # Wert aus .env, ohne Kommentar am Zeilenende und ohne Anfuehrungszeichen
  [ -f .env ] || return 0
  grep -E "^[[:space:]]*$1=" .env | head -n1 | sed -E "s/^[[:space:]]*$1=//; s/[[:space:]]+#.*$//; s/^[\"']//; s/[\"']$//"
}

docker info >/dev/null 2>&1 || fail "Docker laeuft nicht (oder fehlende Rechte - ggf. mit sudo starten)."
[ -f docker-compose.yml ] || fail "docker-compose.yml nicht gefunden (erwartet in $ROOT)."
[ -n "$(docker compose ps -q db 2>/dev/null)" ] || fail "Der Datenbank-Container laeuft nicht. Erst mit 'docker compose up -d' starten."

step "Installierte Version feststellen"
BEFORE="$(docker compose exec -T app-api python -c 'import homedms; print(homedms.__version__)' 2>/dev/null | tr -d '\r\n')"
[ -n "$BEFORE" ] || BEFORE="unbekannt"
echo "Aktuell: $BEFORE"

DUMP=""
if [ "$OHNE_SICHERUNG" = 1 ] && [ "$NUR_SICHERN" = 0 ]; then
  echo "Sicherung uebersprungen (--ohne-sicherung)."
else
  step "Datenbank sichern"
  mkdir -p backups
  DUMP="$ROOT/backups/homedms-$BEFORE-$(date +%Y%m%d-%H%M%S).dump"
  docker compose exec -T db sh -c 'pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB -f /tmp/homedms.dump' \
    || fail "Die Datenbank konnte nicht gesichert werden. Es wurde nichts veraendert."
  docker compose cp db:/tmp/homedms.dump "$DUMP" || { docker compose exec -T db rm -f /tmp/homedms.dump; fail "Die Sicherung konnte nicht kopiert werden. Es wurde nichts veraendert."; }
  docker compose exec -T db rm -f /tmp/homedms.dump >/dev/null
  [ "$(wc -c < "$DUMP")" -ge 1024 ] || fail "Die Sicherung ist unvollstaendig. Es wurde nichts veraendert."
  echo "Gesichert: $DUMP"
  ls -1t backups/homedms-*.dump | tail -n +"$((BEHALTEN + 1))" | xargs -r rm -f
fi
if [ "$NUR_SICHERN" = 1 ]; then echo; echo "Fertig (nur gesichert)."; exit 0; fi

IMAGE="$(env_value APP_IMAGE)"
[ -n "$IMAGE" ] || IMAGE="ghcr.io/sschneidt/famulus-dms"  # Standard aus docker-compose.yml
if echo "$IMAGE" | grep -Eq '^[^/]+[.:][^/]*/'; then FROM_REGISTRY=1; else FROM_REGISTRY=0; fi

if [ "$FROM_REGISTRY" = 1 ]; then
  step "Neue Version herunterladen ($IMAGE)"
  docker compose pull app-api app-worker || fail "Das Image konnte nicht geladen werden. Es laeuft weiter die bisherige Version."
elif [ -d .git ] && command -v git >/dev/null 2>&1; then
  step "Neuen Stand holen (git pull)"
  git pull --ff-only || fail "git pull ist fehlgeschlagen (lokale Aenderungen?). Es laeuft weiter die bisherige Version."
else
  echo "Kein Git-Ordner - es wird der Stand im Ordner gebaut."
fi

step "Famulus DMS neu starten"
if [ "$FROM_REGISTRY" = 1 ]; then docker compose up -d; else docker compose up -d --build; fi || fail "Der Neustart ist fehlgeschlagen."

step "Warten, bis Famulus DMS wieder antwortet"
HEALTH=""
END=$(( $(date +%s) + TIMEOUT ))
while [ "$(date +%s)" -lt "$END" ]; do
  API_ID="$(docker compose ps -q app-api 2>/dev/null)"
  [ -n "$API_ID" ] && HEALTH="$(docker inspect -f '{{.State.Health.Status}}' "$API_ID" 2>/dev/null)"
  [ "$HEALTH" = healthy ] && break
  sleep 3
done
if [ "$HEALTH" != healthy ]; then
  docker compose logs --tail 40 app-api
  echo; echo "Famulus DMS ist nach $TIMEOUT Sekunden nicht bereit (Status: $HEALTH)." >&2
  [ -n "$DUMP" ] && echo "Deine Datenbank-Sicherung liegt in: $DUMP"
  echo "So geht es zurueck: docs/Updates.md, Abschnitt 'Zurueck zur alten Version'."
  exit 1
fi

AFTER="$(docker compose exec -T app-api python -c 'import homedms; print(homedms.__version__)' 2>/dev/null | tr -d '\r\n')"
echo; echo "Fertig. Version: $BEFORE -> ${AFTER:-unbekannt}"
