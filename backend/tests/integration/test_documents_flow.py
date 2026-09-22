"""Durchgehender Ablauf gegen echte DB: Ersteinrichtung -> Login -> Upload -> OCR-Job in der
Queue -> Worker arbeitet ihn ab -> Sichtbarkeitsregeln -> Papierkorb -> Download.
Siehe tests/integration/conftest.py fuer das Einschalten dieser Tests."""
import uuid

import httpx
import pymupdf
from sqlalchemy import select, text

from homedms.core.security import hash_password
from homedms.db import async_session_factory
from homedms.jobs import app as jobs_app
from homedms.main import app
from homedms.models.document import Category, Document, DocumentAccessOverride, OcrStatus
from homedms.models.tenant import Tenant, User, UserRole

API = "/api/v1"


def _digital_pdf(text_content: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text_content)
    data = doc.tobytes()
    doc.close()
    return data


async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict:
    resp = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _add_user(tenant_id: uuid.UUID, email: str, role: UserRole = UserRole.member) -> None:
    async with async_session_factory() as db:
        db.add(User(tenant_id=tenant_id, email=email, password_hash=hash_password("geheim-123"),
                    display_name=email, role=role, notification_channels={}))
        await db.commit()


async def test_document_lifecycle(clean_database):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # --- Ersteinrichtung -----------------------------------------------------------
        assert (await client.get(f"{API}/setup/status")).json() == {"bootstrapped": False}
        resp = await client.post(f"{API}/setup/bootstrap", json={
            "household_name": "Familie Test", "admin_email": "admin@example.com",
            "admin_password": "admin-passwort", "admin_display_name": "Admin",
        })
        assert resp.status_code == 201, resp.text
        tenant_id = uuid.UUID(resp.json()["tenant_id"])
        assert resp.json()["categories_created"] == 13
        # zweiter Bootstrap ist gesperrt
        assert (await client.post(f"{API}/setup/bootstrap", json={
            "household_name": "X", "admin_email": "x@example.com",
            "admin_password": "xxxxxxxx", "admin_display_name": "X",
        })).status_code == 409

        admin = await _login(client, "admin@example.com", "admin-passwort")
        assert (await client.get(f"{API}/auth/me", headers=admin)).json()["role"] == "admin"
        assert len((await client.get(f"{API}/categories", headers=admin)).json()) == 13

        # --- Upload -> OCR-Job wird eingereiht -----------------------------------------
        pdf = _digital_pdf("Stadtwerke Rechnung Nr 4711 Betrag 42 EUR")
        resp = await client.post(
            f"{API}/documents", headers=admin,
            files={"file": ("rechnung.pdf", pdf, "application/pdf")}, data={"title": "Stromrechnung"},
        )
        assert resp.status_code == 201, resp.text
        doc = resp.json()
        doc_id = doc["id"]
        assert doc["title"] == "Stromrechnung"
        assert doc["ocr_status"] == "pending"
        assert doc["files"][0]["filename"] == "page-001.pdf"

        async with async_session_factory() as db:
            jobs = (await db.execute(text(
                "SELECT task_name, status::text, args FROM procrastinate_jobs"
            ))).all()
        assert len(jobs) == 1
        assert jobs[0].task_name == "ocr_document" and jobs[0].status == "todo"
        assert jobs[0].args == {"document_id": doc_id}

        # --- Worker arbeitet die Queue ab ----------------------------------------------
        async with jobs_app.open_async():
            await jobs_app.run_worker_async(wait=False, install_signal_handlers=False)

        async with async_session_factory() as db:
            stored = await db.get(Document, uuid.UUID(doc_id))
            assert stored.ocr_status == OcrStatus.done
            assert "Rechnung Nr 4711" in stored.ocr_text
            status = await db.scalar(text("SELECT status::text FROM procrastinate_jobs"))
        assert status == "succeeded"

        # --- Download liefert die Originaldatei ----------------------------------------
        resp = await client.get(f"{API}/documents/{doc_id}/download", headers=admin)
        assert resp.status_code == 200 and resp.content == pdf

        # --- Sichtbarkeit: Mitglied sieht Dokumente in offenen Kategorien ---------------
        await _add_user(tenant_id, "kind@example.com")
        member = await _login(client, "kind@example.com", "geheim-123")
        listing = (await client.get(f"{API}/documents", headers=member)).json()
        assert listing["total"] == 1

        # ... aber nicht in einer eingeschraenkten Kategorie ohne Freigabe
        async with async_session_factory() as db:
            restricted = Category(tenant_id=tenant_id, name="Privat", is_restricted=True)
            db.add(restricted)
            await db.flush()
            stored = await db.get(Document, uuid.UUID(doc_id))
            stored.category_id = restricted.id
            await db.commit()
        assert (await client.get(f"{API}/documents", headers=member)).json()["total"] == 0
        assert (await client.get(f"{API}/documents/{doc_id}", headers=member)).status_code == 403
        assert (await client.get(f"{API}/documents/{doc_id}/download", headers=member)).status_code == 403
        assert (await client.get(f"{API}/documents", headers=admin)).json()["total"] == 1

        # ... bis eine Einzelfreigabe (DocumentAccessOverride) das Lesen erlaubt - nicht Schreiben
        async with async_session_factory() as db:
            member_id = await db.scalar(select(User.id).where(User.email == "kind@example.com"))
            db.add(DocumentAccessOverride(tenant_id=tenant_id, document_id=uuid.UUID(doc_id),
                                          user_id=member_id, can_view=True, can_edit=False))
            await db.commit()
        assert (await client.get(f"{API}/documents/{doc_id}", headers=member)).status_code == 200
        assert (await client.patch(f"{API}/documents/{doc_id}", headers=member,
                                   json={"title": "gehackt"})).status_code == 403

        # --- Mandantentrennung: fremder Haushalt sieht das Dokument gar nicht (404) ------
        async with async_session_factory() as db:
            other = Tenant(name="Nachbarn")
            db.add(other)
            await db.flush()
            other_id = other.id
            await db.commit()
        await _add_user(other_id, "nachbar@example.com", role=UserRole.admin)
        neighbour = await _login(client, "nachbar@example.com", "geheim-123")
        assert (await client.get(f"{API}/documents/{doc_id}", headers=neighbour)).status_code == 404
        assert (await client.get(f"{API}/documents", headers=neighbour)).json()["total"] == 0

        # --- Bearbeiten, Papierkorb, Wiederherstellen ----------------------------------
        resp = await client.patch(f"{API}/documents/{doc_id}", headers=admin,
                                  json={"original_present": "ja", "original_location": "Ordner Strom"})
        assert resp.status_code == 200 and resp.json()["original_present"] == "ja"

        assert (await client.delete(f"{API}/documents/{doc_id}", headers=admin)).status_code == 204
        assert (await client.get(f"{API}/documents/{doc_id}", headers=admin)).status_code == 404
        assert (await client.get(f"{API}/documents", headers=admin)).json()["total"] == 0
        assert (await client.get(f"{API}/documents/trash", headers=admin)).json()["total"] == 1
        assert (await client.patch(f"{API}/documents/{doc_id}", headers=admin,
                                   json={"title": "x"})).status_code == 409

        resp = await client.post(f"{API}/documents/{doc_id}/restore", headers=admin)
        assert resp.status_code == 200 and resp.json()["deleted_at"] is None
        assert (await client.get(f"{API}/documents", headers=admin)).json()["total"] == 1
        assert (await client.post(f"{API}/documents/{doc_id}/restore", headers=admin)).status_code == 409

        # --- Ohne Token kein Zugriff ---------------------------------------------------
        assert (await client.get(f"{API}/documents")).status_code == 401
