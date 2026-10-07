#!/usr/bin/env bash
# Install Famulus DMS on a Linux server (English). Without Docker: sudo bash scripts/install-linux.en.sh
# Only selects the language - the installation itself is install-linux.sh (options: --no-ai --no-search --no-service).
FAMULUS_LANG=en exec bash "$(dirname "${BASH_SOURCE[0]}")/install-linux.sh" "$@"
