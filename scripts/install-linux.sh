#!/usr/bin/env bash
# Install Famulus DMS on a Linux server WITHOUT Docker (Debian 12+, Ubuntu 22.04+).
#
#   sudo bash scripts/install-linux.sh                  installation or update, language from the system locale
#   sudo bash scripts/install-linux.en.sh               English   (also install-linux.de.sh = Deutsch, install-linux.ru.sh = Russian)
#   sudo bash scripts/install-linux.sh --no-ai          without Ollama (automatic classification stays off)
#   sudo bash scripts/install-linux.sh --no-search      without Meilisearch (search only through the database)
#   sudo bash scripts/install-linux.sh --no-service     do not set up a systemd service (e.g. WSL/container);
#                                                       start by hand, see the output at the end
#   sudo bash scripts/install-linux.sh --lang de|en|ru  language of the installation
#
# The German option names --ohne-ki, --ohne-suche and --ohne-dienst still work.
#
# The Famulus DMS folder (this repository) stays where it is - /opt/homedms is recommended. The script can be
# run again at any time (e.g. after an update): existing settings, database and documents stay untouched.
# All texts shown come from scripts/lang/install-linux.<language>.msg (English is the fallback).
#
# What happens:
#  1. Packages: PostgreSQL, Tesseract (German/English/Russian), curl
#  2. Tools in <Famulus DMS>/.tools: uv + Python 3.12, Node.js (only to build the web interface), Meilisearch
#  3. Ollama + language models (official install script from ollama.com)
#  4. Database "homedms" with its own user and a random password
#  5. Settings file homedms.env (random keys), data below /var/lib/homedms
#  6. Service "homedms" (systemd): starts at boot, restarts after a crash
set -euo pipefail

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
i18n_init install-linux

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m%s %s\033[0m\n' "$(t label_error)" "$*" >&2; exit 1; }
usage() { local k; for k in help_1 help_2 help_3 help_4 help_5 help_6; do echo "$(t "$k")"; done; }

WITH_AI=1
WITH_SEARCH=1
WITH_SERVICE=1
skip_next=0
for arg in "${args[@]}"; do
  if [ "$skip_next" -eq 1 ]; then skip_next=0; continue; fi
  case "$arg" in
    --no-ai|--ohne-ki) WITH_AI=0 ;;
    --no-search|--ohne-suche) WITH_SEARCH=0 ;;
    --no-service|--ohne-dienst) WITH_SERVICE=0 ;;
    --lang) skip_next=1 ;;
    --lang=*) ;;
    -h|--help) usage; exit 0 ;;
    *) die "$(t fail_unknown_option "$arg")" ;;
  esac
done

APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${HOMEDMS_DATA:-/var/lib/homedms}"
TOOLS="$APP_DIR/.tools"
ENV_FILE="$APP_DIR/homedms.env"
SERVICE_USER=homedms
NODE_MAJOR=22
MEILI_VERSION="${MEILI_VERSION:-v1.10.3}"   # same as in the Docker setup (getmeili/meilisearch:v1.10)
CHAT_MODEL="${OLLAMA_CHAT_MODEL:-llama3.2:3b}"
EMBED_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"

secret() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-40}"; }

# Address of this server in the home network: the source address of the route to the internet (not the
# first address of "hostname -I", which may belong to docker0 or a bridge)
lan_address() {
  local addr
  addr="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -n1 || true)"
  [ -n "$addr" ] || addr="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  echo "$addr"
}

[ "$(id -u)" -eq 0 ] || die "$(t fail_root "$0")"
command -v apt-get >/dev/null || die "$(t fail_apt)"
[ -f "$APP_DIR/backend/pyproject.toml" ] || die "$(t fail_appdir "$APP_DIR")"

case "$(uname -m)" in
  x86_64) ARCH_NODE=x64; ARCH_MEILI=amd64 ;;
  aarch64|arm64) ARCH_NODE=arm64; ARCH_MEILI=aarch64 ;;
  *) die "$(t fail_cpu "$(uname -m)")" ;;
esac

# --- 1. Packages ----------------------------------------------------------------------------
step "$(t step_packages)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql postgresql-contrib tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
  tesseract-ocr-rus tesseract-ocr-osd curl ca-certificates xz-utils >/dev/null
systemctl enable --now postgresql >/dev/null

