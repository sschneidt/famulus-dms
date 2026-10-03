"""Gemeinsame Helfer fuer die Integrationstests."""
import httpx
import pymupdf
from sqlalchemy import text

from homedms.db import async_session_factory
from homedms.jobs import app as jobs_app

API = "/api/v1"


def pdf(text_: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in text_.splitlines():
        page.insert_text((72, y), line, fontsize=9)
        y += 14
    data = doc.tobytes()
    doc.close()
    return data


async def run_worker() -> None:
    """Arbeitet alle Jobs ab - inklusive der Folge-Jobs (OCR -> Klassifikation/Extraktion)."""
    async with jobs_app.open_async():
        for _ in range(5):
            await jobs_app.run_worker_async(wait=False, install_signal_handlers=False)
            async with async_session_factory() as db:
                offen = await db.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE status IN ('todo','doing')"))
            if offen == 0:
                return
    raise AssertionError("Jobs wurden nicht abgearbeitet")


async def bootstrap_and_login(client: httpx.AsyncClient) -> dict:
    from homedms.core import setup_code

    r = await client.post(f"{API}/setup/bootstrap", json={
        "household_name": "Familie Test", "admin_email": "admin@example.com",
        "admin_password": "admin-passwort", "admin_display_name": "Admin",
        "setup_code": setup_code.get_or_create(),
    })
    assert r.status_code == 201, r.text
    token = (await client.post(f"{API}/auth/login", json={
        "email": "admin@example.com", "password": "admin-passwort"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
