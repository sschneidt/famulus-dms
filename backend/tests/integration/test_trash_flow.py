"""Papierkorb leeren (homedms/core/trash.py) gegen echte DB, mit echten Dateien."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import text

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.core import trash
from homedms.db import async_session_factory
from homedms.main import app

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


async def test_papierkorb_wird_nach_30_tagen_geleert(clean_database, monkeypatch, tmp_path):
    monkeypatch.setattr(ollama, "client_for", FakeOllama().client)
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        async def upload(text_: str) -> str:
            r = await client.post(f"{API}/documents", headers=auth,
                                  files={"file": ("scan.pdf", pdf(text_), "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        alt = await upload("Rechnung Alt vom 01.01.2026")
        neu = await upload("Rechnung Neu vom 02.02.2026")
        behalten = await upload("Rechnung Behalten vom 03.03.2026")
        await run_worker()
        assert len(files_under(tmp_path)) == 3

        for doc_id in (alt, neu):
            assert (await client.delete(f"{API}/documents/{doc_id}", headers=auth)).status_code == 204
        await run_worker()  # Ablage zieht beide in _Papierkorb

        # "alt" liegt seit 31 Tagen im Papierkorb, "neu" erst seit 29
        now = datetime.now(timezone.utc)
        async with async_session_factory() as db:
            for doc_id, days in ((alt, 31), (neu, 29)):
                await db.execute(text("UPDATE documents SET deleted_at = :t WHERE id = :id"),
                                 {"t": now - timedelta(days=days), "id": doc_id})
            await db.commit()

        async with async_session_factory() as db:
            purged = await trash.purge_expired(db)
        assert [str(i) for i in purged] == [alt]

        trash_list = (await client.get(f"{API}/documents/trash", headers=auth)).json()
        assert [d["id"] for d in trash_list["items"]] == [neu]
        assert (await client.get(f"{API}/documents/{behalten}", headers=auth)).status_code == 200

        async with async_session_factory() as db:
            assert await db.scalar(text("SELECT count(*) FROM documents WHERE id = :id"), {"id": alt}) == 0
            assert await db.scalar(text("SELECT count(*) FROM document_files WHERE document_id = :id"), {"id": alt}) == 0
        assert len(files_under(tmp_path)) == 2  # nur die Datei von "alt" ist weg

        # zweiter Lauf: nichts mehr zu tun
        async with async_session_factory() as db:
            assert await trash.purge_expired(db) == []
