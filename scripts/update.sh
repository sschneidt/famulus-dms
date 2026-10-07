#!/usr/bin/env bash
# Update Famulus DMS (Docker, Linux/NAS): back up the database, fetch the new version, restart, check.
#
#   ./scripts/update.sh                  full update (language from the system locale)
#   ./scripts/update.en.sh               English   (also update.de.sh = Deutsch, update.ru.sh = Russian)
#   ./scripts/update.sh --backup-only    only back up the database
#   ./scripts/update.sh --no-backup
#   ./scripts/update.sh --lang de|en|ru  language
#
# The German option names --nur-sichern and --ohne-sicherung still work.
#
# Where the new version comes from depends on APP_IMAGE in .env: a registry image (e.g. ghcr.io/...)
# -> "docker compose pull"; otherwise it is built from the folder (with a "git pull" first in a Git folder).
# Data, documents and the search index stay untouched; database changes run automatically at start.
# Going back and restoring: docs/Updates.md. All texts: scripts/lang/update.<language>.msg.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The language first, so that every message below is shown in the chosen language
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[$i]}" in
    --lang=*) FAMULUS_LANG="${args[$i]#--lang=}" ;;
    --lang) FAMULUS_LANG="${args[$((i + 1))]:-}" ;;
  esac
done
export FAMULUS_LANG="${FAMULUS_LANG:-}"
# shellcheck source=lib/i18n.sh
source "$SCRIPT_DIR/lib/i18n.sh"
i18n_init update

KEEP="${KEEP:-${BEHALTEN:-5}}"      # BEHALTEN = former name
TIMEOUT="${TIMEOUT:-300}"
BACKUP_ONLY=0
NO_BACKUP=0
skip_next=0
for arg in "${args[@]}"; do
  if [ "$skip_next" -eq 1 ]; then skip_next=0; continue; fi
  case "$arg" in
    --backup-only|--nur-sichern) BACKUP_ONLY=1 ;;
    --no-backup|--ohne-sicherung) NO_BACKUP=1 ;;
    --lang) skip_next=1 ;;
    --lang=*) ;;
    -h|--help) for k in help_1 help_2 help_3 help_4 help_5; do echo "$(t "$k")"; done; exit 0 ;;
    *) echo "$(t label_error) $(t fail_unknown_option "$arg")" >&2; exit 2 ;;
  esac
done

cd "$SCRIPT_DIR/.."
ROOT="$(pwd)"

fail() { echo; echo "$(t label_error) $1" >&2; exit 1; }
step() { echo; echo "==> $1"; }

env_value() {  # value from .env, without a comment at the end of the line and without quotes
  [ -f .env ] || return 0
  grep -E "^[[:space:]]*$1=" .env | head -n1 | sed -E "s/^[[:space:]]*$1=//; s/[[:space:]]+#.*$//; s/^[\"']//; s/[\"']$//"
}

docker info >/dev/null 2>&1 || fail "$(t fail_docker_linux)"
[ -f docker-compose.yml ] || fail "$(t fail_compose "$ROOT")"
[ -n "$(docker compose ps -q db 2>/dev/null)" ] || fail "$(t fail_db_down)"

step "$(t step_version)"
BEFORE="$(docker compose exec -T app-api python -c 'import homedms; print(homedms.__version__)' 2>/dev/null | tr -d '\r\n')"
echo "$(t info_current "${BEFORE:-$(t word_unknown)}")"

DUMP=""
if [ "$NO_BACKUP" = 1 ] && [ "$BACKUP_ONLY" = 0 ]; then
  echo "$(t info_backup_skipped --no-backup)"
else
  step "$(t step_backup)"
  mkdir -p backups
  DUMP="$ROOT/backups/homedms-${BEFORE:-unknown}-$(date +%Y%m%d-%H%M%S).dump"
  docker compose exec -T db sh -c 'pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB -f /tmp/homedms.dump' \
    || fail "$(t fail_backup)"
  docker compose cp db:/tmp/homedms.dump "$DUMP" || { docker compose exec -T db rm -f /tmp/homedms.dump; fail "$(t fail_backup_copy)"; }
  docker compose exec -T db rm -f /tmp/homedms.dump >/dev/null
  [ "$(wc -c < "$DUMP")" -ge 1024 ] || fail "$(t fail_backup_incomplete)"
  echo "$(t info_backup_done "$DUMP")"
  ls -1t backups/homedms-*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm -f
fi
if [ "$BACKUP_ONLY" = 1 ]; then echo; echo "$(t done_backup_only)"; exit 0; fi

IMAGE="$(env_value APP_IMAGE)"
[ -n "$IMAGE" ] || IMAGE="ghcr.io/sschneidt/famulus-dms"  # default from docker-compose.yml
if echo "$IMAGE" | grep -Eq '^[^/]+[.:][^/]*/'; then FROM_REGISTRY=1; else FROM_REGISTRY=0; fi

if [ "$FROM_REGISTRY" = 1 ]; then
  step "$(t step_pull "$IMAGE")"
  docker compose pull app-api app-worker || fail "$(t fail_pull)"
elif [ -d .git ] && command -v git >/dev/null 2>&1; then
  step "$(t step_git)"
  git pull --ff-only || fail "$(t fail_git)"
else
  echo "$(t info_no_git)"
fi

step "$(t step_restart)"
if [ "$FROM_REGISTRY" = 1 ]; then docker compose up -d; else docker compose up -d --build; fi || fail "$(t fail_restart)"

step "$(t step_wait)"
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
  echo; echo "$(t warn_not_ready "$TIMEOUT" "$HEALTH")" >&2
  [ -n "$DUMP" ] && echo "$(t info_dump_location "$DUMP")"
  echo "$(t info_rollback)"
  exit 1
fi

AFTER="$(docker compose exec -T app-api python -c 'import homedms; print(homedms.__version__)' 2>/dev/null | tr -d '\r\n')"
echo; echo "$(t done_update "${BEFORE:-$(t word_unknown)}" "${AFTER:-$(t word_unknown)}")"
