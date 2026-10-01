"""Automatische Benennung und Ablage nach Kategorie/Jahr (homedms/core/filing.py) gegen echte DB,
mit echten Dateien in einem temporaeren Dokumente-Ordner."""
from datetime import date
from pathlib import Path

import httpx

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.main import app
from homedms.tasks import extraction

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker

WASSERSCHADEN = """Sanitaer Mueller GmbH
Industriestrasse 3, 70565 Stuttgart
Rechnung vom 12.09.2026
Objekt: Seeweg 12a, 88709 Meersburg
Reparatur Wasserschaden im Bad, Austausch Eckventil
Betrag: 380,00 EUR"""

HEIZUNG = """Sanitaer Mueller GmbH
Industriestrasse 3, 70565 Stuttgart
Rechnung vom 02.03.2026
Objekt: Seeweg 12 a, 88709 Meersburg
Reparatur Wasserschaden Heizungskeller
Betrag: 120,00 EUR"""

OHNE_OBJEKT = """Sanitaer Mueller GmbH
Industriestrasse 3, 70565 Stuttgart
Rechnung vom 05.05.2026
Reparatur Wasserschaden Garage
Betrag: 90,00 EUR"""

UNKLAR = """Hallo zusammen,
bis bald und viele Gruesse"""


def files_under(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


async def test_benennung_und_ablage(clean_database, monkeypatch, tmp_path):
    fake = FakeOllama()
    monkeypatch.setattr(ollama, "client_for", fake.client)
    monkeypatch.setattr(extraction, "today", lambda: date(2026, 9, 30))
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)  # Haushalt "Familie Test"

        async def upload(text_: str, name: str, title: str = "") -> str:
            data = {"title": title} if title else {}
            r = await client.post(f"{API}/documents", headers=auth, data=data,
                                  files={"file": (name, pdf(text_), "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def detail(doc_id: str) -> dict:
            r = await client.get(f"{API}/documents/{doc_id}", headers=auth)
            assert r.status_code == 200, r.text
            return r.json()

        # --- 1. KI erkennt Betreff/Absender/Datum -> Titel, Dateiname, Ordner ------------------
        d1 = await upload(WASSERSCHADEN, "ScannedDocument1.pdf")
        await run_worker()
        doc = await detail(d1)
        assert doc["subject"] == "Rechnung Wasserschaden-Reparatur"
        assert doc["title"] == "Rechnung Wasserschaden-Reparatur – Sanitaer Mueller GmbH"
        assert doc["title_locked"] is False
        expected = "Familie Test/Haus & Reparaturen/Meersburg Seeweg 12a/2026/2026-09-12 Sanitaer Mueller GmbH – Rechnung Wasserschaden-Reparatur.pdf"
        assert doc["files"][0]["path"] == expected
        assert files_under(tmp_path) == [expected]  # alter Upload-Ordner ist aufgeraeumt

        download = await client.get(f"{API}/documents/{d1}/download", headers=auth)
        assert download.status_code == 200
        assert "2026-09-12" in download.headers["content-disposition"]

        # --- 2. Eigener Titel: bleibt, auch wenn sich Absender aendert; Datei folgt dem Titel? ---
        # Der Dateiname nutzt Datum/Absender/Betreff - ein eigener Titel aendert ihn nicht, ein
        # geaenderter Absender schon.
        r = await client.patch(f"{API}/documents/{d1}", headers=auth, json={"title": "Wasserschaden Bad"})
        assert r.json()["title_locked"] is True
        r = await client.patch(f"{API}/documents/{d1}", headers=auth, json={"issuer": "Mueller Haustechnik"})
        assert r.json()["title"] == "Wasserschaden Bad"
        await run_worker()
        assert files_under(tmp_path) == [
            "Familie Test/Haus & Reparaturen/Meersburg Seeweg 12a/2026/2026-09-12 Mueller Haustechnik – Rechnung Wasserschaden-Reparatur.pdf"
        ]

        # --- 3. Zurueck zur automatischen Benennung --------------------------------------------
        r = await client.patch(f"{API}/documents/{d1}", headers=auth, json={"title_locked": False})
        assert r.json()["title"] == "Rechnung Wasserschaden-Reparatur – Mueller Haustechnik"

        # --- 4. Papierkorb und zurueck ----------------------------------------------------------
        assert (await client.delete(f"{API}/documents/{d1}", headers=auth)).status_code == 204
        await run_worker()
        assert files_under(tmp_path) == [
            "Familie Test/_Papierkorb/2026-09-12 Mueller Haustechnik – Rechnung Wasserschaden-Reparatur.pdf"
        ]
        assert (await client.get(f"{API}/documents/{d1}/download", headers=auth)).status_code == 200
        assert (await client.post(f"{API}/documents/{d1}/restore", headers=auth)).status_code == 200
        await run_worker()
        assert files_under(tmp_path)[0].startswith("Familie Test/Haus & Reparaturen/Meersburg Seeweg 12a/2026/")

        # --- 5. Namensgleichheit: zweites Dokument bekommt " (2)" ------------------------------
        d2 = await upload(WASSERSCHADEN, "Kopie.pdf")
        await run_worker()
        await client.patch(f"{API}/documents/{d2}", headers=auth, json={"issuer": "Mueller Haustechnik"})
        await run_worker()
        names = [Path(p).name for p in files_under(tmp_path)]
        assert "2026-09-12 Mueller Haustechnik – Rechnung Wasserschaden-Reparatur (2).pdf" in names
        assert len(names) == 2

        # --- 6. Nichts erkannt, Titel beim Upload gesetzt: Titel bleibt, Ablage "_Unsortiert" --
        # (Der erfundene Betreff der Attrappe wird verworfen, weil er nicht im Text steht.)
        d3 = await upload(UNKLAR, "brief.pdf", title="Brief von Oma")
        await run_worker()
        doc3 = await detail(d3)
        assert doc3["title"] == "Brief von Oma" and doc3["title_locked"] is True
        assert doc3["subject"] is None
        assert doc3["classification_status"] == "needs_review"
        assert doc3["files"][0]["path"].startswith("Familie Test/_Unsortiert/2026/")
        assert doc3["files"][0]["path"].endswith(".pdf")

        # --- 7. Objekte: gleiche Adresse anders geschrieben -> dasselbe Objekt; Absenderadresse
        #         wird nie ein Objekt ("_Ohne Adresse"); Umbenennen benennt den Ordner um ------------
        d4 = await upload(HEIZUNG, "heizung.pdf")
        d5 = await upload(OHNE_OBJEKT, "garage.pdf")
        await run_worker()
        props = (await client.get(f"{API}/properties", headers=auth)).json()
        assert [(p["name"], p["document_count"]) for p in props] == [("Meersburg Seeweg 12a", 3)]
        assert (await detail(d4))["property_id"] == props[0]["id"]
        doc5 = await detail(d5)
        assert doc5["property_id"] is None
        assert doc5["files"][0]["path"].startswith("Familie Test/Haus & Reparaturen/_Ohne Adresse/2026/")

        r = await client.patch(f"{API}/properties/{props[0]['id']}", headers=auth, json={"name": "Ferienwohnung Meersburg"})
        assert r.status_code == 200, r.text
        await run_worker()
        for doc_id in (d1, d2, d4):
            assert (await detail(doc_id))["files"][0]["path"].startswith(
                "Familie Test/Haus & Reparaturen/Ferienwohnung Meersburg/2026/"
            )
        assert not (tmp_path / "Familie Test/Haus & Reparaturen/Meersburg Seeweg 12a").exists()  # alter Ordner weg

        # Dokument von Hand einem Objekt zuordnen
        r = await client.patch(f"{API}/documents/{d5}", headers=auth, json={"property_id": props[0]["id"]})
        assert r.status_code == 200
        await run_worker()
        assert (await detail(d5))["files"][0]["path"].startswith("Familie Test/Haus & Reparaturen/Ferienwohnung Meersburg/2026/")
        assert not (tmp_path / "Familie Test/Haus & Reparaturen/_Ohne Adresse").exists()

        # Objekt loeschen: Dokumente bleiben, landen in "_Ohne Adresse"
        assert (await client.delete(f"{API}/properties/{props[0]['id']}", headers=auth)).status_code == 204
        await run_worker()
        assert (await detail(d4))["property_id"] is None
        assert (await detail(d4))["files"][0]["path"].startswith("Familie Test/Haus & Reparaturen/_Ohne Adresse/2026/")

        # --- 8. Erneut analysieren -------------------------------------------------------------
        r = await client.post(f"{API}/documents/{d3}/reprocess", headers=auth)
        assert r.status_code == 200, r.text
        assert (await client.post(f"{API}/documents/{d3}/reprocess", headers=auth)).status_code == 409  # laeuft schon
        await run_worker()
        assert (await detail(d3))["extraction_status"] == "done"
