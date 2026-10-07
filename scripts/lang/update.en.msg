# Messages of update.sh and update.ps1 (language: English). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the script). Both scripts share this catalog. Every key must exist in all
# languages - the test backend/tests/test_installer_messages.py checks that.
label_error             = 'Error:'

help_1                  = 'Update Famulus DMS (Docker): back up the database, fetch the new version, restart, check.'
help_2                  = '  --backup-only    only back up the database, update nothing'
help_3                  = '  --no-backup      skip the backup (not recommended)'
help_4                  = '  --lang           language: de, en or ru (default: from the system locale)'
help_5                  = 'The backups go to ./backups (the latest 5 are kept, KEEP=n changes that). More: docs/Updates.md'

fail_unknown_option     = 'Unknown option: {0}'
fail_docker_linux       = 'Docker is not running (or permissions are missing - try with sudo).'
fail_docker_windows     = 'Docker is not running. Please start Docker Desktop and try again.'
fail_compose            = 'docker-compose.yml not found (expected in {0}).'
fail_db_down            = 'The database container is not running. Start it first with ''docker compose up -d''.'

step_version            = 'Checking the installed version'
info_current            = 'Current: {0}'
word_unknown            = 'unknown'

step_backup             = 'Backing up the database'
info_backup_skipped     = 'Backup skipped ({0}).'
fail_backup             = 'The database could not be backed up. Nothing was changed.'
fail_backup_copy        = 'The backup could not be copied. Nothing was changed.'
fail_backup_incomplete  = 'The backup is incomplete. Nothing was changed.'
info_backup_done        = 'Backed up: {0}'
done_backup_only        = 'Done (backup only).'

step_pull               = 'Downloading the new version ({0})'
fail_pull               = 'The image could not be downloaded. The previous version keeps running.'
step_git                = 'Fetching the latest code (git pull)'
fail_git                = 'git pull failed (local changes?). The previous version keeps running.'
info_no_git             = 'Not a Git folder - building the state of this folder.'

step_restart            = 'Restarting Famulus DMS'
fail_restart            = 'The restart failed.'
step_wait               = 'Waiting until Famulus DMS answers again'
warn_not_ready          = 'Famulus DMS is not ready after {0} seconds (status: {1}).'
info_dump_location      = 'Your database backup is in: {0}'
info_rollback           = 'How to go back: docs/Updates.md, section "Back to the old version".'

done_update             = 'Done. Version: {0} -> {1}'
