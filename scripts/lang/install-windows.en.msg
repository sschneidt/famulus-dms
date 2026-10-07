# Messages of install-windows.ps1 (language: English). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the installer). Every key must exist in all languages - the test
# backend/tests/test_installer_messages.py checks that.
@{
    label_error                = 'Error:'

    step_postgres              = 'PostgreSQL'
    step_tesseract             = 'Tesseract (text recognition)'
    step_ollama                = 'Ollama (local AI)'
    step_uv                    = 'Downloading uv (Python package manager)'
    step_python                = 'Setting up the Python environment (backend\.venv)'
    step_node                  = 'Downloading Node.js {0} (only needed to build the web interface)'
    step_build                 = 'Building the web interface'
    step_meili                 = 'Downloading Meilisearch {0}'
    step_settings              = 'Creating settings ({0})'
    step_database              = 'Setting up the database'
    step_autostart             = 'Setting up autostart (scheduled task ''{0}'')'
    step_firewall              = 'Firewall: opening ports {0} and {1} for the home network'
    step_done                  = 'Done! Famulus DMS is running: https://localhost:{0}  (home network: https://{1}:{0})'

    fail_admin                 = 'Please start PowerShell as administrator (right-click > Run as administrator).'
    fail_appdir                = '{0} does not look like the Famulus DMS folder.'
    fail_winget                = 'winget is missing - install ''App Installer'' from the Microsoft Store (usually already present from Windows 10 21H2).'
    fail_64bit                 = 'Only 64-bit Windows is supported.'
    fail_winget_install        = 'winget could not install {0} (code {1})'
    fail_postgres_missing      = 'PostgreSQL was not found (expected under {0}).'
    fail_tesseract_missing     = 'Tesseract was not found.'
    fail_uv_sync               = 'uv sync failed'
    fail_npm_ci                = 'npm ci failed'
    fail_build                 = 'Building the web interface failed'
    fail_psql                  = 'Database command failed (is the password of ''postgres'' correct?)'

    warn_no_input              = 'No input possible - data folder: {0} (to choose another folder, use -DataFolder)'
    warn_path_invalid          = 'Please enter a full path with a drive letter, e.g. D:\Famulus-Data (network paths do not work: the task runs as the system account).'
    warn_drive_missing         = 'The drive {0} does not exist.'
    warn_models                = 'Models could not be downloaded - run later: ollama pull {0}'
    warn_ollama_missing        = 'Ollama was not found - Famulus DMS runs, but automatic classification stays off.'
    warn_firewall              = 'Could not create the firewall rule - if phones or other PCs should connect, allow ports {0} and {1} (TCP) manually.'
    warn_no_response           = 'Famulus DMS does not respond on http://127.0.0.1:{0} - log: {1}'

    prompt_data_folder         = 'Where should documents, scan folder and logs be stored? [{0}]'
    prompt_postgres_password   = 'PostgreSQL is already installed. Password of the user ''postgres'''

    info_existing              = '   Existing installation - data folder: {0}'
    info_data_folder           = '   Data folder: {0}'
    info_pg_password           = '   Password of the database admin (postgres): {0}'
    info_lang_pack             = '   Downloading language pack {0}'
    info_models                = '   Downloading language models ({0}, {1}) - several GB the first time'
    info_cert                  = '   Certificate of the Famulus DMS certificate authority added as trusted on this PC.'
    info_devices               = '   Phones and other PCs: open http://{0}:{1}/zertifikat once and trust the certificate.'
    info_wizard                = '   On the first visit a wizard guides you through the setup (household + admin account).'
    info_code                  = '   Setup code: {0}'
    info_paths                 = '   Documents: {0}   Scan folder: {1}'
    info_logs                  = '   Log: {0}   Autostart: Task Scheduler > ''{1}'''
    info_ollama_note           = '   Note: on Windows Ollama runs as the signed-in user - after a restart the AI only works once you have signed in.'

    task_description           = 'Famulus DMS - document management (web interface, text recognition, AI)'
}