# --- 2. Tools -------------------------------------------------------------------------------
mkdir -p "$TOOLS"
export UV_PYTHON_INSTALL_DIR="$TOOLS/python" UV_CACHE_DIR="$TOOLS/uv-cache" UV_LINK_MODE=copy
if [ ! -x "$TOOLS/uv" ]; then
  step "$(t step_uv)"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$TOOLS" UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
fi
step "$(t step_python)"
(cd "$APP_DIR/backend" && "$TOOLS/uv" sync --frozen --no-dev --python 3.12 --quiet)

node_ok() { command -v "$1" >/dev/null && [ "$("$1" -p 'process.versions.node.split(".")[0]')" -ge "$NODE_MAJOR" ]; }
NODE=node
if ! node_ok node; then
  NODE="$TOOLS/node/bin/node"
  if ! node_ok "$NODE"; then
    step "$(t step_node "$NODE_MAJOR")"
    file=$(curl -fsSL "https://nodejs.org/dist/latest-v$NODE_MAJOR.x/SHASUMS256.txt" | grep -o "node-v[0-9.]*-linux-$ARCH_NODE.tar.xz" | head -1)
    rm -rf "$TOOLS/node" && mkdir -p "$TOOLS/node"
    curl -fsSL "https://nodejs.org/dist/latest-v$NODE_MAJOR.x/$file" | tar -xJ -C "$TOOLS/node" --strip-components=1
  fi
fi
step "$(t step_build)"
(cd "$APP_DIR/frontend" && PATH="$(dirname "$NODE"):$PATH" npm ci --no-audit --no-fund --silent && PATH="$(dirname "$NODE"):$PATH" npm run build --silent >/dev/null)

MEILI_BIN=""
if [ "$WITH_SEARCH" -eq 1 ]; then
  MEILI_BIN="$TOOLS/meilisearch-$MEILI_VERSION"
  if [ ! -x "$MEILI_BIN" ]; then
    step "$(t step_meili "$MEILI_VERSION")"
    curl -fsSL -o "$MEILI_BIN" "https://github.com/meilisearch/meilisearch/releases/download/$MEILI_VERSION/meilisearch-linux-$ARCH_MEILI"
    chmod +x "$MEILI_BIN"
  fi
fi

# --- 3. Ollama ------------------------------------------------------------------------------
if [ "$WITH_AI" -eq 1 ]; then
  if ! command -v ollama >/dev/null; then
    step "$(t step_ollama)"
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  [ "$WITH_SERVICE" -eq 1 ] && { systemctl enable --now ollama >/dev/null 2>&1 || true; }
  step "$(t step_models "$CHAT_MODEL" "$EMBED_MODEL")"
  for _ in $(seq 1 30); do curl -fs http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
  ollama pull "$CHAT_MODEL" && ollama pull "$EMBED_MODEL" || warn "$(t warn_models "$CHAT_MODEL")"
fi

# --- 4./5. User, folders, settings, database ------------------------------------------------
id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
# The service runs as user "homedms" and must be able to read the program folder
if ! runuser -u "$SERVICE_USER" -- test -r "$APP_DIR/backend/homedms/server.py"; then
  die "$(t fail_unreadable "$SERVICE_USER" "$APP_DIR")"
fi
mkdir -p "$DATA_DIR"/{documents,scan,logs,meilisearch,tls}

if [ ! -f "$ENV_FILE" ]; then
  step "$(t step_settings "$ENV_FILE")"
  DB_PASSWORD=$(secret 32)
  # settings template in the installation language (homedms.env.<language>.example), English as the fallback
  TEMPLATE="$APP_DIR/homedms.env.$(i18n_language).example"
  [ -f "$TEMPLATE" ] || TEMPLATE="$APP_DIR/homedms.env.example"
  sed -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://homedms:$DB_PASSWORD@127.0.0.1:5432/homedms|" \
      -e "s|^OLLAMA_URL=.*|OLLAMA_URL=http://127.0.0.1:11434|" \
      -e "s|^JWT_SECRET=.*|JWT_SECRET=$(secret 64)|" \
      -e "s|^MEILISEARCH_KEY=.*|MEILISEARCH_KEY=$(secret 40)|" \
      -e "s|^DOCUMENTS_PATH=.*|DOCUMENTS_PATH=$DATA_DIR/documents|" \
      -e "s|^SCAN_PATH=.*|SCAN_PATH=$DATA_DIR/scan|" \
      -e "s|^LOG_DIR=.*|LOG_DIR=$DATA_DIR/logs|" \
      -e "s|^MEILISEARCH_DATA=.*|MEILISEARCH_DATA=$DATA_DIR/meilisearch|" \
      -e "s|^TLS_DIR=.*|TLS_DIR=$DATA_DIR/tls|" \
      -e "s|^TESSDATA_DIR=.*|TESSDATA_DIR=$DATA_DIR/tessdata|" \
      -e "s|^SETUP_CODE=.*|SETUP_CODE=$(secret 12 | sed 's/.\{4\}/&-/g; s/-$//')|" \
      "$TEMPLATE" > "$ENV_FILE"
