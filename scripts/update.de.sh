#!/usr/bin/env bash
# Famulus DMS aktualisieren (Docker) - Deutsch. Optionen: --nur-sichern, --ohne-sicherung
# Waehlt nur die Sprache - das Update selbst steckt in update.sh.
FAMULUS_LANG=de exec bash "$(dirname "${BASH_SOURCE[0]}")/update.sh" "$@"
