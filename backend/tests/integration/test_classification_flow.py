"""Klassifikation gegen echte DB, mit einer Ollama-Attrappe statt echtem Sprachmodell.

Die Attrappe verhaelt sich vorhersehbar: Embeddings sind "Wortbeutel"-Vektoren (aehnliche Texte ->
aehnliche Vektoren), das "Sprachmodell" entscheidet nach Stichworten. So laesst sich die gesamte
Logik rund um das Modell pruefen: Stufe 1/Stufe 2, Feedback-Loop, Lernen aus Bestaetigungen,
Korrekturen, Ausfall der KI. Wie gut das echte Modell entscheidet, prueft der Smoke-Test.
"""
import uuid

import httpx
import pymupdf
from sqlalchemy import select, text

from homedms.ai import ollama
from homedms.db import async_session_factory
from homedms.jobs import app as jobs_app
from homedms.main import app
from homedms.models.classification import CategoryExemplar
from homedms.models.document import Category

from .fake_ollama import FakeOllama

API = "/api/v1"


def versicherung(i: int) -> str:
    return (f"Versicherung Muster AG Beitragsrechnung Haftpflichtversicherung Versicherungsschein "
            f"Jahresbeitrag faellig Kundennummer {i}")


def pdf(text_: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text_, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


async def run_worker() -> None:
    """Arbeitet alle Jobs ab - inklusive der Folge-Jobs (OCR -> Klassifikation)."""
    async with jobs_app.open_async():
        for _ in range(5):
            await jobs_app.run_worker_async(wait=False, install_signal_handlers=False)
            async with async_session_factory() as db:
                offen = await db.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE status IN ('todo','doing')"))
            if offen == 0:
                return
    raise AssertionError("Jobs wurden nicht abgearbeitet")


async def exemplars(document_id: str | None = None) -> list[tuple[str, str]]:
    async with async_session_factory() as db:
        stmt = select(Category.name, CategoryExemplar.created_via).join(Category)
        if document_id:
            stmt = stmt.where(CategoryExemplar.document_id == uuid.UUID(document_id))
        return [(n, v.value) for n, v in (await db.execute(stmt)).all()]


async def test_classification_learns_from_confirmations(clean_database, monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(ollama, "client_for", fake.client)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post(f"{API}/setup/bootstrap", json={
            "household_name": "Familie Test", "admin_email": "admin@example.com",
            "admin_password": "admin-passwort", "admin_display_name": "Admin",
        })
        token = (await client.post(f"{API}/auth/login", json={
            "email": "admin@example.com", "password": "admin-passwort"})).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        cats = {c["name"]: c["id"] for c in (await client.get(f"{API}/categories", headers=auth)).json()}
        assert "Strom" in next(c for c in (await client.get(f"{API}/categories", headers=auth)).json()
                               if c["name"] == "Wohnen & Nebenkosten")["description"]

        async def upload(text_: str) -> str:
            r = await client.post(f"{API}/documents", headers=auth,
                                  files={"file": ("dok.pdf", pdf(text_), "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def detail(doc_id: str) -> dict:
            return (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()

        async def history(doc_id: str) -> list[dict]:
            return (await client.get(f"{API}/documents/{doc_id}/classification-history", headers=auth)).json()

        # --- 1. Ohne Beispiele entscheidet das Sprachmodell (Stufe 2) -----------------------
        d1 = await upload(versicherung(1))
        await run_worker()
        doc = await detail(d1)
        assert doc["classification_status"] == "auto_assigned"
        assert doc["classification_stage"] == "llm"
        assert doc["category_id"] == cats["Versicherungen"]
        assert doc["classification_confidence"] == 0.95
        assert await exemplars(d1) == [("Versicherungen", "llm_confirmed")]
        events = await history(d1)
        assert [e["stage"] for e in events] == ["llm"] and "Noch keine Beispiel-Dokumente" in events[0]["note"]

        # --- 2. Unsicher -> Feedback-Loop, Vorschlag steht in der Historie -------------------
        d2 = await upload("Einladung zum Sommerfest im Verein am Samstag mit Grillbuffet")
        await run_worker()
        doc = await detail(d2)
        assert doc["classification_status"] == "needs_review" and doc["category_id"] is None
        queue = (await client.get(f"{API}/documents/needs-review", headers=auth)).json()
        assert [i["id"] for i in queue["items"]] == [d2]
        assert "Vorschlag 'Sonstiges' mit 40% Sicherheit" in (await history(d2))[0]["note"]

        # --- 3. Manuell zuordnen -> bestaetigt + neues Lernbeispiel -------------------------
        r = await client.post(f"{API}/documents/{d2}/category", headers=auth, json={"category_id": cats["Sonstiges"]})
        assert r.status_code == 200 and r.json()["classification_status"] == "confirmed"
        await run_worker()
        assert await exemplars(d2) == [("Sonstiges", "manual_feedback")]
        assert [e["stage"] for e in await history(d2)] == ["llm", "manual"]
        assert (await client.get(f"{API}/documents/needs-review", headers=auth)).json()["total"] == 0

        # --- 4. Ab 5 Beispielen entscheidet Stufe 1 ohne Sprachmodell -----------------------
        for i in range(2, 6):
            await upload(versicherung(i))
        await run_worker()
        classify_calls_before = fake.classify_calls
        d6 = await upload(versicherung(6))
        await run_worker()
        doc = await detail(d6)
        assert doc["classification_stage"] == "embedding", await history(d6)
        assert doc["category_id"] == cats["Versicherungen"] and doc["classification_confidence"] >= 0.85
        assert fake.classify_calls == classify_calls_before  # Sprachmodell fuer die Kategorie nicht bemueht
        assert await exemplars(d6) == [("Versicherungen", "auto_high_confidence")]

        # --- 5. Korrektur ersetzt das Lernbeispiel, statt falsch weiterzulernen --------------
        await client.post(f"{API}/documents/{d6}/category", headers=auth, json={"category_id": cats["Sonstiges"]})
        await run_worker()
        assert await exemplars(d6) == [("Sonstiges", "manual_feedback")]
        # erneutes automatisches Klassifizieren ueberschreibt eine Bestaetigung nicht
        async with jobs_app.open_async():
            await jobs_app.configure_task("classify_document").defer_async(document_id=d6)
        await run_worker()
        assert (await detail(d6))["category_id"] == cats["Sonstiges"]

        # --- 6. Fremde Kategorie / ungueltige Anfrage -------------------------------------
        assert (await client.post(f"{API}/documents/{d6}/category", headers=auth,
                                  json={"category_id": str(uuid.uuid4())})).status_code == 404

        # --- 7. KI nicht erreichbar -> Feedback-Loop mit verstaendlichem Hinweis ------------
        fake.down = True
        d7 = await upload(versicherung(7))
        await run_worker()
        doc = await detail(d7)
        assert doc["ocr_status"] == "done" and doc["classification_status"] == "needs_review"
        assert "KI nicht verfuegbar" in (await history(d7))[0]["note"]

        # --- 8. Endgueltiges Loeschen entfernt auch das Lernbeispiel -----------------------
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": uuid.UUID(d1)})
            await db.commit()
        assert await exemplars(d1) == []
