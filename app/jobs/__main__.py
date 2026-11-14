import asyncio
import logging
import signal
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

from app.core.clock import Utc
from app.core.journal import LogJournal
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.building import Workbench
from app.jobs.checking import Unconfigured
from app.jobs.database import Database
from app.jobs.folios import Folios
from app.jobs.gateway import Gateway, Tracked
from app.jobs.logbook import Careful, Journaled, Local
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.jobs.retention import Both, Cached, Monthly
from app.jobs.stages import Benches, Building, Kit, Routed, Standard
from app.jobs.versions import Fingerprint, Stamp
from app.jobs.worker import Shift
from app.llm.assembly import Configured
from app.storage.disk import DiskStorage
from app.storage.layout import Keys


async def run() -> None:
    environment = Environment()
    settings = EnvSettings(environment)
    database = Database(settings.database())
    stop = asyncio.Event()
    with suppress(NotImplementedError):
        for name in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_running_loop().add_signal_handler(name, stop.set)
    journal = LogJournal(logging.getLogger("worker"))
    journal.info("Воркер запущен", 0, 0)
    queue = Queue(database, Utc())
    folio = Folios(database, queue, Utc())
    gateway = Gateway(
        Configured(
            environment,
            journal,
            Tracked(database, asyncio.get_running_loop(), environment.llm_total_timeout),
        )
    )
    bench = Workbench(DiskStorage(settings.storage()), settings.soffice())
    version = settings.version() or "dev"
    stamp = Stamp(
        version, Fingerprint(settings.cards()).hex(), settings.prompts(), settings.model()
    )
    pipelines = Routed(
        Standard(
            journal,
            folio,
            database,
            bench,
            Kit(
                settings.cards(),
                DiskStorage(settings.storage()),
                stamp,
                Unconfigured(Benches(gateway, journal, 1, environment.semantic_pack_size)),
                ThreadPoolExecutor(settings.threads(), thread_name_prefix="semantic"),
            ),
        ),
        Building(
            bench,
            folio,
            Shelving(database, queue, DiskStorage(settings.storage()), Keys()),
            gateway,
            journal,
        ),
    )
    logbook = Careful(
        Journaled(
            database,
            Utc(),
            Local(version),
            stamp,
            Both(
                Monthly(database, Utc(), settings.months()),
                Cached(settings.soffice(), Utc(), settings.cache_days()),
            ),
        ),
        journal,
    )
    await Shift(queue, pipelines, settings, journal, logbook).serve(stop)
    await database.close()
    journal.info("Воркер остановлен", 0, 0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())
