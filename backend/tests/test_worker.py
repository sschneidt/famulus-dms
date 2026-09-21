"""Worker-/Job-Grundgeruest (homedms/jobs.py, homedms/worker.py) - prueft nur die Verkabelung
(App-Objekt, Tasks registriert, DATABASE_URL-Normalisierung fuer psycopg), fuehrt keinen Task
tatsaechlich gegen eine DB aus (dafuer braucht es einen laufenden Postgres-Container, siehe
README.md Abschnitt "Tests"). Die eigentliche OCR-Extraktionslogik ist in tests/test_ocr.py
abgedeckt.
"""
from homedms.config import Settings
from homedms.jobs import app
from homedms.tasks.misc import ping
from homedms.worker import app as worker_app


def test_worker_uses_the_shared_jobs_app():
    assert worker_app is app


def test_expected_tasks_are_registered():
    assert "ping" in app.tasks
    assert "ocr_document" in app.tasks


async def test_ping_task_returns_message():
    result = await ping.func("hallo")
    assert result == "hallo"


def test_database_url_normalization_plain_postgresql():
    s = Settings(database_url="postgresql://u:p@host:5432/db")
    assert s.sqlalchemy_database_url == "postgresql+asyncpg://u:p@host:5432/db"
    assert s.procrastinate_database_url == "postgresql://u:p@host:5432/db"


def test_database_url_normalization_asyncpg_variant():
    s = Settings(database_url="postgresql+asyncpg://u:p@host:5432/db")
    assert s.sqlalchemy_database_url == "postgresql+asyncpg://u:p@host:5432/db"
    assert s.procrastinate_database_url == "postgresql://u:p@host:5432/db"
