# Messages of install-linux.sh (language: English). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the script). Every key must exist in all languages - the test
# backend/tests/test_installer_messages.py checks that.
label_error          = 'Error:'

help_1               = 'Install Famulus DMS on a Linux server without Docker (Debian 12+, Ubuntu 22.04+).'
help_2               = '  sudo bash scripts/install-linux.sh [--no-ai] [--no-search] [--no-service] [--lang de|en|ru]'
help_3               = '  --no-ai        without Ollama (automatic classification stays off)'
help_4               = '  --no-search    without Meilisearch (search only through the database)'
help_5               = '  --no-service   do not set up a systemd service (e.g. WSL/container); start by hand, see the end of the output'
help_6               = '  --lang         language of the installation: de, en or ru (default: from the system locale)'

fail_unknown_option  = 'Unknown option: {0}'
fail_root            = 'Please start with sudo: sudo bash {0}'
fail_apt             = 'This script supports Debian/Ubuntu (apt). Other systems: docs/Installation-ohne-Docker.md'
fail_appdir          = '{0} does not look like the Famulus DMS folder'
fail_cpu             = 'Processor {0} is not supported'
fail_unreadable      = 'User {0} cannot read {1} (e.g. because it is inside a home folder). Move the folder to /opt/homedms and run this script there again.'

step_packages        = 'Installing packages (PostgreSQL, Tesseract)'
step_uv              = 'Downloading uv (Python package manager)'
step_python          = 'Setting up the Python environment (backend/.venv)'
step_node            = 'Downloading Node.js {0} (only needed to build the web interface)'
step_build           = 'Building the web interface'
step_meili           = 'Downloading Meilisearch {0}'
step_ollama          = 'Installing Ollama'
step_models          = 'Downloading language models ({0}, {1}) - several GB the first time'
step_settings        = 'Creating settings ({0})'
step_database        = 'Setting up the database'
step_service         = 'Setting up the service (systemd: homedms)'
step_done_no_service = 'Done (without service). Start with:'
step_done            = 'Done! Famulus DMS is running: https://{0}:{1}'

warn_models          = 'Models could not be downloaded - run later: ollama pull {0}'
warn_no_response     = 'Famulus DMS does not respond - log: journalctl -u homedms -n 50  or  {0}'

info_trust_1         = '   1. On every device (phone, PC) open http://{0}:{1}/zertifikat once and'
info_trust_2         = '      trust the Famulus DMS certificate authority (instructions on that page).'
info_wizard          = '   2. Then open https://{0}:{1} - the wizard creates the household and the admin account.'
info_code            = '      Setup code: {0}'
info_paths           = '   Documents: {0}   Scan folder: {1}   Log: {2}'
info_service         = '   Service: systemctl status homedms   |   Update: refresh the folder and run this script again'
