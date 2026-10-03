#!/usr/bin/env bash
# HomeDMS auf einem Linux-Server installieren - OHNE Docker (Debian 12+, Ubuntu 22.04+).
#
#   sudo bash scripts/install-linux.sh                 Installation bzw. Aktualisierung
#   sudo bash scripts/install-linux.sh --ohne-ki       ohne Ollama (KI-Einordnung bleibt aus)
#   sudo bash scripts/install-linux.sh --ohne-suche    ohne Meilisearch (Suche nur ueber die Datenbank)
#   sudo bash scripts/install-linux.sh --ohne-dienst   keinen systemd-Dienst einrichten (z. B. WSL/Container);
#                                                   Start dann von Hand, siehe Ausgabe am Ende
#
# Der HomeDMS-Ordner (dieses Repository) bleibt, wo er ist - empfohlen /opt/homedms. Das Skript
# kann jederzeit erneut laufen (z. B. nach einem Update): Vorhandene Einstellungen, Datenbank und
# Dokumente bleiben unberuehrt.
#
# Was passiert:
#  1. Pakete: PostgreSQL, Tesseract (Deutsch/Englisch), curl
#  2. Werkzeuge in <HomeDMS>/.tools: uv + Python 3.12, Node.js (nur zum Bauen der Oberflaeche),
#     Meilisearch
#  3. Ollama + Sprachmodelle (offizielles Installationsskript von ollama.com)
#  4. Datenbank "homedms" mit eigenem Benutzer und Zufallspasswort
#  5. Einstellungen homedms.env (Zufallsschluessel), Daten unter /var/lib/homedms
#  6. Dienst "homedms" (systemd): startet beim Hochfahren, startet bei Absturz neu
set -euo pipefail

WITH_AI=1
WITH_SEARCH=1
WITH_SERVICE=1
for arg in "$@"; do
  case "$arg" in
    --ohne-ki) WITH_AI=0 ;;
    --ohne-suche) WITH_SEARCH=0 ;;
    --ohne-dienst) WITH_SERVICE=0 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 1 ;;
  esac
done

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${HOMEDMS_DATA:-/var/lib/homedms}"
TOOLS="$APP_DIR/.tools"
ENV_FILE="$APP_DIR/homedms.env"
SERVICE_USER=homedms
NODE_MAJOR=22
MEILI_VERSION="${MEILI_VERSION:-v1.10.3}"   # wie im Docker-Betrieb (getmeili/meilisearch:v1.10)
CHAT_MODEL="${OLLAMA_CHAT_MODEL:-llama3.2:3b}"
EMBED_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31mFehler: %s\033[0m\n' "$*" >&2; exit 1; }
secret() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-40}"; }

[ "$(id -u)" -eq 0 ] || die "Bitte mit sudo starten: sudo bash $0"
command -v apt-get >/dev/null || die "Dieses Skript unterstuetzt Debian/Ubuntu (apt). Andere Systeme: docs/Installation-ohne-Docker.md"
[ -f "$APP_DIR/backend/pyproject.toml" ] || die "$APP_DIR sieht nicht wie der HomeDMS-Ordner aus"

case "$(uname -m)" in
  x86_64) ARCH_NODE=x64; ARCH_MEILI=amd64 ;;
  aarch64|arm64) ARCH_NODE=arm64; ARCH_MEILI=aarch64 ;;
  *) die "Prozessor $(uname -m) wird nicht unterstuetzt" ;;
esac

# --- 1. Pakete ------------------------------------------------------------------------------
step "Pakete installieren (PostgreSQL, Tesseract)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql postgresql-contrib tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
  tesseract-ocr-osd curl ca-certificates xz-utils >/dev/null
systemctl enable --now postgresql >/dev/null