else
  DB_PASSWORD=$(sed -n 's|^DATABASE_URL=postgresql://[^:]*:\([^@]*\)@.*|\1|p' "$ENV_FILE")
fi
# Search: switch on or off according to the option (an existing file is only changed here)
if [ "$WITH_SEARCH" -eq 1 ]; then
  sed -i -e "s|^MEILISEARCH_BINARY=.*|MEILISEARCH_BINARY=$MEILI_BIN|" -e "s|^MEILISEARCH_URL=$|MEILISEARCH_URL=http://127.0.0.1:7700|" "$ENV_FILE"
else
  sed -i -e "s|^MEILISEARCH_BINARY=.*|MEILISEARCH_BINARY=|" -e "s|^MEILISEARCH_URL=.*|MEILISEARCH_URL=|" "$ENV_FILE"
fi
chmod 640 "$ENV_FILE"
chown root:"$SERVICE_USER" "$ENV_FILE"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$DATA_DIR"
chmod 700 "$DATA_DIR/tls"

step "$(t step_database)"
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='homedms'" | grep -q 1; then
  runuser -u postgres -- psql -qc "CREATE ROLE homedms LOGIN PASSWORD '$DB_PASSWORD'"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='homedms'" | grep -q 1; then
  runuser -u postgres -- psql -qc "CREATE DATABASE homedms OWNER homedms ENCODING 'UTF8' TEMPLATE template0"
fi
runuser -u postgres -- psql -d homedms -qc "SET client_min_messages = warning; CREATE EXTENSION IF NOT EXISTS pg_trgm"

# --- 6. Service -----------------------------------------------------------------------------
if [ "$WITH_SERVICE" -eq 0 ]; then
  step "$(t step_done_no_service)"
  echo "   sudo -u $SERVICE_USER env HOMEDMS_ENV=$ENV_FILE $APP_DIR/backend/.venv/bin/python -m homedms.server"
  exit 0
fi
step "$(t step_service)"
cat > /etc/systemd/system/homedms.service <<UNIT
[Unit]
Description=Famulus DMS - document management
After=network-online.target postgresql.service ollama.service
Wants=network-online.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR/backend
Environment=HOMEDMS_ENV=$ENV_FILE
ExecStart=$APP_DIR/backend/.venv/bin/python -m homedms.server
Restart=on-failure
RestartSec=5
# On stop, the worker and Meilisearch get time to shut down cleanly
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable homedms >/dev/null
systemctl restart homedms

PORT=$(sed -n 's/^PORT=//p' "$ENV_FILE"); PORT=${PORT:-8000}
HTTPS_PORT=$(sed -n 's/^HTTPS_PORT=//p' "$ENV_FILE"); HTTPS_PORT=${HTTPS_PORT:-8443}
# 127.0.0.1 instead of "localhost": the server listens on IPv4, "localhost" may be tried as IPv6 (::1) first
for _ in $(seq 1 60); do curl -fs "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 1; done
if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then
  ADDRESS="$(lan_address)"
  ADDRESS="${ADDRESS:-localhost}"
  step "$(t step_done "$ADDRESS" "$HTTPS_PORT")"
  echo "$(t info_trust_1 "$ADDRESS" "$PORT")"
  echo "$(t info_trust_2)"
  echo "$(t info_wizard "$ADDRESS" "$HTTPS_PORT")"
  SETUP_CODE=$(sed -n 's/^SETUP_CODE=//p' "$ENV_FILE")
  if [ -n "$SETUP_CODE" ] && ! runuser -u postgres -- psql -d homedms -tAc "SELECT 1 FROM tenants LIMIT 1" 2>/dev/null | grep -q 1; then
    echo "$(t info_code "$SETUP_CODE")"
  fi
  echo "$(t info_paths "$DATA_DIR/documents" "$DATA_DIR/scan" "$DATA_DIR/logs")"
  echo "$(t info_service)"
else
  warn "$(t warn_no_response "$DATA_DIR/logs/homedms.log")"
  exit 1
fi
