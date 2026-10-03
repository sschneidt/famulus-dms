"""Anzeigename und Haushaltsname aendern (Praxisfall: beim Einrichten ueber /docs blieb "string" stehen)."""
import httpx

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.main import app

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker


async def test_profil_und_haushalt_umbenennen(clean_database, monkeypatch, tmp_path):
    monkeypatch.setattr(ollama, "client_for", FakeOllama().client)
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)
        me = (await client.get(f"{API}/auth/me", headers=auth)).json()
        assert me["display_name"] == "Admin" and me["household_name"] == "Familie Test"

        r = await client.patch(f"{API}/auth/me", headers=auth, json={"display_name": "  Silvia Muster "})
        assert r.status_code == 200, r.text
        assert r.json()["display_name"] == "Silvia Muster"
        assert (await client.patch(f"{API}/auth/me", headers=auth, json={"display_name": "   "})).status_code == 422
        assert (await client.patch(f"{API}/auth/me", json={"display_name": "X"})).status_code == 401

        r = await client.post(f"{API}/documents", headers=auth,
                              files={"file": ("brief.pdf", pdf("Ein Brief vom 01.09.2026"), "application/pdf")})
        doc_id = r.json()["id"]
        await run_worker()
        doc = (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()
        assert doc["files"][0]["path"].startswith("Familie Test/")

        # Haushalt umbenennen -> Ablage-Ordner zieht mit um
        r = await client.patch(f"{API}/tenant", headers=auth, json={"name": "Familie Muster"})
        assert r.status_code == 200, r.text
        assert r.json() == {"name": "Familie Muster", "documents_refiled": 1}
        await run_worker()
        doc = (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()
        assert doc["files"][0]["path"].startswith("Familie Muster/")
        assert (tmp_path / doc["files"][0]["path"]).is_file()
        assert not (tmp_path / "Familie Test").exists()
        assert (await client.get(f"{API}/auth/me", headers=auth)).json()["household_name"] == "Familie Muster"
        assert (await client.get(f"{API}/tenant", headers=auth)).json()["name"] == "Familie Muster"
