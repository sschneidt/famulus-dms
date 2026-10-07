# Messages of update.sh and update.ps1 (language: German). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the script). Both scripts share this catalog. Every key must exist in all
# languages - the test backend/tests/test_installer_messages.py checks that.
label_error             = 'Fehler:'

help_1                  = 'Famulus DMS aktualisieren (Docker): Datenbank sichern, neue Version holen, neu starten, prüfen.'
help_2                  = '  --nur-sichern      nur die Datenbank sichern, nichts aktualisieren'
help_3                  = '  --ohne-sicherung   Sicherung überspringen (nicht empfohlen)'
help_4                  = '  --lang             Sprache: de, en oder ru (Standard: aus der Systemsprache)'
help_5                  = 'Die Sicherungen liegen in ./backups (die letzten 5 bleiben, BEHALTEN=n ändert das). Mehr: docs/Updates.md'

fail_unknown_option     = 'Unbekannte Option: {0}'
fail_docker_linux       = 'Docker läuft nicht (oder fehlende Rechte - ggf. mit sudo starten).'
fail_docker_windows     = 'Docker läuft nicht. Bitte Docker Desktop starten und noch einmal versuchen.'
fail_compose            = 'docker-compose.yml nicht gefunden (erwartet in {0}).'
fail_db_down            = 'Der Datenbank-Container läuft nicht. Erst mit ''docker compose up -d'' starten.'

step_version            = 'Installierte Version feststellen'
info_current            = 'Aktuell: {0}'
word_unknown            = 'unbekannt'

step_backup             = 'Datenbank sichern'
info_backup_skipped     = 'Sicherung übersprungen ({0}).'
fail_backup             = 'Die Datenbank konnte nicht gesichert werden. Es wurde nichts verändert.'
fail_backup_copy        = 'Die Sicherung konnte nicht kopiert werden. Es wurde nichts verändert.'
fail_backup_incomplete  = 'Die Sicherung ist unvollständig. Es wurde nichts verändert.'
info_backup_done        = 'Gesichert: {0}'
done_backup_only        = 'Fertig (nur gesichert).'

step_pull               = 'Neue Version herunterladen ({0})'
fail_pull               = 'Das Image konnte nicht geladen werden. Es läuft weiter die bisherige Version.'
step_git                = 'Neuen Stand holen (git pull)'
fail_git                = 'git pull ist fehlgeschlagen (lokale Änderungen?). Es läuft weiter die bisherige Version.'
info_no_git             = 'Kein Git-Ordner - es wird der Stand im Ordner gebaut.'

step_restart            = 'Famulus DMS neu starten'
fail_restart            = 'Der Neustart ist fehlgeschlagen.'
step_wait               = 'Warten, bis Famulus DMS wieder antwortet'
warn_not_ready          = 'Famulus DMS ist nach {0} Sekunden nicht bereit (Status: {1}).'
info_dump_location      = 'Deine Datenbank-Sicherung liegt in: {0}'
info_rollback           = 'So geht es zurück: docs/Updates.md, Abschnitt "Zurück zur alten Version".'

done_update             = 'Fertig. Version: {0} -> {1}'
