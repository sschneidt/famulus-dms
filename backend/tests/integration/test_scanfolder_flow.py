"""Scan-Ordner-Import gegen echte DB und echte Dateien (homedms/tasks/scanfolder.py)."""
import os
import time
from datetime import date
from pathlib import Path

import httpx

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.core.security import hash_password
from homedms.db import async_session_factory
from homedms.jobs import app as jobs_app
from homedms.main import app
from homedms.models.tenant import User, UserRole
from homedms.tasks import extraction
from homedms.tasks import scanfolder

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker

RECHNUNG = """Stadtwerke Musterstadt GmbH
Stromrechnung vom 01.09.2026
Betrag: 42,00 EUR - zahlbar bis 15.10.2026"""


def put(root: Path, rel: str, content: bytes, age: float = 120) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    old = time.time() - age
    os.utime(path, (old, old))
    return path


def files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


async def scan() -> None:
    async with jobs_app.open_async():
        await scanfolder.scan_folders.func(timestamp=0)


async def test_scan_ordner(clean_database, monkeypatch, tmp_path):
    scan_root, docs_root = tmp_path / "scan", tmp_path / "docs"
    scan_root.mkdir()
    monkeypatch.setattr(get_settings(), "scan_path", str(scan_root))
    monkeypatch.setattr(get_settings(), "documents_path", str(docs_root))
    monkeypatch.setattr(ollama, "client_for", FakeOllama().client)
    monkeypatch.setattr(extraction, "today", lambda: date(2026, 9, 30))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)
        month = time.strftime("%Y-%m")
        rechnung = pdf(RECHNUNG)

        put(scan_root, "Scan_0815.pdf", rechnung)
        put(scan_root, "Unterordner/Scan_0815_kopie.pdf", rechnung)  # gleicher Inhalt -> Duplikat
        put(scan_root, "Brief.docx", b"PK...")  # nicht unterstuetzt
        put(scan_root, "halb.pdf", b"%PDF-1.7\n... abgebrochen", age=60)  # wird evtl. noch geschrieben
        put(scan_root, "kaputt.pdf", b"%PDF-1.7\n... abgebrochen", age=3600)  # endgueltig unvollstaendig
        put(scan_root, "frisch.pdf", rechnung + b" ", age=1)  # gerade erst angekommen
        put(scan_root, "@eaDir/Scan_0815.pdf/SYNOFILE_THUMB_M.jpg", b"x")  # Synology-Vorschau
        put(scan_root, ".DS_Store", b"x")

        await scan()  # richtet bei einem Haushalt den Scan-Ordner selbst ein

        sources = (await client.get(f"{API}/import-sources", headers=auth)).json()
        assert len(sources) == 1 and sources[0]["path"] == "" and sources[0]["is_active"]
        recent = {e["file"]: e for e in sources[0]["recent"]}
        assert recent["Scan_0815.pdf"]["status"] == "importiert"
        assert recent["Unterordner/Scan_0815_kopie.pdf"]["status"] == "duplikat"
        assert recent["Brief.docx"]["status"] == "fehler" and "nicht unterstuetzt" in recent["Brief.docx"]["message"]
        assert recent["kaputt.pdf"]["status"] == "fehler"
        assert "halb.pdf" not in recent and "frisch.pdf" not in recent
        assert sources[0]["waiting"] == 2

        assert files(scan_root) == sorted([
            ".DS_Store", "@eaDir/Scan_0815.pdf/SYNOFILE_THUMB_M.jpg", "frisch.pdf", "halb.pdf",
            f"_failed/{month}/Brief.docx", f"_failed/{month}/kaputt.pdf",
            f"_imported/{month}/Scan_0815.pdf", f"_imported/{month}/Scan_0815_kopie.pdf",
        ])

        # Das Dokument gehoert dem Haushalt und laeuft durch die gewohnte Kette
        await run_worker()
        doc_id = recent["Scan_0815.pdf"]["document_id"]
        assert recent["Unterordner/Scan_0815_kopie.pdf"]["document_id"] == doc_id
        doc = (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()
        assert doc["owner_user_id"] is None and doc["source"] == "nas_scan_folder"
        assert doc["ocr_status"] == "done" and doc["extraction_status"] == "done"
        assert doc["title"] == "Stromrechnung – Stadtwerke Musterstadt GmbH"  # automatisch benannt

        # Ein normales Haushaltsmitglied sieht und bearbeitet es (keine Person ist Eigentuemer)
        async with async_session_factory() as db:
            db.add(User(tenant_id=(await client.get(f"{API}/auth/me", headers=auth)).json()["tenant_id"],
                        email="anna@example.com", password_hash=hash_password("geheim-123"),
                        display_name="Anna", role=UserRole.member, notification_channels={}))
            await db.commit()
        token = (await client.post(f"{API}/auth/login", json={
            "email": "anna@example.com", "password": "geheim-123"})).json()["access_token"]
        anna = {"Authorization": f"Bearer {token}"}
        assert (await client.get(f"{API}/documents/{doc_id}", headers=anna)).status_code == 200
        assert (await client.patch(f"{API}/documents/{doc_id}", headers=anna, json={"issuer": "SWM"})).status_code == 200
        assert (await client.get(f"{API}/import-sources", headers=anna)).status_code == 403  # nur Admin

        # Zweiter Durchlauf: die fertig geschriebene Datei wird jetzt abgeholt
        os.utime(scan_root / "frisch.pdf", (time.time() - 120, time.time() - 120))
        await scan()
        sources = (await client.get(f"{API}/import-sources", headers=auth)).json()
        assert sources[0]["recent"][0]["file"] == "frisch.pdf" and sources[0]["recent"][0]["status"] == "importiert"
        assert sources[0]["waiting"] == 1  # halb.pdf

        # Verwaltung: Jetzt pruefen, deaktivieren, ungueltige/ueberschneidende Ordner
        sid = sources[0]["id"]
        r = await client.post(f"{API}/import-sources/{sid}/scan-now", headers=auth)
        assert r.status_code == 202
        assert (await client.patch(f"{API}/import-sources/{sid}", headers=auth, json={"path": "../etc"})).status_code == 422
        assert (await client.post(f"{API}/import-sources", headers=auth, json={"path": "Familie"})).status_code == 409
        r = await client.patch(f"{API}/import-sources/{sid}", headers=auth, json={"is_active": False})
        assert r.json()["is_active"] is False
        put(scan_root, "neu.pdf", pdf("Neuer Brief"))
        await scan()
        assert (scan_root / "neu.pdf").exists()  # deaktiviert -> bleibt liegen

        # Ordner fehlt -> verstaendliche Meldung
        await client.patch(f"{API}/import-sources/{sid}", headers=auth, json={"is_active": True, "path": "gibtsnicht"})
        await scan()
        source = (await client.get(f"{API}/import-sources", headers=auth)).json()[0]
        assert "nicht gefunden" in source["error"]
