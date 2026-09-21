"""Platzhalter-Task - beweist die Job-Queue-Verkabelung end-to-end (DB-Verbindung, Worker-Start).
Wird entfernt, sobald es genug echte Tasks gibt, dass ein Beweis-Task ueberfluessig ist."""
import logging

from homedms.jobs import app

logger = logging.getLogger("homedms.tasks.misc")


@app.task(name="ping")
async def ping(message: str = "pong") -> str:
    logger.info("ping-Task ausgefuehrt: %s", message)
    return message
