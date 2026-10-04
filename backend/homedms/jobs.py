"""Zentrale Procrastinate-App (PostgreSQL-Job-Queue, siehe docs/Docker-Compose-Entwurf.md
Abschnitt 2) - eine einzige Instanz, die sowohl vom Worker-Prozess (fuehrt Jobs aus,
homedms/worker.py) als auch vom API-Prozess (erzeugt Jobs, z. B. beim Dokument-Upload)
importiert wird.

Tasks registrieren sich selbst am Modul-Import (via @app.task-Dekorator in homedms/tasks/*.py).
Damit sowohl Worker- als auch API-Prozess dieselben Tasks kennen (Procrastinate muss einen Task
lokal registriert haben, um ihn per configure_task(...).defer_async(...) einreihen zu koennen),
werden alle Task-Module hier zentral importiert - unabhaengig davon, ob der jeweilige Prozess sie
selbst ausfuehrt oder nur erzeugt.
"""
from procrastinate import App, PsycopgConnector

from homedms.config import get_settings

settings = get_settings()

app = App(connector=PsycopgConnector(conninfo=settings.procrastinate_database_url))

from homedms.tasks import misc as _misc  # noqa: E402,F401  (registriert 'ping')
from homedms.tasks import ocr as _ocr  # noqa: E402,F401  (registriert 'ocr_document')
from homedms.tasks import classification as _classification  # noqa: E402,F401  (classify_document, learn_exemplar)
from homedms.tasks import extraction as _extraction  # noqa: E402,F401  (extract_metadata)
from homedms.tasks import filing as _filing  # noqa: E402,F401  (file_document)
from homedms.tasks import scanfolder as _scanfolder  # noqa: E402,F401  (scan_folders, jede Minute)
from homedms.tasks import system as _system  # noqa: E402,F401  (restart_worker, pull_model - Seite Diagnose)
from homedms.tasks import notifications as _notifications  # noqa: E402,F401  (send_reminders, alle 15 Min.)
