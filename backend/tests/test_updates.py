"""Auf Updates pruefen (core/updates.py) - ohne Netz, GitHub wird mit httpx.MockTransport nachgestellt."""
import httpx
import pytest

from homedms import __version__
from homedms.config import get_settings
from homedms.core import updates


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(get_settings(), "update_check_url", "https://example.invalid/releases/latest")
    updates.clear_cache()
    yield
    updates.clear_cache()


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def release(tag: str, **extra):
    return {"tag_name": tag, "html_url": f"https://example.invalid/releases/{tag}", "published_at": "2026-11-03T10:00:00Z", **extra}


@pytest.mark.parametrize(("latest", "current", "expected"), [
    ("0.2.4", "0.2.3", True),
    ("v0.3.0", "0.2.9", True),
    ("1.0.0", "0.99.99", True),
    ("0.2.10", "0.2.9", True),  # Zahlen, nicht Text
    ("0.2.3", "0.2.3", False),
    ("0.2.2", "0.2.3", False),
    ("unsinn", "0.2.3", False),
    ("0.2.4", "unsinn", False),
])
def test_versionsvergleich(latest, current, expected):
    assert updates.is_newer(latest, current) is expected


async def test_neuere_version_wird_gemeldet():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["agent"] = request.headers["user-agent"]
        return httpx.Response(200, json=release("v99.0.0"))

    info = await updates.check(client_for(handler))
    assert info.available and info.latest == "99.0.0" and info.current == __version__
    assert info.url.endswith("/v99.0.0") and info.published_at is not None
    assert seen["agent"] == f"famulus-dms/{__version__}"  # nennt sich selbst, keine Adresse des Nutzers


async def test_gleiche_version_ist_aktuell():
    info = await updates.check(client_for(lambda r: httpx.Response(200, json=release(f"v{__version__}"))))
    assert not info.available and info.latest == __version__


async def test_ergebnis_wird_kurz_gemerkt_und_mit_force_neu_geholt():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=release("v99.0.0"))

    client = client_for(handler)
    await updates.check(client)
    await updates.check(client)
    assert len(calls) == 1
    await updates.check(client, force=True)
    assert len(calls) == 2


@pytest.mark.parametrize(("response", "fragment"), [
    (httpx.Response(404), "404"),
    (httpx.Response(403, json={"message": "rate limit"}), "403"),
    (httpx.Response(200, text="<html>"), "nicht lesbar"),
    (httpx.Response(200, json={"tag_name": "nightly"}), "nicht lesbar"),
    (httpx.Response(200, json=["unerwartet"]), "nicht lesbar"),
])
async def test_fehlerhafte_antworten(response, fragment):
    with pytest.raises(updates.UpdateCheckError) as err:
        await updates.check(client_for(lambda r: response))
    assert fragment in str(err.value)


async def test_netzwerkfehler():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kein Netz")

    with pytest.raises(updates.UpdateCheckError) as err:
        await updates.check(client_for(handler))
    assert "Internet" in str(err.value)


async def test_schnittstelle_verlangt_eine_anmeldung():
    from homedms.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        r = await api.post("/api/v1/system/updates/check")
    assert r.status_code in (401, 403), r.text


async def test_ohne_adresse_ist_die_pruefung_aus(monkeypatch):
    monkeypatch.setattr(get_settings(), "update_check_url", "")
    assert not updates.enabled()
    with pytest.raises(updates.UpdateCheckError) as err:
        await updates.check(client_for(lambda r: pytest.fail("darf nicht fragen")))
    assert "abgeschaltet" in str(err.value)
