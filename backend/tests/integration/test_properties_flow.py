"""Objekte von Hand anlegen (POST /properties) gegen echte DB."""
import httpx

from homedms.main import app

from .helpers import API, bootstrap_and_login


async def test_objekt_von_hand_anlegen(clean_database):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        # Nur ein Name genuegt
        r = await client.post(f"{API}/properties", headers=auth, json={"name": "  Gartenhaus "})
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "Gartenhaus" and r.json()["street"] == "" and r.json()["document_count"] == 0

        # Mit Adresse
        r = await client.post(f"{API}/properties", headers=auth, json={
            "name": "Ferienwohnung", "street": "Seeweg 12a", "postal_code": "88709", "city": "Meersburg"})
        assert r.status_code == 201, r.text

        names = [p["name"] for p in (await client.get(f"{API}/properties", headers=auth)).json()]
        assert names == ["Ferienwohnung", "Gartenhaus"]

        # Doppelt: gleicher Name (egal wie geschrieben), gleiche Adresse anders geschrieben
        r = await client.post(f"{API}/properties", headers=auth, json={"name": "gartenhaus"})
        assert r.status_code == 409
        r = await client.post(f"{API}/properties", headers=auth, json={
            "name": "Meersburg Seeweg", "street": "Seeweg 12 A", "postal_code": "88709", "city": "Meersburg"})
        assert r.status_code == 409 and "Ferienwohnung" in r.json()["detail"]

        # Halbe Adresse und leerer Name
        r = await client.post(f"{API}/properties", headers=auth, json={"name": "Halb", "street": "Seeweg 1"})
        assert r.status_code == 422
        assert (await client.post(f"{API}/properties", headers=auth, json={"name": "   "})).status_code == 422

        # Ohne Anmeldung nicht
        assert (await client.post(f"{API}/properties", json={"name": "X"})).status_code in (401, 403)
