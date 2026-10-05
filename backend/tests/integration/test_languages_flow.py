"""Mehrsprachigkeit: Sprache im Konto, Meldungen je Sprache, Sprachpakete der Texterkennung
(Auswahl bei der Einrichtung, Seite "Sprachen", Nachladen im Hintergrund - Download simuliert)."""
import types

import httpx

from homedms.config import get_settings
from homedms.core import ocr_languages, setup_code
from homedms.main import app

from .helpers import API, run_worker

MODEL = b"\0" * (ocr_languages.MIN_MODEL_BYTES + 10)


def _fake_download(monkeypatch, requested: list[str]) -> None:
    """Statt tessdata_fast auf GitHub: fra/rus liefern, alles andere 404."""
    def handler(request: httpx.Request) -> httpx.Response:
        code = request.url.path.rsplit("/", 1)[-1].removesuffix(".traineddata")
        requested.append(code)
        return httpx.Response(200, content=MODEL) if code in ("fra", "rus") else httpx.Response(404)

    def client(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(ocr_languages, "httpx", types.SimpleNamespace(
        AsyncClient=client, Timeout=httpx.Timeout, HTTPError=httpx.HTTPError))


def _by_code(data: dict) -> dict:
    return {lang["code"]: lang for lang in data["languages"]}


async def test_sprachen_und_sprachpakete(clean_database, monkeypatch, tmp_path):
    # mitgelieferte Pakete: deu, eng (+ osd); eigener tessdata-Ordner im Testverzeichnis
    system = tmp_path / "system"
    system.mkdir()
    for code in ("deu", "eng", "osd"):
        (system / f"{code}.traineddata").write_bytes(MODEL)
    monkeypatch.setattr(ocr_languages, "system_dir", lambda: system)
    monkeypatch.setattr(get_settings(), "tessdata_dir", str(tmp_path / "tessdata"))
    monkeypatch.setattr(get_settings(), "ocr_languages", "deu+eng")
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path / "docs"))
    requested: list[str] = []
    _fake_download(monkeypatch, requested)
    ocr_languages.prepare()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Einrichtung: Auswahl der Sprachpakete wird angeboten
        status = (await client.get(f"{API}/setup/status")).json()
        offered = {c["code"]: c["installed"] for c in status["ocr_languages"]}
        assert offered["deu"] and offered["eng"] and not offered["fra"] and "osd" not in offered

        r = await client.post(f"{API}/setup/bootstrap", headers={"Accept-Language": "en"}, json={
            "household_name": "Familie Test", "admin_email": "admin@example.com",
            "admin_password": "admin-passwort", "admin_display_name": "Admin",
            "setup_code": "falsch", "default_language": "en", "ocr_languages": ["eng", "deu", "fra"],
        })
        assert r.status_code == 403 and r.json()["detail"].startswith("The setup code is wrong")
        r = await client.post(f"{API}/setup/bootstrap", json={
            "household_name": "Familie Test", "admin_email": "admin@example.com",
            "admin_password": "admin-passwort", "admin_display_name": "Admin",
            "setup_code": setup_code.get_or_create(), "default_language": "en",
            "ocr_languages": ["eng", "deu", "fra"],
        })
        assert r.status_code == 201, r.text
        token = (await client.post(f"{API}/auth/login", json={
            "email": "admin@example.com", "password": "admin-passwort"})).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert (await client.get(f"{API}/auth/me", headers=auth)).json()["locale"] == "en"

        # fra fehlt -> Download laeuft im Hintergrund
        data = (await client.get(f"{API}/ocr-languages", headers=auth)).json()
        assert _by_code(data)["fra"]["status"] == "installing" and data["effective"] == "eng+deu"
        await run_worker()
        data = (await client.get(f"{API}/ocr-languages", headers=auth)).json()
        assert _by_code(data)["fra"]["status"] == "installed" and data["effective"] == "eng+deu+fra"
        assert (tmp_path / "tessdata" / "fra.traineddata").is_file()
        assert requested == ["fra"]

        # Auswahl aendern: unbekannt -> 422 (in der Sprache der Anfrage), ita scheitert beim Download
        r = await client.put(f"{API}/ocr-languages", headers={**auth, "Accept-Language": "ru"},
                             json={"languages": ["deu", "xyz"]})
        assert r.status_code == 422 and r.json()["detail"] == "Неизвестный языковой пакет: xyz"
        r = await client.put(f"{API}/ocr-languages", headers=auth, json={"languages": ["deu", "ita"]})
        assert r.status_code == 200, r.text
        await run_worker()
        data = (await client.get(f"{API}/ocr-languages", headers=auth)).json()
        ita = _by_code(data)["ita"]
        assert ita["status"] == "failed" and "404" in ita["error"]
        # eng bleibt wegen der Oberflaechensprache dabei
        assert _by_code(data)["eng"]["required_by"] == ["Admin"] and data["effective"] == "deu+eng"

        # Sprache im Konto auf Russisch -> rus wird nachgeladen, Meldungen auf Russisch
        r = await client.patch(f"{API}/auth/me", headers=auth, json={"locale": "ru"})
        assert r.status_code == 200 and r.json()["locale"] == "ru"
        assert (await client.patch(f"{API}/auth/me", headers=auth, json={"locale": "fr"})).status_code == 422
        await run_worker()
        data = (await client.get(f"{API}/ocr-languages", headers=auth)).json()
        assert _by_code(data)["rus"]["status"] == "installed" and _by_code(data)["rus"]["required_by"] == ["Admin"]
        assert data["effective"] == "deu+rus"
        r = await client.get(f"{API}/documents/00000000-0000-0000-0000-000000000000",
                             headers={**auth, "Accept-Language": "ru"})
        assert r.status_code == 404 and r.json()["detail"] == "Документ не найден"

        # fehlgeschlagenes Paket erneut anstossen
        r = await client.post(f"{API}/ocr-languages/install", headers=auth)
        assert _by_code(r.json())["ita"]["status"] == "installing"
