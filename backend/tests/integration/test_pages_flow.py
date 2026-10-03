"""Mehrseitige Dokumente gegen echte DB und echte Dateien."""
import io
from datetime import date
from pathlib import Path

import httpx
from PIL import Image

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.main import app
from homedms.tasks import extraction

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, pdf, run_worker


def png(color="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), color).save(buf, format="PNG")
    return buf.getvalue()


async def test_mehrseitig(clean_database, monkeypatch, tmp_path):
    monkeypatch.setattr(ollama, "client_for", FakeOllama().client)
    monkeypatch.setattr(extraction, "today", lambda: date(2026, 9, 30))
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        async def detail(doc_id: str) -> dict:
            return (await client.get(f"{API}/documents/{doc_id}", headers=auth)).json()

        # --- 1. Zwei Dateien = ein Dokument mit zwei Seiten, Text aller Seiten erkannt --------
        r = await client.post(f"{API}/documents", headers=auth, files=[
            ("file", ("seite1.pdf", pdf("Stadtwerke Musterstadt GmbH\nStromrechnung vom 01.09.2026"), "application/pdf")),
            ("file", ("seite2.pdf", pdf("Betrag: 42,00 EUR - zahlbar bis 15.10.2026"), "application/pdf")),
        ])
        assert r.status_code == 201, r.text
        doc_id = r.json()["id"]
        await run_worker()
        doc = await detail(doc_id)
        assert doc["page_count"] == 2
        assert "Stromrechnung" in doc["ocr_text"] and "zahlbar bis" in doc["ocr_text"]
        assert doc["amount"] == 42.0  # Betrag stand auf Seite 2
        assert doc["files"][0]["mime_type"] == "application/pdf"

        # --- 2. Seiten hinzufuegen (Foto ans Ende, Deckblatt an den Anfang) -----------------
        r = await client.post(f"{API}/documents/{doc_id}/pages", headers=auth,
                              files=[("file", ("foto.png", png(), "image/png"))])
        assert r.status_code == 200, r.text
        assert r.json()["page_count"] == 3
        # waehrend der Neuauswertung keine weitere Aenderung
        r = await client.delete(f"{API}/documents/{doc_id}/pages/3", headers=auth)
        assert r.status_code == 409
        await run_worker()

        r = await client.post(f"{API}/documents/{doc_id}/pages", headers=auth, data={"position": "1"},
                              files=[("file", ("deckblatt.pdf", pdf("Deckblatt"), "application/pdf"))])
        assert r.json()["page_count"] == 4
        await run_worker()
        doc = await detail(doc_id)
        assert doc["ocr_text"].lstrip().startswith("Deckblatt")
        assert doc["amount"] == 42.0  # vorhandene Angaben bleiben

        # --- 3. Umsortieren, Loeschen, Vorschaubilder ----------------------------------------
        r = await client.put(f"{API}/documents/{doc_id}/pages/order", headers=auth, json={"order": [2, 3, 1, 4]})
        assert r.status_code == 200
        await run_worker()
        assert (await detail(doc_id))["ocr_text"].lstrip().startswith("Stadtwerke")
        assert (await client.put(f"{API}/documents/{doc_id}/pages/order", headers=auth,
                                 json={"order": [1, 1, 2, 3]})).status_code == 422
        r = await client.delete(f"{API}/documents/{doc_id}/pages/3", headers=auth)  # Deckblatt
        assert r.json()["page_count"] == 3
        await run_worker()
        assert "Deckblatt" not in (await detail(doc_id))["ocr_text"]

        thumb = await client.get(f"{API}/documents/{doc_id}/pages/2/thumbnail", headers=auth, params={"width": 200})
        assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/png"
        with Image.open(io.BytesIO(thumb.content)) as img:
            assert img.width == 200
        assert (await client.get(f"{API}/documents/{doc_id}/pages/9/thumbnail", headers=auth)).status_code == 422

        # Datei liegt weiterhin genau einmal in der Ablage, als PDF
        pdfs = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert len(pdfs) == 1 and pdfs[0].suffix == ".pdf"

        # --- 4. Einzelfoto + weitere Seite -> wird zur PDF -------------------------------------
        r = await client.post(f"{API}/documents", headers=auth, files={"file": ("brief.png", png(), "image/png")})
        foto_id = r.json()["id"]
        await run_worker()
        assert (await detail(foto_id))["page_count"] == 1
        r = await client.post(f"{API}/documents/{foto_id}/pages", headers=auth,
                              files=[("file", ("seite2.png", png("gray"), "image/png"))])
        assert r.json()["page_count"] == 2
        await run_worker()
        doc = await detail(foto_id)
        assert doc["files"][0]["mime_type"] == "application/pdf" and doc["page_count"] == 2
        assert not any(p.suffix == ".png" for p in tmp_path.rglob("*") if p.is_file())  # altes Foto ersetzt

        # Letzte Seite nicht loeschbar; ungueltige Dateien abgelehnt
        r = await client.post(f"{API}/documents", headers=auth, files={"file": ("e.pdf", pdf("Einzeln"), "application/pdf")})
        single = r.json()["id"]
        await run_worker()
        assert (await client.delete(f"{API}/documents/{single}/pages/1", headers=auth)).status_code == 422
        r = await client.post(f"{API}/documents", headers=auth, files=[
            ("file", ("a.pdf", pdf("A"), "application/pdf")), ("file", ("mail.eml", b"From: x", "message/rfc822")),
        ])
        assert r.status_code == 422


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _find(root: Path, doc: dict) -> Path:
    """Gespeicherte Datei eines Dokuments (Ablagepfad ist relativ zum Dokumente-Ordner)."""
    path = root / doc["files"][0]["path"]
    assert path.is_file(), path
    return path


def _page_ratio(path: Path, page: int = 0) -> float:
    import pymupdf

    with pymupdf.open(path) as doc:
        rect = doc[page].rect
        return rect.height / rect.width


async def test_foto_zuschnitt(clean_database, monkeypatch, tmp_path):
    """Handy-Foto vom Tisch: Vorschau, Hochladen (mit/ohne Zuschnitt), nachtraeglich gerade richten."""
    from ..test_docscan import SCHRAEG_VON_OBEN, blatt, foto

    monkeypatch.setattr(ollama, "client_for", FakeOllama().client)
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))
    photo = _jpeg(foto(blatt(), SCHRAEG_VON_OBEN)[0])  # 3000 x 4000, Blatt schraeg auf dunklem Tisch

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        # --- Vorschau: aufbereitetes JPEG, nichts gespeichert ---------------------------------
        r = await client.post(f"{API}/photos/rectify", headers=auth, files={"file": ("foto.jpg", photo, "image/jpeg")})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/jpeg" and r.headers["x-cropped"] == "true"
        with Image.open(io.BytesIO(r.content)) as img:
            assert abs(img.height / img.width - 2 ** 0.5) < 0.01
        preview = r.content
        assert not any(p.is_file() for p in tmp_path.rglob("*"))
        r = await client.post(f"{API}/photos/rectify", headers=auth, files={"file": ("a.pdf", pdf("x"), "application/pdf")})
        assert r.status_code == 422
        assert (await client.post(f"{API}/photos/rectify", files={"file": ("f.jpg", photo, "image/jpeg")})).status_code == 401

        # --- Hochladen: ohne Angabe wird zugeschnitten; Vorschau-Ergebnis nicht doppelt -------
        r = await client.post(f"{API}/documents", headers=auth, files={"file": ("foto.jpg", photo, "image/jpeg")})
        assert r.status_code == 201, r.text
        auto_id = r.json()["id"]
        r = await client.post(f"{API}/documents", headers=auth, data={"auto_crop": ["false", "true"]}, files=[
            ("file", ("vorschau.jpg", preview, "image/jpeg")), ("file", ("foto2.jpg", photo, "image/jpeg")),
        ])
        assert r.status_code == 201, r.text
        mixed_id = r.json()["id"]
        r = await client.post(f"{API}/documents", headers=auth, data={"auto_crop": "false"},
                              files={"file": ("original.jpg", photo, "image/jpeg")})
        original_id = r.json()["id"]
        await run_worker()

        details = {i: (await client.get(f"{API}/documents/{i}", headers=auth)).json() for i in (auto_id, mixed_id, original_id)}
        paths = {i: _find(tmp_path, d) for i, d in details.items()}
        assert abs(_page_ratio(paths[auto_id]) - 2 ** 0.5) < 0.01
        assert abs(_page_ratio(paths[mixed_id], 0) - 2 ** 0.5) < 0.01
        assert abs(_page_ratio(paths[mixed_id], 1) - 2 ** 0.5) < 0.01
        assert abs(_page_ratio(paths[original_id]) - 4 / 3) < 0.01  # Original gewuenscht
        assert "Kreditvertrag" in details[auto_id]["ocr_text"]

        # --- Nachtraeglich: Original-Seite gerade richten; zweites Mal gibt's nichts zu tun -----
        r = await client.post(f"{API}/documents/{original_id}/pages/1/rectify", headers=auth)
        assert r.status_code == 200, r.text
        await run_worker()
        doc = (await client.get(f"{API}/documents/{original_id}", headers=auth)).json()
        assert abs(_page_ratio(_find(tmp_path, doc)) - 2 ** 0.5) < 0.01
        r = await client.post(f"{API}/documents/{original_id}/pages/1/rectify", headers=auth)
        assert r.status_code == 422
        r = await client.post(f"{API}/documents/{original_id}/pages/5/rectify", headers=auth)
        assert r.status_code == 422
