""""Prüfen > Nicht analysiert": KI-Ausfall und verlorene Auftraege finden, "Alle analysieren" holt nach."""
from datetime import date

import httpx
from sqlalchemy import text

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.db import async_session_factory
from homedms.main import app
from homedms.tasks import extraction

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker

STROM = "Stadtwerke Musterstadt GmbH\nStromrechnung vom 01.09.2026\nBetrag: 42,00 EUR - zahlbar bis 15.10.2026"


async def test_nicht_analysierte_dokumente_nachholen(clean_database, monkeypatch, tmp_path):
    fake = FakeOllama()
    fake.down = True  # z. B. Ollama unter Windows noch nicht gestartet
    monkeypatch.setattr(ollama, "client_for", fake.client)
    monkeypatch.setattr(extraction, "today", lambda: date(2026, 9, 30))
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        async def upload(content: bytes, name: str) -> str:
            r = await client.post(f"{API}/documents", headers=auth, files={"file": (name, content, "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def unanalyzed() -> dict:
            r = await client.get(f"{API}/documents/unanalyzed", headers=auth)
            assert r.status_code == 200, r.text
            return r.json()

        async def detail(doc_id: str) -> dict:
            return (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()

        # --- 1. KI nicht erreichbar: Kategorie und Angaben fehlen ---------------------------------
        strom = await upload(pdf(STROM), "strom.pdf")
        await run_worker()
        doc = await detail(strom)
        assert doc["classification_status"] == "needs_review" and doc["classification_error"]
        assert doc["extraction_status"] == "failed" and doc["subject"] is None

        # --- 2. Verlorener Auftrag: "laeuft" seit einer Stunde, aber nichts in der Warteschlange ----
        haengt = await upload(pdf("Versicherung AG\nBeitragsrechnung vom 02.09.2026"), "vers.pdf")
        await run_worker()
        async with async_session_factory() as db:
            await db.execute(text(
                "UPDATE documents SET ocr_status='pending', updated_at = now() - interval '1 hour' WHERE id = :id"
            ), {"id": haengt})
            await db.commit()

        # --- 3. Gerade hochgeladen (Auftrag wartet): gehoert NICHT in die Liste -------------------
        frisch = await upload(pdf("Brief vom 03.09.2026"), "frisch.pdf")

        data = await unanalyzed()
        assert data["ai_available"] is False
        by_id = {item["id"]: item for item in data["items"]}
        assert set(by_id) == {strom, haengt}
        assert by_id[strom]["reasons"] == [
            "Kategorie: KI war nicht erreichbar", "Betreff, Absender, Fristen: KI war nicht erreichbar",
        ]
        assert by_id[haengt]["reasons"] == ["Texterkennung wurde unterbrochen"]

        # --- 4. KI wieder da -> "Alle analysieren" holt genau das Fehlende nach --------------------
        fake.down = False
        assert (await unanalyzed())["ai_available"] is True
        r = await client.post(f"{API}/documents/unanalyzed/analyze", headers=auth)
        assert r.status_code == 200, r.text
        assert r.json() == {"queued": 2, "jobs": 3}  # strom: Einordnung + Angaben, haengt: Texterkennung
        await run_worker()

        doc = await detail(strom)
        assert doc["classification_error"] is None
        assert doc["classification_status"] == "auto_assigned" and doc["extraction_status"] == "done"
        assert doc["amount"] == 42.0
        assert (await detail(haengt))["ocr_status"] == "done"
        assert (await detail(frisch))["ocr_status"] == "done"
        assert (await unanalyzed())["total"] == 0

        # Nichts mehr zu tun -> nichts eingereiht
        r = await client.post(f"{API}/documents/unanalyzed/analyze", headers=auth)
        assert r.json() == {"queued": 0, "jobs": 0}
