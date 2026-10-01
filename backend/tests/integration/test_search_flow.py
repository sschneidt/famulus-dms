"""Volltextsuche (GET /documents?q=...) gegen echte DB.

- Mit echtem Meilisearch, wenn MEILISEARCH_URL auf eine laufende Instanz zeigt (sonst uebersprungen):
  Tippfehler-Toleranz, Teilwoerter, Haushalts-Trennung, Papierkorb. Eigener Index je Testlauf.
- Immer: Rueckfall auf die Teilwort-Suche in der Datenbank, wenn Meilisearch nicht erreichbar ist.
"""
import asyncio
import os
import uuid
from datetime import date

import httpx
import pytest

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.core import meili
from homedms.core.security import hash_password
from homedms.db import async_session_factory
from homedms.main import app
from homedms.models.tenant import Tenant, User, UserRole
from homedms.tasks import extraction

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker

WASSERSCHADEN = """Sanitaer Mueller GmbH
Rechnung vom 12.09.2026
Reparatur des Wasserschadens im Bad, Austausch Eckventil
Betrag: 380,00 EUR"""

STROM = """Stadtwerke Musterstadt GmbH
Stromrechnung vom 01.09.2026
Betrag: 42,00 EUR - zahlbar bis 15.10.2026"""


def meili_available() -> bool:
    url = os.environ.get("MEILISEARCH_URL")
    if not url:
        return False
    try:
        return httpx.get(f"{url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


async def wait_for_index(c: meili.MeiliClient) -> None:
    for _ in range(100):
        tasks = await c._request("GET", f"/tasks?indexUids={meili.INDEX}&statuses=enqueued,processing")
        if not tasks.get("results"):
            return
        await asyncio.sleep(0.1)
    raise AssertionError("Meilisearch hat den Index nicht aktualisiert")


async def setup(client, monkeypatch, tmp_path) -> tuple[dict, dict[str, str]]:
    monkeypatch.setattr(ollama, "client_for", FakeOllama().client)
    monkeypatch.setattr(extraction, "today", lambda: date(2026, 9, 30))
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))
    auth = await bootstrap_and_login(client)
    ids = {}
    for name, text_ in (("wasser", WASSERSCHADEN), ("strom", STROM)):
        r = await client.post(f"{API}/documents", headers=auth, files={"file": (f"{name}.pdf", pdf(text_), "application/pdf")})
        assert r.status_code == 201, r.text
        ids[name] = r.json()["id"]
    return auth, ids


async def search(client, auth, q: str, **params) -> dict:
    r = await client.get(f"{API}/documents", headers=auth, params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.skipif(not meili_available(), reason="kein Meilisearch unter MEILISEARCH_URL erreichbar")
async def test_suche_mit_meilisearch(clean_database, monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(meili, "INDEX", f"test_{uuid.uuid4().hex[:8]}")
    real = meili.MeiliClient(os.environ["MEILISEARCH_URL"], settings.meilisearch_key)
    monkeypatch.setattr(meili, "client", lambda: real)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth, ids = await setup(client, monkeypatch, tmp_path)
        await run_worker()  # OCR -> KI -> Ablage + Suchindex
        await wait_for_index(real)

        # Tippfehler-Toleranz (nur Meilisearch) mit markiertem Treffer im Ausschnitt
        result = await search(client, auth, "wasserschadn")
        assert [d["id"] for d in result["items"]] == [ids["wasser"]]
        assert any(s["hit"] for s in result["items"][0]["search_snippet"])

        # Wortteil in zusammengesetztem Wort (nur Datenbank-Teilwortsuche)
        assert [d["id"] for d in (await search(client, auth, "schaden"))["items"]] == [ids["wasser"]]
        # Umlaut-Umschreibung (Meilisearch)
        assert [d["id"] for d in (await search(client, auth, "stadtwerk"))["items"]] == [ids["strom"]]
        # Kombination mit Filter
        r = await search(client, auth, "rechnung", status="confirmed")
        assert r["total"] == 0
        assert (await search(client, auth, "rechnung"))["total"] == 2

        # Anderer Haushalt sieht nichts davon - auch nicht ueber den gemeinsamen Index
        async with async_session_factory() as db:
            other = Tenant(name="Nachbarn")
            db.add(other)
            await db.flush()
            db.add(User(tenant_id=other.id, email="nachbar@example.com", password_hash=hash_password("geheim-123"),
                        display_name="Nachbar", role=UserRole.admin, notification_channels={}))
            await db.commit()
        token = (await client.post(f"{API}/auth/login", json={
            "email": "nachbar@example.com", "password": "geheim-123"})).json()["access_token"]
        assert (await search(client, {"Authorization": f"Bearer {token}"}, "wasserschadn"))["total"] == 0

        # Papierkorb: verschwindet aus der Suche (und aus dem Index)
        assert (await client.delete(f"{API}/documents/{ids['wasser']}", headers=auth)).status_code == 204
        await run_worker()
        await wait_for_index(real)
        assert (await search(client, auth, "wasserschadn"))["total"] == 0
        hits = await real.search("wasserschadn", str((await client.get(f"{API}/auth/me", headers=auth)).json()["tenant_id"]))
        assert hits == []
        await real._request("DELETE", f"/indexes/{meili.INDEX}")


async def test_suche_ohne_meilisearch(clean_database, monkeypatch, tmp_path):
    """Faellt Meilisearch aus, sucht die Datenbank weiter - nur ohne Tippfehler-Toleranz."""
    down = meili.MeiliClient("http://127.0.0.1:9", "x")
    monkeypatch.setattr(meili, "client", lambda: down)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth, ids = await setup(client, monkeypatch, tmp_path)
        await run_worker()  # Indexieren scheitert nur mit Warnung, Ablage klappt trotzdem

        result = await search(client, auth, "Wasserschaden Bad")
        assert [d["id"] for d in result["items"]] == [ids["wasser"]]
        snippet = result["items"][0]["search_snippet"]
        assert [s["text"].lower() for s in snippet if s["hit"]] == ["wasserschaden", "bad"]
        assert (await search(client, auth, "wasserschadn"))["total"] == 0  # kein Tippfehler-Ausgleich
        assert (await search(client, auth, "100%"))["total"] == 0  # Platzhalter woertlich
        # Seitenweise
        page1 = await search(client, auth, "rechnung", page_size=1)
        page2 = await search(client, auth, "rechnung", page_size=1, page=2)
        assert page1["total"] == 2 and len(page1["items"]) == 1
        assert {page1["items"][0]["id"], page2["items"][0]["id"]} == set(ids.values())
        # ohne q bleibt alles wie bisher (keine Ausschnitte)
        plain = (await client.get(f"{API}/documents", headers=auth)).json()
        assert plain["total"] == 2 and all(d["search_snippet"] is None for d in plain["items"])
