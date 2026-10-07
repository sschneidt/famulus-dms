# Messages of install-windows.ps1 (language: German). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the installer). Every key must exist in all languages - the test
# backend/tests/test_installer_messages.py checks that.
@{
    label_error                = 'Fehler:'

    step_postgres              = 'PostgreSQL'
    step_tesseract             = 'Tesseract (Texterkennung)'
    step_ollama                = 'Ollama (lokale KI)'
    step_uv                    = 'uv (Python-Paketverwaltung) laden'
    step_python                = 'Python-Umgebung einrichten (backend\.venv)'
    step_node                  = 'Node.js {0} laden (nur zum Bauen der Weboberfläche)'
    step_build                 = 'Weboberfläche bauen'
    step_meili                 = 'Meilisearch {0} laden'
    step_settings              = 'Einstellungen anlegen ({0})'
    step_database              = 'Datenbank einrichten'
    step_autostart             = 'Autostart einrichten (geplante Aufgabe ''{0}'')'
    step_firewall              = 'Firewall: Ports {0} und {1} im Heimnetz freigeben'
    step_done                  = 'Fertig! Famulus DMS läuft: https://localhost:{0}  (im Heimnetz: https://{1}:{0})'

    fail_admin                 = 'Bitte PowerShell als Administrator starten (Rechtsklick > Als Administrator ausführen).'
    fail_appdir                = '{0} sieht nicht wie der Famulus-DMS-Ordner aus.'
    fail_winget                = 'winget fehlt - ''App-Installer'' aus dem Microsoft Store installieren (ab Windows 10 21H2 meist schon vorhanden).'
    fail_64bit                 = 'Nur 64-Bit-Windows wird unterstützt.'
    fail_winget_install        = 'winget konnte {0} nicht installieren (Code {1})'
    fail_postgres_missing      = 'PostgreSQL wurde nicht gefunden (erwartet unter {0}).'
    fail_tesseract_missing     = 'Tesseract wurde nicht gefunden.'
    fail_uv_sync               = 'uv sync fehlgeschlagen'
    fail_npm_ci                = 'npm ci fehlgeschlagen'
    fail_build                 = 'Bauen der Weboberfläche fehlgeschlagen'
    fail_psql                  = 'Datenbank-Befehl fehlgeschlagen (Passwort von ''postgres'' richtig?)'

    warn_no_input              = 'Keine Eingabe möglich - Datenordner: {0} (anderer Ordner: -DatenOrdner angeben)'
    warn_path_invalid          = 'Bitte einen vollständigen Pfad mit Laufwerksbuchstaben angeben, z. B. D:\Famulus-Data (Netzwerkpfade gehen nicht: die Aufgabe läuft als Systemkonto).'
    warn_drive_missing         = 'Das Laufwerk {0} gibt es nicht.'
    warn_models                = 'Modelle konnten nicht geladen werden - später: ollama pull {0}'
    warn_ollama_missing        = 'Ollama wurde nicht gefunden - Famulus DMS läuft, die KI-Einordnung bleibt aber aus.'
    warn_firewall              = 'Firewall-Regel konnte nicht angelegt werden - Zugriff von Handy/anderen PCs ggf. von Hand freigeben: Ports {0} und {1} (TCP)'
    warn_no_response           = 'Famulus DMS antwortet nicht auf http://127.0.0.1:{0} - Protokoll: {1}'

    prompt_data_folder         = 'Wo sollen Dokumente, Scan-Ordner und Protokolle liegen? [{0}]'
    prompt_postgres_password   = 'PostgreSQL ist schon installiert. Passwort des Benutzers ''postgres'''

    info_existing              = '   Vorhandene Installation - Datenordner: {0}'
    info_data_folder           = '   Datenordner: {0}'
    info_pg_password           = '   Passwort des Datenbank-Admins (postgres): {0}'
    info_lang_pack             = '   Sprachpaket {0} laden'
    info_models                = '   Sprachmodelle laden ({0}, {1}) - beim ersten Mal einige GB'
    info_cert                  = '   Zertifikat der Famulus-DMS-Zertifizierungsstelle auf diesem PC als vertrauenswürdig eingetragen.'
    info_devices               = '   Handy und andere PCs: einmal http://{0}:{1}/zertifikat öffnen und dem Zertifikat vertrauen.'
    info_wizard                = '   Beim ersten Aufruf führt ein Assistent durch die Einrichtung (Haushalt + Admin-Konto).'
    info_code                  = '   Einrichtungscode: {0}'
    info_paths                 = '   Dokumente: {0}   Scan-Ordner: {1}'
    info_logs                  = '   Protokoll: {0}   Autostart: Aufgabenplanung > ''{1}'''
    info_ollama_note           = '   Hinweis: Ollama läuft unter Windows im angemeldeten Benutzer - nach einem Neustart erst nach der Anmeldung.'

    task_description           = 'Famulus DMS - Dokumentenverwaltung (Weboberfläche, Texterkennung, KI)'
}
