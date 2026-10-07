#!/usr/bin/env bash
# Famulus DMS auf einem Linux-Server installieren (Deutsch). Ohne Docker: sudo bash scripts/install-linux.de.sh
# Waehlt nur die Sprache - die Installation selbst steckt in install-linux.sh (Optionen: --ohne-ki --ohne-suche --ohne-dienst).
FAMULUS_LANG=de exec bash "$(dirname "${BASH_SOURCE[0]}")/install-linux.sh" "$@"
