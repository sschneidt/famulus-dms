"""Seite "Diagnose": Zustand aller Bausteine und Reparatur-Aktionen gegen echte DB."""
import httpx
from sqlalchemy import text

from homedms.ai import ollama
from homedms.config import get_settings
from homedms.db import async_session_factory
from homedms.main import app

from .fake_ollama import FakeOllama
from .helpers import API, bootstrap_and_login, run_worker


async def queued(task: str) -> int:
    async with async_session_factory() as db:
        return await db.scalar(text(
            "SELECT count(*) FROM procrastinate_jobs WHERE task_name = :t AND status = 'todo'"
        ), {"t": task})


async def test_diagnose(clean_database, monkeypatch, tmp_path):
    fake = FakeOllama()
    monkeypatch.setattr(ollama, "client_for", fake.client)
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        r = await client.get(f"{API}/system/diagnostics", headers=auth)
        assert r.status_code == 200, r.text
        data = r.json()
        parts = {c["key"]: c for c in data["components"]}
        assert set(parts) == {"app", "database", "worker", "ai", "search", "ocr", "storage", "tls", "notifications"}
        assert parts["notifications"]["status"] == "disabled"
        assert parts["database"]["status"] == "ok"
        assert parts["ai"]["status"] == "ok" and parts["ai"]["summary"] == "bereit"
        assert parts["ocr"]["status"] == "ok"
        assert parts["storage"]["status"] in ("ok", "warning")
        assert {"restart-worker"} <= {a["id"] for a in parts["worker"]["actions"]} or parts["worker"]["status"] == "error"
        assert data["overall"] in ("ok", "warning", "error")

        # KI weg -> rot mit Hinweis; Modell fehlt -> gelb mit "herunterladen"
        fake.down = True
        parts = {c["key"]: c for c in (await client.get(f"{API}/system/diagnostics", headers=auth)).json()["components"]}
        assert parts["ai"]["status"] == "error" and "Nicht analysiert" in parts["ai"]["hint"]
        fake.down = False
        monkeypatch.setattr(get_settings(), "ollama_chat_model", "gibt-es-nicht:7b")
        parts = {c["key"]: c for c in (await client.get(f"{API}/system/diagnostics", headers=auth)).json()["components"]}
        assert parts["ai"]["status"] == "warning" and "gibt-es-nicht:7b" in parts["ai"]["summary"]
        assert "pull-models" in [a["id"] for a in parts["ai"]["actions"]]

        # --- Aktionen ------------------------------------------------------------------------
        r = await client.post(f"{API}/system/actions/pull-models", headers=auth)
        assert r.status_code == 200, r.text
        assert (await client.post(f"{API}/system/actions/pull-models", headers=auth)).status_code == 200  # doppelt: kein Fehler
        assert await queued("pull_model") == 2  # Sprach- + Embedding-Modell, je einmal

        r = await client.post(f"{API}/system/actions/restart-worker", headers=auth)
        assert r.status_code == 200 and await queued("restart_worker") == 1
        async with async_session_factory() as db:  # pull_model braucht echtes Ollama - hier nicht ausfuehren
            await db.execute(text("DELETE FROM procrastinate_jobs WHERE task_name = 'pull_model'"))
            await db.commit()
        await run_worker()  # restart_worker laeuft (ausserhalb von homedms.worker: nur Hinweis im Protokoll)
        assert await queued("restart_worker") == 0

        r = await client.post(f"{API}/system/actions/unload-models", headers=auth)
        assert r.status_code == 200 and r.json()["message"].startswith("0 Modell")
        assert (await client.post(f"{API}/system/actions/retry-stalled", headers=auth)).status_code == 200
        assert (await client.post(f"{API}/system/actions/reindex-search", headers=auth)).status_code in (200, 502)
        assert (await client.post(f"{API}/system/actions/format-c", headers=auth)).status_code == 404

        # nur Admins
        await client.post(f"{API}/users", headers=auth, json={
            "email": "kind@example.com", "display_name": "Kind", "password": "kinder-passwort"})
        token = (await client.post(f"{API}/auth/login", json={
            "email": "kind@example.com", "password": "kinder-passwort"})).json()["access_token"]
        member = {"Authorization": f"Bearer {token}"}
        assert (await client.get(f"{API}/system/diagnostics", headers=member)).status_code == 403
        assert (await client.post(f"{API}/system/actions/restart-worker", headers=member)).status_code == 403
