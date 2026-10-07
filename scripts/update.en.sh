#!/usr/bin/env bash
# Update Famulus DMS (Docker) - English. Options: --backup-only, --no-backup
# Only selects the language - the update itself is update.sh.
FAMULUS_LANG=en exec bash "$(dirname "${BASH_SOURCE[0]}")/update.sh" "$@"
