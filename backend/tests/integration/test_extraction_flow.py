"""Metadaten- und Fristenerkennung gegen echte DB, mit Ollama-Attrappe (tests/integration/fake_ollama.py).
Prueft die Regeln aus Anforderungsdokument 4.4a: Vorschlaege statt automatischer Uebernahme,
Schutz gegen erfundene Fristen, keine Doppel-Vorschlaege, Nutzereingaben werden nicht
ueberschrieben, Ausfall der KI."""
import uuid
from datetime import date

import httpx
from sqlalchemy import text

from homedms.ai import ollama
from homedms.core.security import hash_password
from homedms.db import async_session_factory
from homedms.jobs import app as jobs_app
from homedms.main import app
from homedms.models.tenant import Tenant, User, UserRole
from homedms.tasks import extraction

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker

RECHNUNG = """Stadtwerke Musterstadt GmbH
Stromrechnung vom 01.09.2026
Betrag: 42,00 EUR - zahlbar bis 15.10.2026"""


async def rerun_extraction(doc_id: str) -> None:
    """Extraktion erneut anstossen, als liefe sie zum ersten Mal (Status zuruecksetzen)."""
    async with async_session_factory() as db:
        await db.execute(text("UPDATE documents SET extraction_status = 'pending' WHERE id = :id"), {"id": uuid.UUID(doc_id)})
        await db.commit()
    async with jobs_app.open_async():
        await jobs_app.configure_task("extract_metadata").defer_async(document_id=doc_id)
    await run_worker()


async def test_metadata_and_deadline_proposals(clean_database, monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(ollama, "client_for", fake.client)
    monkeypatch.setattr(extraction, "today", lambda: date(2026, 9, 28))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)
        me = (await client.get(f"{API}/auth/me", headers=auth)).json()

        async def upload(text_: str) -> str:
            r = await client.post(f"{API}/documents", headers=auth, files={"file": ("dok.pdf", pdf(text_), "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def detail(doc_id: str) -> dict:
            return (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()

        async def proposals(doc_id: str) -> list[dict]:
            return (await client.get(f"{API}/documents/{doc_id}/wiedervorlagen", headers=auth)).json()

        # --- 1. Metadaten werden eingetragen, Frist wird Vorschlag ------------------------
        d1 = await upload(RECHNUNG)
        await run_worker()
        doc = await detail(d1)
        assert doc["extraction_status"] == "done"
        assert doc["document_date"] == "2026-09-01"
        assert doc["issuer"] == "Stadtwerke Musterstadt GmbH"
        assert doc["amount"] == 42.0
        [wv] = await proposals(d1)  # die erfundene Frist der Attrappe wurde verworfen
        assert wv["status"] == "vorgeschlagen" and wv["source"] == "ai_suggested"
        assert wv["due_date"] == "2026-10-15" and wv["note"] == "Zahlungsfrist"
        assert wv["source_snippet"] == "zahlbar bis 15.10.2026"
        assert wv["assigned_user_id"] == me["id"] and wv["confidence"] == 0.9
        assert fake.extract_calls == 1

        overview = (await client.get(f"{API}/wiedervorlagen?status=vorgeschlagen", headers=auth)).json()
        assert overview["total"] == 1 and overview["items"][0]["id"] == wv["id"]

        # --- 2. Bestaetigen: vorgeschlagen -> offen, danach nicht nochmal ------------------
        r = await client.post(f"{API}/wiedervorlagen/{wv['id']}/confirm", headers=auth)
        assert r.status_code == 200 and r.json()["status"] == "offen"
        assert (await client.post(f"{API}/wiedervorlagen/{wv['id']}/confirm", headers=auth)).status_code == 409
        assert (await client.post(f"{API}/wiedervorlagen/{wv['id']}/reject", headers=auth)).status_code == 409

        # --- 3. Keine Doppel-Vorschlaege, Nutzereingaben bleiben --------------------------
        r = await client.patch(f"{API}/documents/{d1}", headers=auth, json={"issuer": "Stadtwerke", "amount": 40.5})
        assert r.status_code == 200 and r.json()["amount"] == 40.5
        await rerun_extraction(d1)
        doc = await detail(d1)
        assert doc["issuer"] == "Stadtwerke" and doc["amount"] == 40.5  # nicht ueberschrieben
        assert len(await proposals(d1)) == 1  # offene KI-Wiedervorlage -> kein neuer Vorschlag

        # --- 4. Verwerfen --------------------------------------------------------------
        d2 = await upload(RECHNUNG.replace("15.10.2026", "20.11.2026"))
        await run_worker()
        [wv2] = await proposals(d2)
        r = await client.post(f"{API}/wiedervorlagen/{wv2['id']}/reject", headers=auth)
        assert r.status_code == 200 and r.json()["status"] == "verworfen"
        assert (await client.get(f"{API}/wiedervorlagen?status=verworfen", headers=auth)).json()["total"] == 1
        assert (await client.get(f"{API}/wiedervorlagen?status=quatsch", headers=auth)).status_code == 422

        # --- 5. Dokument ohne Fristen: Metadaten ja, Vorschlaege nein --------------------
        d3 = await upload("Musterverein e.V.\nEinladung vom 10.09.2026 zum Sommerfest")
        await run_worker()
        doc = await detail(d3)
        assert doc["extraction_status"] == "done" and doc["document_date"] == "2026-09-10" and doc["amount"] is None
        assert await proposals(d3) == []

        # --- 6. Papierkorb: Termine des Dokuments verschwinden aus der Uebersicht ----------
        assert (await client.get(f"{API}/wiedervorlagen", headers=auth)).json()["total"] == 2
        await client.delete(f"{API}/documents/{d1}", headers=auth)
        assert (await client.get(f"{API}/wiedervorlagen", headers=auth)).json()["total"] == 1

        # --- 7. KI nicht erreichbar: Extraktion "failed", Dokument sonst in Ordnung --------
        fake.down = True
        d4 = await upload(RECHNUNG)
        await run_worker()
        doc = await detail(d4)
        assert doc["ocr_status"] == "done" and doc["extraction_status"] == "failed"
        assert doc["document_date"] is None and await proposals(d4) == []

        # --- 8. Fremder Haushalt sieht nichts und kann nichts bestaetigen ----------------
        d5 = await upload(RECHNUNG.replace("15.10.2026", "01.12.2026"))
        fake.down = False
        await run_worker()
        [wv5] = await proposals(d5)
        async with async_session_factory() as db:
            other = Tenant(name="Nachbarn")
            db.add(other)
            await db.flush()
            db.add(User(tenant_id=other.id, email="nachbar@example.com", password_hash=hash_password("geheim-123"),
                        display_name="Nachbar", role=UserRole.admin, notification_channels={}))
            await db.commit()
        token = (await client.post(f"{API}/auth/login", json={
            "email": "nachbar@example.com", "password": "geheim-123"})).json()["access_token"]
        nachbar = {"Authorization": f"Bearer {token}"}
        assert (await client.get(f"{API}/wiedervorlagen", headers=nachbar)).json()["total"] == 0
        assert (await client.get(f"{API}/documents/{d5}/wiedervorlagen", headers=nachbar)).status_code == 404
        assert (await client.post(f"{API}/wiedervorlagen/{wv5['id']}/confirm", headers=nachbar)).status_code == 404
        assert (await proposals(d5))[0]["status"] == "vorgeschlagen"
