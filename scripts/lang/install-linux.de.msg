# Messages of install-linux.sh (language: German). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the script). Every key must exist in all languages - the test
# backend/tests/test_installer_messages.py checks that.
label_error          = 'Fehler:'

help_1               = 'Famulus DMS auf einem Linux-Server ohne Docker installieren (Debian 12+, Ubuntu 22.04+).'
help_2               = '  sudo bash scripts/install-linux.sh [--ohne-ki] [--ohne-suche] [--ohne-dienst] [--lang de|en|ru]'
help_3               = '  --ohne-ki      ohne Ollama (die automatische Einordnung bleibt aus)'
help_4               = '  --ohne-suche   ohne Meilisearch (Suche nur über die Datenbank)'
help_5               = '  --ohne-dienst  keinen systemd-Dienst einrichten (z. B. WSL/Container); Start von Hand, siehe Ende der Ausgabe'
help_6               = '  --lang         Sprache der Installation: de, en oder ru (Standard: aus der Systemsprache)'

fail_unknown_option  = 'Unbekannte Option: {0}'
fail_root            = 'Bitte mit sudo starten: sudo bash {0}'
fail_apt             = 'Dieses Skript unterstützt Debian/Ubuntu (apt). Andere Systeme: docs/Installation-ohne-Docker.md'
fail_appdir          = '{0} sieht nicht wie der Famulus-DMS-Ordner aus'
fail_cpu             = 'Prozessor {0} wird nicht unterstützt'
fail_unreadable      = 'Benutzer {0} kann {1} nicht lesen (z. B. weil er in einem Home-Ordner liegt). Ordner nach /opt/homedms verschieben und dort erneut starten.'

step_packages        = 'Pakete installieren (PostgreSQL, Tesseract)'
step_uv              = 'uv (Python-Paketverwaltung) laden'
step_python          = 'Python-Umgebung einrichten (backend/.venv)'
step_node            = 'Node.js {0} laden (nur zum Bauen der Weboberfläche)'
step_build           = 'Weboberfläche bauen'
step_meili           = 'Meilisearch {0} laden'
step_ollama          = 'Ollama installieren'
step_models          = 'Sprachmodelle laden ({0}, {1}) - beim ersten Mal einige GB'
step_settings        = 'Einstellungen anlegen ({0})'
step_database        = 'Datenbank einrichten'
step_service         = 'Dienst einrichten (systemd: homedms)'
step_done_no_service = 'Fertig (ohne Dienst). Starten mit:'
step_done            = 'Fertig! Famulus DMS läuft: https://{0}:{1}'

warn_models          = 'Modelle konnten nicht geladen werden - später: ollama pull {0}'
warn_no_response     = 'Famulus DMS antwortet nicht - Protokoll: journalctl -u homedms -n 50  bzw.  {0}'

info_trust_1         = '   1. Auf jedem Gerät (Handy, PC) einmal http://{0}:{1}/zertifikat öffnen und'
info_trust_2         = '      der Famulus-DMS-Zertifizierungsstelle vertrauen (Anleitung auf der Seite).'
info_wizard          = '   2. Dann https://{0}:{1} öffnen - der Assistent legt Haushalt und Admin-Konto an.'
info_code            = '      Einrichtungscode: {0}'
info_paths           = '   Dokumente: {0}   Scan-Ordner: {1}   Protokoll: {2}'
info_service         = '   Dienst: systemctl status homedms   |   Update: Ordner aktualisieren, dieses Skript erneut starten'
