# Messages of install-windows.ps1 (language: Russian). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the installer). Every key must exist in all languages - the test
# backend/tests/test_installer_messages.py checks that.
@{
    label_error                = 'Ошибка:'

    step_postgres              = 'PostgreSQL'
    step_tesseract             = 'Tesseract (распознавание текста)'
    step_ollama                = 'Ollama (локальный ИИ)'
    step_uv                    = 'Загрузка uv (менеджер пакетов Python)'
    step_python                = 'Настройка окружения Python (backend\.venv)'
    step_node                  = 'Загрузка Node.js {0} (нужен только для сборки веб-интерфейса)'
    step_build                 = 'Сборка веб-интерфейса'
    step_meili                 = 'Загрузка Meilisearch {0}'
    step_settings              = 'Создание настроек ({0})'
    step_database              = 'Настройка базы данных'
    step_autostart             = 'Настройка автозапуска (задача планировщика ''{0}'')'
    step_firewall              = 'Брандмауэр: открытие портов {0} и {1} для домашней сети'
    step_done                  = 'Готово! Famulus DMS работает: https://localhost:{0}  (в домашней сети: https://{1}:{0})'

    fail_admin                 = 'Запустите PowerShell от имени администратора (правый клик > Запуск от имени администратора).'
    fail_appdir                = '{0} не похож на папку Famulus DMS.'
    fail_winget                = 'winget не найден - установите «Установщик приложений» из Microsoft Store (обычно он уже есть, начиная с Windows 10 21H2).'
    fail_64bit                 = 'Поддерживается только 64-разрядная Windows.'
    fail_winget_install        = 'winget не смог установить {0} (код {1})'
    fail_postgres_missing      = 'PostgreSQL не найден (ожидался в {0}).'
    fail_tesseract_missing     = 'Tesseract не найден.'
    fail_uv_sync               = 'Ошибка uv sync'
    fail_npm_ci                = 'Ошибка npm ci'
    fail_build                 = 'Не удалось собрать веб-интерфейс'
    fail_psql                  = 'Ошибка команды базы данных (верен ли пароль пользователя ''postgres''?)'

    warn_no_input              = 'Ввод невозможен - папка данных: {0} (другую папку укажите параметром -DataFolder)'
    warn_path_invalid          = 'Укажите полный путь с буквой диска, например D:\Famulus-Data (сетевые пути не подходят: задача выполняется от имени системной учётной записи).'
    warn_drive_missing         = 'Диск {0} не существует.'
    warn_models                = 'Не удалось загрузить модели - позже выполните: ollama pull {0}'
    warn_ollama_missing        = 'Ollama не найден - Famulus DMS работает, но автоматическая классификация отключена.'
    warn_firewall              = 'Не удалось создать правило брандмауэра - чтобы подключаться с телефонов и других ПК, вручную откройте порты {0} и {1} (TCP).'
    warn_no_response           = 'Famulus DMS не отвечает на http://127.0.0.1:{0} - журнал: {1}'

    prompt_data_folder         = 'Где хранить документы, папку сканирования и журналы? [{0}]'
    prompt_postgres_password   = 'PostgreSQL уже установлен. Пароль пользователя ''postgres'''

    info_existing              = '   Найдена существующая установка - папка данных: {0}'
    info_data_folder           = '   Папка данных: {0}'
    info_pg_password           = '   Пароль администратора базы данных (postgres): {0}'
    info_lang_pack             = '   Загрузка языкового пакета {0}'
    info_models                = '   Загрузка языковых моделей ({0}, {1}) - при первом запуске несколько ГБ'
    info_cert                  = '   Сертификат центра сертификации Famulus DMS добавлен в доверенные на этом компьютере.'
    info_devices               = '   Телефоны и другие компьютеры: один раз откройте http://{0}:{1}/zertifikat и доверьтесь сертификату.'
    info_wizard                = '   При первом входе мастер проведёт через настройку (домохозяйство + учётная запись администратора).'
    info_code                  = '   Код настройки: {0}'
    info_paths                 = '   Документы: {0}   Папка сканирования: {1}'
    info_logs                  = '   Журнал: {0}   Автозапуск: Планировщик заданий > ''{1}'''
    info_ollama_note           = '   Примечание: в Windows Ollama работает от имени вошедшего пользователя - после перезагрузки ИИ заработает только после входа.'

    task_description           = 'Famulus DMS - управление документами (веб-интерфейс, распознавание текста, ИИ)'
}