# --- 2. Werkzeuge ---------------------------------------------------------------------------
mkdir -p "$TOOLS"
export UV_PYTHON_INSTALL_DIR="$TOOLS/python" UV_CACHE_DIR="$TOOLS/uv-cache" UV_LINK_MODE=copy
if [ ! -x "$TOOLS/uv" ]; then
  step "uv (Python-Paketverwaltung) laden"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$TOOLS" UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
fi
step "Python-Umgebung einrichten (backend/.venv)"
(cd "$APP_DIR/backend" && "$TOOLS/uv" sync --frozen --no-dev --python 3.12 --quiet)

node_ok() { command -v "$1" >/dev/null && [ "$("$1" -p 'process.versions.node.split(".")[0]')" -ge "$NODE_MAJOR" ]; }
NODE=node
if ! node_ok node; then
  NODE="$TOOLS/node/bin/node"
  if ! node_ok "$NODE"; then
    step "Node.js $NODE_MAJOR laden (nur zum Bauen der Weboberflaeche)"
    file=$(curl -fsSL "https://nodejs.org/dist/latest-v$NODE_MAJOR.x/SHASUMS256.txt" | grep -o "node-v[0-9.]*-linux-$ARCH_NODE.tar.xz" | head -1)
    rm -rf "$TOOLS/node" && mkdir -p "$TOOLS/node"
    curl -fsSL "https://nodejs.org/dist/latest-v$NODE_MAJOR.x/$file" | tar -xJ -C "$TOOLS/node" --strip-components=1
  fi
fi
step "Weboberflaeche bauen"
(cd "$APP_DIR/frontend" && PATH="$(dirname "$NODE"):$PATH" npm ci --no-audit --no-fund --silent && PATH="$(dirname "$NODE"):$PATH" npm run build --silent >/dev/null)

MEILI_BIN=""
if [ "$WITH_SEARCH" -eq 1 ]; then
  MEILI_BIN="$TOOLS/meilisearch-$MEILI_VERSION"
  if [ ! -x "$MEILI_BIN" ]; then
    step "Meilisearch $MEILI_VERSION laden"
    curl -fsSL -o "$MEILI_BIN" "https://github.com/meilisearch/meilisearch/releases/download/$MEILI_VERSION/meilisearch-linux-$ARCH_MEILI"
    chmod +x "$MEILI_BIN"
  fi
fi

# --- 3. Ollama ------------------------------------------------------------------------------
if [ "$WITH_AI" -eq 1 ]; then
  if ! command -v ollama >/dev/null; then
    step "Ollama installieren"
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  [ "$WITH_SERVICE" -eq 1 ] && { systemctl enable --now ollama >/dev/null 2>&1 || true; }
  step "Sprachmodelle laden ($CHAT_MODEL, $EMBED_MODEL) - beim ersten Mal einige GB"
  for _ in $(seq 1 30); do curl -fs http://localhost:11434/api/version >/dev/null && break; sleep 1; done
  ollama pull "$CHAT_MODEL" && ollama pull "$EMBED_MODEL" || warn "Modelle konnten nicht geladen werden - spaeter: ollama pull $CHAT_MODEL"
fi

# --- 4./5. Benutzer, Ordner, Einstellungen, Datenbank ---------------------------------------
id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
# Der Dienst laeuft als Benutzer "homedms" und muss den Programmordner lesen koennen
if ! runuser -u "$SERVICE_USER" -- test -r "$APP_DIR/backend/homedms/server.py"; then
  die "Benutzer $SERVICE_USER kann $APP_DIR nicht lesen (z. B. weil er in einem Home-Ordner liegt). Ordner nach /opt/homedms verschieben und dort erneut starten."
fi
mkdir -p "$DATA_DIR"/{documents,scan,logs,meilisearch}

