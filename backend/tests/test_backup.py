"""Datenbanksicherung aus der Anwendung (core/backup.py) - ohne echte Datenbank, pg_dump wird nachgestellt."""
import asyncio
import os
import time

import pytest

from homedms.config import get_settings, read_or_create_secret
from homedms.core import backup


@pytest.fixture
def folder(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "backup_path", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "backup_keep", 3)
    monkeypatch.setattr(settings, "database_url", "postgresql://user:p%40ss@dbhost:5433/mydb")
    return tmp_path / "backups"


class FakeProcess:
    def __init__(self, returncode: int, err: bytes = b""):
        self.returncode, self._err = returncode, err

    async def communicate(self):
        return b"", self._err


def fake_pg_dump(monkeypatch, *, returncode=0, size=4096, err=b""):
    """Ersetzt pg_dump: schreibt die Datei hinter "-f" und merkt sich Aufruf und Umgebung."""
    calls = []

    async def fake_exec(exe, *args, env=None, **kwargs):
        calls.append({"exe": exe, "args": list(args), "env": env})
        target = args[args.index("-f") + 1]
        if returncode == 0:
            with open(target, "wb") as handle:
                handle.write(b"x" * size)
        return FakeProcess(returncode, err)

    monkeypatch.setattr(backup, "find_pg_dump", lambda: "/usr/bin/pg_dump")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls


async def test_sicherung_wird_angelegt(folder, monkeypatch):
    calls = fake_pg_dump(monkeypatch)
    item = await backup.create()

    assert item.name.startswith("homedms-") and item.name.endswith(".dump") and item.size == 4096
    assert [b.name for b in backup.list_backups()] == [item.name]
    assert not list(folder.glob("*.part"))
    args = calls[0]["args"]
    assert args[:1] == ["-Fc"] and "-h" in args and args[args.index("-h") + 1] == "dbhost"
    assert args[args.index("-p") + 1] == "5433" and args[args.index("-d") + 1] == "mydb"
    assert args[args.index("-U") + 1] == "user"


async def test_passwort_nicht_in_den_argumenten(folder, monkeypatch):
    calls = fake_pg_dump(monkeypatch)
    await backup.create()
    assert "p@ss" not in " ".join(calls[0]["args"]) and "p%40ss" not in " ".join(calls[0]["args"])
    assert calls[0]["env"]["PGPASSWORD"] == "p@ss"  # Prozentzeichen im Passwort wurden aufgeloest


async def test_alte_sicherungen_werden_aufgeraeumt(folder, monkeypatch):
    fake_pg_dump(monkeypatch)
    folder.mkdir(parents=True)
    for i in range(5):  # fuenf alte, jeweils eine Stunde aelter
        path = folder / f"homedms-0.1.0-2026010{i}-120000.dump"
        path.write_bytes(b"x" * 2000)
        os.utime(path, (time.time() - 3600 * (10 - i),) * 2)
    await backup.create()
    names = [b.name for b in backup.list_backups()]
    assert len(names) == 3 and "homedms-0.1.0-20260100-120000.dump" not in names


async def test_fremde_dateien_bleiben_unberuehrt(folder, monkeypatch):
    fake_pg_dump(monkeypatch)
    folder.mkdir(parents=True)
    (folder / "notizen.txt").write_text("nicht loeschen")
    (folder / "homedms-x.dump.part").write_bytes(b"halb")
    for _ in range(5):
        await backup.create()
        time.sleep(1.1)  # Sekunden im Dateinamen
    assert (folder / "notizen.txt").exists() and (folder / "homedms-x.dump.part").exists()
    assert len(backup.list_backups()) == 3


async def test_fehlerhaftes_pg_dump(folder, monkeypatch):
    fake_pg_dump(monkeypatch, returncode=1, err=b"pg_dump: error: connection failed\npg_dump: error: password authentication failed")
    with pytest.raises(backup.BackupError, match="password authentication failed"):
        await backup.create()
    assert backup.list_backups() == [] and not list(folder.glob("*.part"))


async def test_zu_kleine_datei_gilt_als_fehler(folder, monkeypatch):
    fake_pg_dump(monkeypatch, size=10)
    with pytest.raises(backup.BackupError, match="unvollständig"):
        await backup.create()
    assert backup.list_backups() == [] and not list(folder.glob("*.part"))


async def test_ohne_pg_dump(folder, monkeypatch):
    monkeypatch.setattr(backup, "find_pg_dump", lambda: None)
    assert backup.available() is False
    with pytest.raises(backup.BackupError, match="pg_dump wurde nicht gefunden"):
        await backup.create()


@pytest.mark.parametrize("name", ["../geheim.dump", "..\\geheim.dump", "homedms-x.txt", "andere.dump", "", "homedms-/x.dump"])
def test_unzulaessige_namen(folder, name):
    folder.mkdir(parents=True)
    (folder.parent / "geheim.dump").write_bytes(b"x" * 2000)
    with pytest.raises(FileNotFoundError):
        backup.path_of(name)
    with pytest.raises(FileNotFoundError):
        backup.delete(name)


def test_loeschen(folder):
    folder.mkdir(parents=True)
    (folder / "homedms-0.2.1-20260101-000000.dump").write_bytes(b"x" * 2000)
    backup.delete("homedms-0.2.1-20260101-000000.dump")
    assert backup.list_backups() == []


# --- JWT-Schluesseldatei (config.read_or_create_secret) -----------------------------------------


def test_schluesseldatei_wird_einmal_angelegt(tmp_path):
    path = tmp_path / "sub" / "jwt_secret"
    first = read_or_create_secret(path)
    assert len(first) == 64 and read_or_create_secret(path) == first
    assert path.read_text().strip() == first


def test_schluesseldatei_bei_gleichzeitigem_start(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "jwt_secret"
    with ThreadPoolExecutor(8) as pool:
        values = set(pool.map(lambda _: read_or_create_secret(path), range(16)))
    assert len(values) == 1


def test_schluessel_aus_datei_nur_bei_platzhalter(tmp_path, monkeypatch):
    from homedms.config import Settings

    path = tmp_path / "jwt_secret"
    monkeypatch.setenv("JWT_SECRET_FILE", str(path))
    monkeypatch.delenv("JWT_SECRET", raising=False)
    auto = Settings(_env_file=None).jwt_secret
    assert len(auto) == 64 and path.read_text().strip() == auto

    monkeypatch.setenv("JWT_SECRET", "mein-eigener-schluessel")  # ausdruecklich gesetzt: gewinnt
    assert Settings(_env_file=None).jwt_secret == "mein-eigener-schluessel"

    monkeypatch.setenv("JWT_SECRET", "CHANGE_ME_LONG_RANDOM_STRING")  # Platzhalter aus der Vorlage: Datei
    assert Settings(_env_file=None).jwt_secret == auto
