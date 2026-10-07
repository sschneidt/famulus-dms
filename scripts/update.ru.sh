#!/usr/bin/env bash
# Update Famulus DMS (Docker) - Russian. Options: --backup-only, --no-backup
# Only selects the language - the update itself is update.sh.
FAMULUS_LANG=ru exec bash "$(dirname "${BASH_SOURCE[0]}")/update.sh" "$@"
