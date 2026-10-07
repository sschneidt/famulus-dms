# Messages of update.sh and update.ps1 (language: Russian). One text per line: key = 'text'  ('' stands for a quote;
# {0}, {1} ... are filled in by the script). Both scripts share this catalog. Every key must exist in all
# languages - the test backend/tests/test_installer_messages.py checks that.
label_error             = 'Ошибка:'

help_1                  = 'Обновление Famulus DMS (Docker): резервная копия базы, загрузка новой версии, перезапуск, проверка.'
help_2                  = '  --backup-only    только резервная копия базы, без обновления'
help_3                  = '  --no-backup      пропустить резервное копирование (не рекомендуется)'
help_4                  = '  --lang           язык: de, en или ru (по умолчанию - из языка системы)'
help_5                  = 'Копии хранятся в ./backups (остаются последние 5, KEEP=n меняет это). Подробнее: docs/Updates.md'

fail_unknown_option     = 'Неизвестный параметр: {0}'
fail_docker_linux       = 'Docker не запущен (или не хватает прав - попробуйте с sudo).'
fail_docker_windows     = 'Docker не запущен. Запустите Docker Desktop и повторите попытку.'
fail_compose            = 'docker-compose.yml не найден (ожидался в {0}).'
fail_db_down            = 'Контейнер базы данных не запущен. Сначала выполните ''docker compose up -d''.'

step_version            = 'Проверка установленной версии'
info_current            = 'Сейчас: {0}'
word_unknown            = 'неизвестно'

step_backup             = 'Резервная копия базы данных'
info_backup_skipped     = 'Резервное копирование пропущено ({0}).'
fail_backup             = 'Не удалось создать резервную копию базы данных. Ничего не изменено.'
fail_backup_copy        = 'Не удалось скопировать резервную копию. Ничего не изменено.'
fail_backup_incomplete  = 'Резервная копия неполная. Ничего не изменено.'
info_backup_done        = 'Копия создана: {0}'
done_backup_only        = 'Готово (только резервная копия).'

step_pull               = 'Загрузка новой версии ({0})'
fail_pull               = 'Не удалось загрузить образ. Продолжает работать прежняя версия.'
step_git                = 'Получение последнего кода (git pull)'
fail_git                = 'git pull не удался (есть локальные изменения?). Продолжает работать прежняя версия.'
info_no_git             = 'Это не папка Git - собирается состояние этой папки.'

step_restart            = 'Перезапуск Famulus DMS'
fail_restart            = 'Не удалось выполнить перезапуск.'
step_wait               = 'Ожидание ответа Famulus DMS'
warn_not_ready          = 'Famulus DMS не готов через {0} с (состояние: {1}).'
info_dump_location      = 'Ваша резервная копия базы данных: {0}'
info_rollback           = 'Как вернуться назад: docs/Updates.md, раздел "Возврат к старой версии".'

done_update             = 'Готово. Версия: {0} -> {1}'
