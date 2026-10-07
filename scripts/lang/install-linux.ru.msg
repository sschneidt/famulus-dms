# Messages of install-linux.sh (language: Russian). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the script). Every key must exist in all languages - the test
# backend/tests/test_installer_messages.py checks that.
label_error          = 'Ошибка:'

help_1               = 'Установка Famulus DMS на сервер Linux без Docker (Debian 12+, Ubuntu 22.04+).'
help_2               = '  sudo bash scripts/install-linux.sh [--no-ai] [--no-search] [--no-service] [--lang de|en|ru]'
help_3               = '  --no-ai        без Ollama (автоматическая классификация отключена)'
help_4               = '  --no-search    без Meilisearch (поиск только через базу данных)'
help_5               = '  --no-service   не создавать службу systemd (например, WSL/контейнер); запуск вручную, см. конец вывода'
help_6               = '  --lang         язык установки: de, en или ru (по умолчанию - из языка системы)'

fail_unknown_option  = 'Неизвестный параметр: {0}'
fail_root            = 'Запустите с sudo: sudo bash {0}'
fail_apt             = 'Скрипт поддерживает Debian/Ubuntu (apt). Другие системы: docs/Installation-ohne-Docker.md'
fail_appdir          = '{0} не похож на папку Famulus DMS'
fail_cpu             = 'Процессор {0} не поддерживается'
fail_unreadable      = 'Пользователь {0} не может читать {1} (например, из-за расположения в домашней папке). Переместите папку в /opt/homedms и запустите скрипт там снова.'

step_packages        = 'Установка пакетов (PostgreSQL, Tesseract)'
step_uv              = 'Загрузка uv (менеджер пакетов Python)'
step_python          = 'Настройка окружения Python (backend/.venv)'
step_node            = 'Загрузка Node.js {0} (нужен только для сборки веб-интерфейса)'
step_build           = 'Сборка веб-интерфейса'
step_meili           = 'Загрузка Meilisearch {0}'
step_ollama          = 'Установка Ollama'
step_models          = 'Загрузка языковых моделей ({0}, {1}) - при первом запуске несколько ГБ'
step_settings        = 'Создание настроек ({0})'
step_database        = 'Настройка базы данных'
step_service         = 'Настройка службы (systemd: homedms)'
step_done_no_service = 'Готово (без службы). Запуск:'
step_done            = 'Готово! Famulus DMS работает: https://{0}:{1}'

warn_models          = 'Не удалось загрузить модели - позже выполните: ollama pull {0}'
warn_no_response     = 'Famulus DMS не отвечает - журнал: journalctl -u homedms -n 50  или  {0}'

info_trust_1         = '   1. На каждом устройстве (телефон, ПК) один раз откройте http://{0}:{1}/zertifikat и'
info_trust_2         = '      доверьтесь центру сертификации Famulus DMS (инструкция на странице).'
info_wizard          = '   2. Затем откройте https://{0}:{1} - мастер создаст домохозяйство и учётную запись администратора.'
info_code            = '      Код настройки: {0}'
info_paths           = '   Документы: {0}   Папка сканирования: {1}   Журнал: {2}'
info_service         = '   Служба: systemctl status homedms   |   Обновление: обновите папку и снова запустите этот скрипт'
