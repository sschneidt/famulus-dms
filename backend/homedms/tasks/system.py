"""Auftraege fuer die Seite "Diagnose" (api/routes/system.py)."""
import logging

import httpx

from homedms.jobs import app

logger = logging.getLogger("homedms.tasks.system")


@app.task(name="restart_worker", queue="default")
async def restart_worker() -> None:
    """Laeuft IM Worker: beendet ihn, damit Docker bzw. der Starter ihn frisch startet."""
    from homedms.worker import request_restart

    logger.warning("Worker-Neustart angefordert (Seite Diagnose)")
    if not request_restart():
        logger.warning("Worker-Neustart nicht moeglich - Worker laeuft nicht ueber homedms.worker")


@app.task(name="pull_model", queue="ai")
async def pull_model(model: str) -> None:
    """KI-Modell herunterladen (einige GB, kann dauern) - im Hintergrund statt im Webserver."""
    from homedms.ai import ollama

    client = ollama.client_for(None)
    logger.info("Lade KI-Modell %s ...", model)
    async with client._client(3600) as http:  # noqa: SLF001
        resp = await http.post("/api/pull", json={"model": model, "stream": False})
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama /api/pull {model}: {resp.status_code} {resp.text[:200]}")
    logger.info("KI-Modell %s geladen", model)


@app.task(name="install_ocr_language", queue="default", pass_context=False)
async def install_ocr_language(code: str) -> None:
    """Sprachpaket der Texterkennung herunterladen (core/ocr_languages.py). Fehler stehen danach auf
    der Seite "Sprachen" bzw. in der Diagnose - kein endloses Wiederholen."""
    from homedms.core import ocr_languages
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        try:
            path = await ocr_languages.download(code)
        except ocr_languages.OcrLanguageError as exc:
            logger.warning("Sprachpaket %s nicht installiert: %s", code, exc)
            await ocr_languages.set_state(db, code, {"status": "failed", "error": str(exc)})
            return
        logger.info("Sprachpaket %s installiert (%s)", code, path)
        await ocr_languages.set_state(db, code, None)


async def unload_models() -> int:
    """Geladene Modelle aus dem Arbeitsspeicher werfen (keep_alive 0) - laeuft direkt in der API."""
    from homedms.ai import ollama

    client = ollama.client_for(None)
    async with client._client(30) as http:  # noqa: SLF001
        loaded = (await http.get("/api/ps")).json().get("models", [])
        for model in loaded:
            try:
                await http.post("/api/generate", json={"model": model.get("name"), "keep_alive": 0})
            except httpx.HTTPError as exc:
                logger.warning("Modell %s nicht entladen: %s", model.get("name"), exc)
    return len(loaded)
