"""Zahlungen gegen echte DB: alte eingescannte Rechnungen gelten als bezahlt, neue lassen sich mit
Datum als bezahlt markieren - ueber das Dokument oder ueber den Zahlungstermin."""
from datetime import date

import httpx

from homedms.ai import ollama
from homedms.api.routes import documents as documents_route
from homedms.api.routes import wiedervorlagen as wv_route
from homedms.config import get_settings
from homedms.main import app
from homedms.tasks import extraction

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker

TODAY = date(2026, 9, 30)


def rechnung(faellig: str) -> str:
    return f"""Stadtwerke Musterstadt GmbH
Stromrechnung vom 01.02.2026
Betrag: 42,00 EUR - zahlbar bis {faellig}"""


async def test_zahlungen(clean_database, monkeypatch, tmp_path):
    monkeypatch.setattr(ollama, "client_for", FakeOllama().client)
    for module in (extraction, documents_route, wv_route):
        monkeypatch.setattr(module, "today", lambda: TODAY)
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        async def upload(text_: str) -> str:
            r = await client.post(f"{API}/documents", headers=auth, files={"file": ("r.pdf", pdf(text_), "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def detail(doc_id: str) -> dict:
            return (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()

        async def termine(doc_id: str) -> list[dict]:
            return (await client.get(f"{API}/documents/{doc_id}/wiedervorlagen", headers=auth)).json()

        alt = await upload(rechnung("15.03.2026"))  # > 3 Monate vor dem 30.09.2026
        neu = await upload(rechnung("15.10.2026"))
        neu2 = await upload(rechnung("20.10.2026"))
        kuerzlich = await upload(rechnung("01.09.2026"))  # verstrichen, aber < 3 Monate
        await run_worker()

        # --- 1. Alte eingescannte Rechnung: automatisch bezahlt, Frist nur dokumentiert ----------
        doc = await detail(alt)
        assert (doc["payment_status"], doc["paid_on"], doc["paid_assumed"]) == ("bezahlt", None, True)
        assert [(t["note"], t["status"], t["due_date"]) for t in await termine(alt)] == [
            ("Zahlungsfrist", "erledigt", "2026-03-15")
        ]

        # Kuerzlich verstrichen: offen, ueberfaelliger Vorschlag ("schon bezahlt?")
        doc = await detail(kuerzlich)
        assert doc["payment_status"] == "offen"
        assert [(t["status"], t["due_date"]) for t in await termine(kuerzlich)] == [("vorgeschlagen", "2026-09-01")]

        # --- 2. Neue Rechnung: offen, Vorschlag; als bezahlt markieren mit Datum ----------------
        doc = await detail(neu)
        assert doc["payment_status"] == "offen"
        assert [t["status"] for t in await termine(neu)] == ["vorgeschlagen"]
        offen = (await client.get(f"{API}/documents", headers=auth, params={"payment_status": "offen"})).json()
        assert {d["id"] for d in offen["items"]} == {neu, neu2, kuerzlich}

        # Uebersicht "Unbezahlt": naechste Frist zuerst (ueberfaellig vorn), Summe der Betraege
        unpaid = (await client.get(f"{API}/documents/unpaid", headers=auth)).json()
        assert [(d["id"], d["payment_due"]) for d in unpaid["items"]] == [
            (kuerzlich, "2026-09-01"), (neu, "2026-10-15"), (neu2, "2026-10-20"),
        ]
        assert (unpaid["total"], unpaid["total_amount"]) == (3, 126.0)

        r = await client.patch(f"{API}/documents/{neu}", headers=auth, json={"payment_status": "bezahlt", "paid_on": "2026-10-02"})
        assert r.status_code == 200, r.text
        assert (r.json()["payment_status"], r.json()["paid_on"], r.json()["paid_assumed"]) == ("bezahlt", "2026-10-02", False)
        assert [t["status"] for t in await termine(neu)] == ["erledigt"]  # Vorschlag hat sich erledigt

        # Datum korrigieren, dann doch wieder offen
        r = await client.patch(f"{API}/documents/{neu}", headers=auth, json={"paid_on": "2026-10-03"})
        assert r.json()["paid_on"] == "2026-10-03"
        r = await client.patch(f"{API}/documents/{neu}", headers=auth, json={"payment_status": "offen"})
        assert (r.json()["payment_status"], r.json()["paid_on"]) == ("offen", None)
        # Zahlungsdatum ohne "bezahlt" ist ein Fehler
        r = await client.patch(f"{API}/documents/{neu}", headers=auth, json={"paid_on": "2026-10-03"})
        assert r.status_code == 422

        # --- 3. Ueber den Termin: Zahlungsfrist bestaetigen und mit Datum erledigen ------------
        wv_id = (await termine(neu2))[0]["id"]
        assert (await client.post(f"{API}/wiedervorlagen/{wv_id}/confirm", headers=auth)).status_code == 200
        r = await client.post(f"{API}/wiedervorlagen/{wv_id}/complete", headers=auth, json={"paid_on": "2026-10-05"})
        assert r.status_code == 200, r.text
        doc = await detail(neu2)
        assert (doc["payment_status"], doc["paid_on"]) == ("bezahlt", "2026-10-05")

        # Ohne Datum: heute
        r = await client.patch(f"{API}/documents/{neu}", headers=auth, json={"payment_status": "bezahlt"})
        assert r.json()["paid_on"] == TODAY.isoformat()
