"""Integrationstests gegen eine ECHTE PostgreSQL-Datenbank (mit pg_trgm).

Laufen nur, wenn sie ausdruecklich eingeschaltet werden - sie LEEREN vor jedem Lauf alle
Tabellen der Zieldatenbank:

    HOMEDMS_INTEGRATION_TESTS=1
    DATABASE_URL=postgresql://<user>:<pw>@<host>:<port>/<name>_test

Als zusaetzliche Absicherung muss der Datenbankname auf "_test" enden, damit nie versehentlich
die echte Famulus-DMS-Datenbank geleert wird. Das Schema wird vorher per `alembic upgrade head`
angelegt/aktualisiert (testet damit auch die Migrationen selbst).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _enabled() -> tuple[bool, str]:
    if os.environ.get("HOMEDMS_INTEGRATION_TESTS") != "1":
        return False, "HOMEDMS_INTEGRATION_TESTS=1 nicht gesetzt"
    url = os.environ.get("DATABASE_URL", "")
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not db_name.endswith("_test"):
        return False, f"Datenbankname '{db_name}' endet nicht auf '_test' - aus Sicherheitsgruenden uebersprungen"
    return True, ""


def pytest_collection_modifyitems(config, items):
    enabled, reason = _enabled()
    if enabled:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "integration" in item.nodeid:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_database():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
async def clean_database(migrated_database):
    """Leert alle Tabellen (ausser alembic_version) und gibt die Engine am Ende frei, damit
    keine Verbindung ueber das Test-Ende hinaus an einem geschlossenen Event-Loop haengt."""
    from sqlalchemy import text

    from homedms.db import engine

    async with engine.begin() as conn:
        tables = (
            await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")
            )
        ).scalars().all()
        await conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
    from homedms.core import login_guard

    login_guard._ip_failures.clear()  # Fehlversuche frueherer Tests zaehlen nicht
    yield
    await engine.dispose()
