"""Update aus der Anwendung anstossen (core/updater.py): Dateien im Sicherungsordner, kein Docker-Zugriff."""
import json
import time

import httpx
import pytest

from homedms import __version__
from homedms.config import get_settings
from homedms.core import backup, updater


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_path", str(tmp_path))
    return tmp_path


def beat(folder, age: float = 0) -> None:
    (folder / updater.HEARTBEAT).write_text(f"{int(time.time() - age)}\n", encoding="utf-8")


def write_status(folder, state: str, version: str = "9.9.9", detail: str = "") -> None:
    (folder / updater.STATUS).write_text(json.dumps({"state": state, "version": version, "detail": detail, "at": 1}), encoding="utf-8")


@pytest.fixture
def backed_up(monkeypatch):
    calls = []

    async def fake_create():
        calls.append(1)

    monkeypatch.setattr(backup, "create", fake_create)
    monkeypatch.setattr(backup, "available", lambda: True)
    return calls


def test_ohne_lebenszeichen_gibt_es_keinen_helfer(folder):
    assert updater.status() == updater.AgentStatus(False, None, None, "")


@pytest.mark.parametrize(("age", "alive"), [(0, True), (120, True), (200, False), (-500, False)])
def test_lebenszeichen_darf_nicht_zu_alt_sein(folder, age, alive):
    beat(folder, age)
    assert updater.status().available is alive


def test_unlesbares_lebenszeichen(folder):
    (folder / updater.HEARTBEAT).write_text("gestern", encoding="utf-8")
    assert not updater.status().available


@pytest.mark.parametrize("state", ["checking", "pulling", "restarting", "health", "done", "failed", "rolled_back"])
def test_status_des_helfers_wird_gelesen(folder, state):
    beat(folder)
    write_status(folder, state, detail="Hinweis")
    assert updater.status() == updater.AgentStatus(True, state, "9.9.9", "Hinweis")


def test_unbekannter_oder_kaputter_status_wird_ignoriert(folder):
    beat(folder)
    write_status(folder, "hackerangriff")
    assert updater.status().state is None
    (folder / updater.STATUS).write_text("{kaputt", encoding="utf-8")
    assert updater.status().state is None
    (folder / updater.STATUS).write_text("[1, 2]", encoding="utf-8")
    assert updater.status().state is None


def test_laufendes_update_zaehlt_auch_ohne_frisches_lebenszeichen(folder):
    """Waehrend des Updates schreibt der Helfer evtl. kein Lebenszeichen - die Anzeige soll trotzdem weiterlaufen."""
    beat(folder, 1000)
    write_status(folder, "health")
    assert updater.status().available and updater.status().state == "health"


async def test_anforderung_sichert_die_datenbank_und_schreibt_die_datei(folder, backed_up):
    beat(folder)
    result = await updater.request("99.0.0")
    assert backed_up == [1]
    assert (folder / updater.REQUEST).read_text(encoding="utf-8") == "version=99.0.0\n"
    assert result.state == "requested" and result.version == "99.0.0"


async def test_altes_ergebnis_wird_bei_neuer_anforderung_geloescht(folder, backed_up):
    beat(folder)
    write_status(folder, "failed")
    await updater.request("99.0.0")
    assert not (folder / updater.STATUS).exists()


@pytest.mark.parametrize("version", ["latest", "1.2", "99.0.0; rm -rf /", "../99.0.0", "99.0.0\nversion=1.0.0", ""])
async def test_ungueltige_version_wird_abgelehnt(folder, backed_up, version):
    beat(folder)
    with pytest.raises(updater.UpdaterError):
        await updater.request(version)
    assert not (folder / updater.REQUEST).exists() and backed_up == []


@pytest.mark.parametrize("version", [__version__, "0.0.1"])
async def test_nur_neuere_version(folder, backed_up, version):
    beat(folder)
    with pytest.raises(updater.UpdaterError, match="nicht neuer"):
        await updater.request(version)


async def test_ohne_helfer_keine_anforderung(folder, backed_up):
    with pytest.raises(updater.UpdaterError, match="Update-Helfer"):
        await updater.request("99.0.0")
    assert not (folder / updater.REQUEST).exists()


async def test_nicht_zweimal_gleichzeitig(folder, backed_up):
    beat(folder)
    await updater.request("99.0.0")
    with pytest.raises(updater.UpdaterError, match="läuft bereits"):
        await updater.request("99.0.0")
    assert backed_up == [1]


async def test_ohne_gelungene_sicherung_wird_nichts_angefordert(folder, monkeypatch):
    beat(folder)
    monkeypatch.setattr(backup, "available", lambda: True)

    async def failing():
        raise backup.BackupError("Platte voll")

    monkeypatch.setattr(backup, "create", failing)
    with pytest.raises(updater.UpdaterError, match="Platte voll"):
        await updater.request("99.0.0")
    assert not (folder / updater.REQUEST).exists()


async def test_ohne_pg_dump_wird_nicht_aktualisiert(folder, monkeypatch):
    beat(folder)
    monkeypatch.setattr(backup, "available", lambda: False)
    with pytest.raises(updater.UpdaterError, match="pg_dump"):
        await updater.request("99.0.0")


def test_nicht_abgeholte_anforderung_gilt_als_gescheitert(folder):
    beat(folder)
    request = folder / updater.REQUEST
    request.write_text("version=99.0.0\n", encoding="utf-8")
    assert updater.status().state == "requested"
    later = time.time() + updater.REQUEST_MAX_AGE + 10
    beat_later = int(later)
    (folder / updater.HEARTBEAT).write_text(str(beat_later), encoding="utf-8")
    assert updater.status(now=later).state == "failed"
    assert updater.status(now=later).detail == "not_picked_up"


@pytest.mark.skipif(not hasattr(__import__("os"), "symlink"), reason="keine Links")
def test_ein_link_statt_einer_datei_wird_nicht_gelesen(folder, tmp_path_factory):
    target = tmp_path_factory.mktemp("elsewhere") / "secret"
    target.write_text(str(int(time.time())), encoding="utf-8")
    try:
        (folder / updater.HEARTBEAT).symlink_to(target)
    except OSError:
        pytest.skip("Links sind hier nicht erlaubt")
    assert not updater.status().available


async def test_schnittstelle_verlangt_eine_anmeldung():
    from homedms.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        assert (await api.get("/api/v1/system/updates/installer")).status_code in (401, 403)
        assert (await api.post("/api/v1/system/updates/installer", json={"version": "99.0.0"})).status_code in (401, 403)