if [ ! -f "$ENV_FILE" ]; then
  step "Einstellungen anlegen ($ENV_FILE)"
  DB_PASSWORD=$(secret 32)
  sed -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://homedms:$DB_PASSWORD@localhost:5432/homedms|" \
      -e "s|^JWT_SECRET=.*|JWT_SECRET=$(secret 64)|" \
      -e "s|^MEILISEARCH_KEY=.*|MEILISEARCH_KEY=$(secret 40)|" \
      -e "s|^DOCUMENTS_PATH=.*|DOCUMENTS_PATH=$DATA_DIR/documents|" \
      -e "s|^SCAN_PATH=.*|SCAN_PATH=$DATA_DIR/scan|" \
      -e "s|^LOG_DIR=.*|LOG_DIR=$DATA_DIR/logs|" \
      -e "s|^MEILISEARCH_DATA=.*|MEILISEARCH_DATA=$DATA_DIR/meilisearch|" \
      "$APP_DIR/homedms.env.example" > "$ENV_FILE"
else
  DB_PASSWORD=$(sed -n 's|^DATABASE_URL=postgresql://[^:]*:\([^@]*\)@.*|\1|p' "$ENV_FILE")
fi
# Suche: an-/abschalten je nach Option (vorhandene Datei wird nur an dieser Stelle angepasst)
if [ "$WITH_SEARCH" -eq 1 ]; then
  sed -i -e "s|^MEILISEARCH_BINARY=.*|MEILISEARCH_BINARY=$MEILI_BIN|" -e "s|^MEILISEARCH_URL=$|MEILISEARCH_URL=http://127.0.0.1:7700|" "$ENV_FILE"
else
  sed -i -e "s|^MEILISEARCH_BINARY=.*|MEILISEARCH_BINARY=|" -e "s|^MEILISEARCH_URL=.*|MEILISEARCH_URL=|" "$ENV_FILE"
fi
chmod 640 "$ENV_FILE"
chown root:"$SERVICE_USER" "$ENV_FILE"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$DATA_DIR"

step "Datenbank einrichten"
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='homedms'" | grep -q 1; then
  runuser -u postgres -- psql -qc "CREATE ROLE homedms LOGIN PASSWORD '$DB_PASSWORD'"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='homedms'" | grep -q 1; then
  runuser -u postgres -- psql -qc "CREATE DATABASE homedms OWNER homedms ENCODING 'UTF8' TEMPLATE template0"
fi
runuser -u postgres -- psql -d homedms -qc "CREATE EXTENSION IF NOT EXISTS pg_trgm"

# --- 6. Dienst ------------------------------------------------------------------------------
if [ "$WITH_SERVICE" -eq 0 ]; then
  step "Fertig (ohne Dienst). Starten mit:"
  echo "   sudo -u $SERVICE_USER env HOMEDMS_ENV=$ENV_FILE $APP_DIR/backend/.venv/bin/python -m homedms.server"
  exit 0
fi
step "Dienst einrichten (systemd: homedms)"
cat > /etc/systemd/system/homedms.service <<UNIT
[Unit]
Description=HomeDMS - Dokumentenverwaltung
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
# Beim Stoppen bekommen Worker und Meilisearch Zeit zum sauberen Beenden
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable homedms >/dev/null
systemctl restart homedms

PORT=$(sed -n 's/^PORT=//p' "$ENV_FILE"); PORT=${PORT:-8000}
for _ in $(seq 1 60); do curl -fs "http://localhost:$PORT/health" >/dev/null && break; sleep 1; done
if curl -fs "http://localhost:$PORT/health" >/dev/null; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  step "Fertig! HomeDMS laeuft: http://${IP:-localhost}:$PORT"
  echo "   Beim ersten Aufruf fuehrt ein Assistent durch die Einrichtung (Haushalt + Admin-Konto)."
  echo "   Dokumente: $DATA_DIR/documents   Scan-Ordner: $DATA_DIR/scan   Protokoll: $DATA_DIR/logs"
  echo "   Dienst: systemctl status homedms   |   Update: Ordner aktualisieren, dieses Skript erneut starten"
else
  warn "HomeDMS antwortet nicht - Protokoll: journalctl -u homedms -n 50  bzw.  $DATA_DIR/logs/homedms.log"
  exit 1
fi
