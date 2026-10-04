"""Hintergrund-Job: Erinnerungen (Ablauf und Regeln: homedms/core/notifications.py).

Alle 15 Minuten: faellige Tageszusammenfassungen erstellen, wartende E-Mails/Push-Nachrichten
verschicken (auch Wiederholungsversuche), einmal pro Nacht alte Eintraege aufraeumen.
"""
import logging
import time

from homedms.jobs import app

logger = logging.getLogger("homedms.tasks.notifications")

LOCK = "notifications"


@app.periodic(cron="*/15 * * * *")
@app.task(name="send_reminders", queue="default", queueing_lock=LOCK, pass_context=False)
async def send_reminders(timestamp: int) -> None:
    from homedms.core import notifications
    from homedms.db import async_session_factory

    async with async_session_factory() as db:
        created = await notifications.run_digests(db)
        sent = await notifications.deliver_pending(db)
        if created or sent:
            logger.info("Erinnerungen: %d Zusammenfassungen erstellt, %d Nachrichten verschickt", created, sent)
        local = notifications.local_now()
        if local.hour == 3 and local.minute < 15:
            await notifications.cleanup(db)


async def request_run() -> None:
    """Sofort einen Durchlauf einreihen (z. B. nach dem Aendern der Uhrzeit)."""
    from procrastinate.exceptions import AlreadyEnqueued

    try:
        await app.configure_task("send_reminders", queueing_lock=LOCK).defer_async(timestamp=int(time.time()))
    except AlreadyEnqueued:
        pass
