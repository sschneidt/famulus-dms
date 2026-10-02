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
import signal

from homedms.jobs import app

# Zwei getrennte Warteschlangen, je ein eigener Arbeitsstrang:
# - "default": Texterkennung, Ablage, Suchindex - schnell, sollen nie warten muessen
# - "ai":      Klassifikation, Metadaten/Fristen, Lernbeispiele - Sprachmodell-Aufrufe dauern auf
#              einem NAS ohne GPU Minuten und laufen bewusst einzeln (das Modell rechnet ohnehin
#              nur einen Auftrag zugleich schnell).
# Vorher lief alles in einer Schlange: Ein langsamer Modell-Aufruf hielt die Texterkennung neuer
# Uploads auf (Smoke-Test: "Texterkennung Scan - Status pending").
QUEUES = {"dateien": ["default", "builtin"], "ki": ["ai"]}  # builtin: Procrastinate-eigene Wartungsauftraege


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with app.open_async():
        workers = [
            asyncio.create_task(
                app.run_worker_async(name=name, queues=queues, concurrency=1, install_signal_handlers=False)
            )
            for name, queues in QUEUES.items()
        ]
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: [w.cancel() for w in workers])  # sauber beenden
        await asyncio.gather(*workers, return_exceptions=True)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
