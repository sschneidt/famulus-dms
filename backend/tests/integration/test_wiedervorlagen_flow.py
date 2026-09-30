"""Wiedervorlagen vollstaendig (Anforderungsdokument 4.4a) gegen echte DB: anlegen, aendern,
bestaetigen, erledigen mit Folgetermin, loeschen, Aufbewahrungsregeln."""
import uuid
from datetime import date

import httpx

from homedms.ai import ollama
from homedms.api.routes import wiedervorlagen as wv_routes
from homedms.main import app
from homedms.tasks import extraction

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker

TODAY = date(2026, 9, 30)
RECHNUNG = """Stadtwerke Musterstadt GmbH
Stromrechnung vom 01.09.2026
Betrag: 42,00 EUR - zahlbar bis 15.10.2026"""


async def test_wiedervorlagen_lifecycle(clean_database, monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(ollama, "client_for", fake.client)
    monkeypatch.setattr(extraction, "today", lambda: TODAY)
    monkeypatch.setattr(wv_routes, "today", lambda: TODAY)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)
        me = (await client.get(f"{API}/auth/me", headers=auth)).json()
        cats = {c["name"]: c["id"] for c in (await client.get(f"{API}/categories", headers=auth)).json()}

        async def upload(text_: str) -> str:
            r = await client.post(f"{API}/documents", headers=auth, files={"file": ("d.pdf", pdf(text_), "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def wvs(doc_id: str) -> list[dict]:
            return (await client.get(f"{API}/documents/{doc_id}/wiedervorlagen", headers=auth)).json()

        async def post(path: str, json=None):
            return await client.post(f"{API}{path}", headers=auth, json=json)

        async def patch(path: str, json):
            return await client.patch(f"{API}{path}", headers=auth, json=json)

        d1 = await upload(RECHNUNG)
        await run_worker()
        doc = (await client.get(f"{API}/documents/{d1}", headers=auth)).json()
        assert doc["category_id"] == cats["Wohnen & Nebenkosten"] and doc["document_date"] == "2026-09-01"

        # --- KI-Vorschlag: Bezeichnung geglaettet, korrigieren, bestaetigen, erledigen ------
        [p] = await wvs(d1)
        assert p["note"] == "Zahlungsfrist" and p["status"] == "vorgeschlagen"  # Modell sagte "zahlbar bis"
        assert (await post(f"/wiedervorlagen/{p['id']}/complete")).status_code == 409  # erst bestaetigen
        r = await patch(f"/wiedervorlagen/{p['id']}", {"due_date": "2026-10-20", "note": "Strom bezahlen"})
        assert r.status_code == 200 and r.json()["status"] == "vorgeschlagen" and r.json()["due_date"] == "2026-10-20"
        assert (await post(f"/wiedervorlagen/{p['id']}/confirm")).json()["status"] == "offen"
        r = await post(f"/wiedervorlagen/{p['id']}/complete")
        assert r.status_code == 200
        assert r.json()["completed"]["status"] == "erledigt" and r.json()["completed"]["completed_at"]
        assert r.json()["next"] is None  # einmaliger Termin
        assert (await post(f"/wiedervorlagen/{p['id']}/complete")).status_code == 409
        assert (await patch(f"/wiedervorlagen/{p['id']}", {"note": "x"})).status_code == 409

        # --- Manuell: jaehrlich, rechtzeitig erledigt -> naechstes Jahr ---------------------
        r = await post(f"/documents/{d1}/wiedervorlagen", {
            "due_date": "2026-09-30", "note": "Stromanbieter vergleichen", "recurrence": "yearly"})
        assert r.status_code == 201, r.text
        yearly = r.json()
        assert yearly["status"] == "offen" and yearly["source"] == "manual" and yearly["assigned_user_id"] == me["id"]
        nxt = (await post(f"/wiedervorlagen/{yearly['id']}/complete")).json()["next"]
        assert nxt["due_date"] == "2027-09-30" and nxt["status"] == "offen" and nxt["recurrence"] == "yearly"
        assert nxt["note"] == "Stromanbieter vergleichen"

        # --- Monatlich, zu spaet erledigt -> naechster kuenftiger Termin, keine Nachholreihe --
        monthly = (await post(f"/documents/{d1}/wiedervorlagen", {
            "due_date": "2026-06-15", "note": "Zaehlerstand ablesen", "recurrence": "monthly"})).json()
        assert (await post(f"/wiedervorlagen/{monthly['id']}/complete")).json()["next"]["due_date"] == "2026-10-15"

        # --- Alle 3 Monate (custom_months) ------------------------------------------------
        quarterly = (await post(f"/documents/{d1}/wiedervorlagen", {
            "due_date": "2026-10-01", "note": "Abschlag pruefen", "recurrence": "custom_months",
            "recurrence_interval_months": 3})).json()
        assert (await post(f"/wiedervorlagen/{quarterly['id']}/complete")).json()["next"]["due_date"] == "2027-01-01"

        # --- Validierung -------------------------------------------------------------------
        assert (await post(f"/documents/{d1}/wiedervorlagen", {
            "due_date": "2026-10-01", "note": "x", "recurrence": "custom_months"})).status_code == 422
        assert (await post(f"/documents/{d1}/wiedervorlagen", {
            "due_date": "2026-10-01", "note": "x", "assigned_user_id": str(uuid.uuid4())})).status_code == 422
        assert (await post(f"/documents/{uuid.uuid4()}/wiedervorlagen", {
            "due_date": "2026-10-01", "note": "x"})).status_code == 404

        # --- Loeschen ----------------------------------------------------------------------
        tmp = (await post(f"/documents/{d1}/wiedervorlagen", {"due_date": "2026-11-01", "note": "weg damit"})).json()
        assert (await client.delete(f"{API}/wiedervorlagen/{tmp['id']}", headers=auth)).status_code == 204
        assert tmp["id"] not in [w["id"] for w in await wvs(d1)]

        # --- Aufbewahrungsregel: legt Termin fuer bestehende Dokumente an --------------------
        r = await post("/retention-rules", {"category_id": cats["Wohnen & Nebenkosten"],
                                            "retention_period_months": 24, "requires_original": True})
        assert r.status_code == 201, r.text
        rule = r.json()
        assert (await post("/retention-rules", {"category_id": cats["Wohnen & Nebenkosten"],
                                                "retention_period_months": 12})).status_code == 409

        def retention(items):
            found = [w for w in items if w["source"] == "retention_rule"]
            assert len(found) <= 1
            return found[0] if found else None

        ret = retention(await wvs(d1))
        assert ret["due_date"] == "2028-09-01" and ret["type"] == "retention" and ret["status"] == "offen"
        assert "2 Jahre" in ret["note"] and "Original" in ret["note"]

        # Regel aendern -> Termin wandert mit
        assert (await patch(f"/retention-rules/{rule['id']}", {"retention_period_months": 120})).status_code == 200
        assert retention(await wvs(d1))["due_date"] == "2036-09-01"
        # Dokumentdatum aendern -> Termin wandert mit
        await patch(f"/documents/{d1}", {"document_date": "2026-08-01"})
        ret = retention(await wvs(d1))
        assert ret["due_date"] == "2036-08-01"
        # Termin selbst ist an die Regel gebunden, die Notiz nicht
        assert (await patch(f"/wiedervorlagen/{ret['id']}", {"due_date": "2030-01-01"})).status_code == 409
        assert (await patch(f"/wiedervorlagen/{ret['id']}", {"reminder_lead_days": 60})).status_code == 200

        # Kategorie ohne Regel -> Termin verschwindet, zurueck -> Termin wieder da
        await post(f"/documents/{d1}/category", {"category_id": cats["Steuern"]})
        assert retention(await wvs(d1)) is None
        await post(f"/documents/{d1}/category", {"category_id": cats["Wohnen & Nebenkosten"]})
        assert retention(await wvs(d1))["due_date"] == "2036-08-01"
        await run_worker()  # Lernbeispiele der manuellen Zuordnungen

        # Neues Dokument: automatisch klassifiziert + Datum erkannt -> Termin automatisch
        d3 = await upload(RECHNUNG.replace("01.09.2026", "15.09.2026"))
        await run_worker()
        assert retention(await wvs(d3))["due_date"] == "2036-09-15"

        # Erledigter Aufbewahrungstermin wird nicht neu angelegt
        ret1 = retention(await wvs(d1))
        assert (await post(f"/wiedervorlagen/{ret1['id']}/complete")).json()["next"] is None
        await patch(f"/retention-rules/{rule['id']}", {"notify_before_days": 14})
        assert [w["status"] for w in await wvs(d1) if w["source"] == "retention_rule"] == ["erledigt"]
        assert retention(await wvs(d3))["reminder_lead_days"] == 14

        # Regel loeschen -> offene Aufbewahrungstermine weg, erledigte bleiben
        assert (await client.delete(f"{API}/retention-rules/{rule['id']}", headers=auth)).status_code == 204
        assert retention(await wvs(d3)) is None
        assert [w["status"] for w in await wvs(d1) if w["source"] == "retention_rule"] == ["erledigt"]
        assert (await client.get(f"{API}/retention-rules", headers=auth)).json() == []
