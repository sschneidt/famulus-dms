"""Worker-Entrypoint (APP_ROLE=worker, siehe docker-compose.yml).

Job-Queue laeuft direkt ueber PostgreSQL via Procrastinate statt Celery+Redis
(docs/Docker-Compose-Entwurf.md Abschnitt 2 - loest den offenen Punkt "Job-Queue-Technologie"
aus dem Anforderungsdokument).

Dies ist bewusst nur das Grundgeruest: die eigentlichen Hintergrund-Aufgaben (OCR,
Klassifikation Stufe 1+2, Metadaten-/Fristen-Extraktion, Wiedervorlage-Wiederholungen,
Benachrichtigungs-Versand - siehe docker-compose.yml Kommentar zu app-worker) werden
Schritt fuer Schritt als eigene @app.task-Funktionen in homedms/tasks/ ergaenzt, sobald
die jeweiligen Features drankommen. Ein einzelner Platzhalter-Task (`ping`) haengt hier
bereits, um die Verkabelung (DB-Verbindung, Worker-Start) end-to-end zu verifizieren.

Start (lokal): `uv run python -m homedms.worker`
Start (Container, APP_ROLE=worker): dasselbe Kommando, siehe Dockerfile (CMD-Weiche je nach APP_ROLE).
"""
import asyncio
import logging

from procrastinate import App, PsycopgConnector

from homedms.config import get_settings

settings = get_settings()
logger = logging.getLogger("homedms.worker")

app = App(connector=PsycopgConnector(conninfo=settings.procrastinate_database_url))


@app.task(name="ping")
async def ping(message: str = "pong") -> str:
    """Platzhalter-Task - beweist, dass ein Job durch die Queue laeuft.
    Wird entfernt, sobald die ersten echten Tasks (OCR etc.) existieren."""
    logger.info("ping-Task ausgefuehrt: %s", message)
    return message


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with app.open_async():
        await app.run_worker_async()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
