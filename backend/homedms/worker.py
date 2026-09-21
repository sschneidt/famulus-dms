"""Worker-Entrypoint (APP_ROLE=worker, siehe docker-compose.yml).

Job-Queue laeuft direkt ueber PostgreSQL via Procrastinate statt Celery+Redis
(docs/Docker-Compose-Entwurf.md Abschnitt 2). Die eigentliche Procrastinate-App inkl. aller
Tasks lebt zentral in homedms/jobs.py (dort auch importiert von homedms/api/routes/documents.py,
das Jobs erzeugt) - dieses Modul startet nur die Worker-Schleife, die sie ausfuehrt.

Start (lokal): `uv run python -m homedms.worker`
Start (Container, APP_ROLE=worker): dasselbe Kommando, siehe Dockerfile (CMD-Weiche je nach APP_ROLE).
"""
import asyncio
import logging

from homedms.jobs import app


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with app.open_async():
        await app.run_worker_async()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
