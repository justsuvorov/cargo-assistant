import asyncio
import logging
import signal
from contextlib import suppress

from app.core.clock import Utc
from app.core.journal import LogJournal
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.database import Database
from app.jobs.queue import Queue
from app.jobs.stages import Standard
from app.jobs.worker import Shift


async def run() -> None:
    settings = EnvSettings(Environment())
    database = Database(settings.database())
    stop = asyncio.Event()
    with suppress(NotImplementedError):
        for name in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_running_loop().add_signal_handler(name, stop.set)
    journal = LogJournal(logging.getLogger("worker"))
    journal.info("Воркер запущен", 0, 0)
    await Shift(Queue(database, Utc()), Standard(journal), settings, journal).serve(stop)
    await database.close()
    journal.info("Воркер остановлен", 0, 0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())
