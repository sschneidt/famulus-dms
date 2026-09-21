"""Worker-Grundgeruest (homedms/worker.py) - prueft nur die Verkabelung (App-Objekt,
Platzhalter-Task registriert, DATABASE_URL-Normalisierung fuer psycopg), fuehrt keinen
Task tatsaechlich gegen eine DB aus (dafuer braucht es einen laufenden Postgres-Container,
siehe README.md Abschnitt "Tests").
"""
from homedms.config import Settings
from homedms.worker import app, ping


def test_ping_task_is_registered():
    assert "ping" in app.tasks


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
