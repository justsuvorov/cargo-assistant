import asyncio
import time
from typing import Final, Protocol, final

from app.core.journal import Journal
from app.core.settings import Settings
from app.jobs.errors import LostError, WaitingError
from app.jobs.logbook import Failed, Logbook, Succeeded, TimedOut, Waited
from app.jobs.queue import Jobs, Snapshot
from app.jobs.stages import Pipelines


class Serving(Protocol):
    """Process that takes jobs from the queue and runs their stages."""

    async def serve(self, stop: asyncio.Event) -> None: ...

    async def drain(self) -> int: ...


@final
class Shift:
    """Shift of a worker process that runs several jobs at once, revives stuck ones, signals that
    the worker is alive and, once per period, purges the journal."""

    __slots__ = ("_jobs", "_journal", "_logbook", "_pipelines", "_settings")

    def __init__(
        self,
        jobs: Jobs,
        pipelines: Pipelines,
        settings: Settings,
        journal: Journal,
        logbook: Logbook,
    ) -> None:
        self._jobs: Final = jobs
        self._pipelines: Final = pipelines
        self._settings: Final = settings
        self._journal: Final = journal
        self._logbook: Final = logbook

    async def serve(self, stop: asyncio.Event) -> None:
        running: set[asyncio.Task[None]] = set()
        await self._logbook.hello()
        beaten = purged = float("-inf")
        while not stop.is_set():
            await self._jobs.revive(self._settings.timeout() * 2, self._settings.attempts())
            await self._jobs.resume()
            for job_id in await self._jobs.claim(self._settings.jobs() - len(running)):
                task = asyncio.create_task(self._run(job_id))
                running.add(task)
                task.add_done_callback(running.discard)
            moment = time.monotonic()
            if moment - beaten >= self._settings.beat():
                await self._logbook.beat(len(running))
                beaten = moment
            if moment - purged >= self._settings.purge():
                self._journal.info(f"Очищено строк журнала: {await self._logbook.purge()}", 0, 0)
                purged = moment
            try:
                await asyncio.wait_for(stop.wait(), self._settings.poll())
            except TimeoutError:
                continue
        await asyncio.gather(*running)
        await self._logbook.bye()

    async def drain(self) -> int:
        count = 0
        await self._jobs.resume()
        while claimed := await self._jobs.claim(self._settings.jobs()):
            await asyncio.gather(*(self._run(job_id) for job_id in claimed))
            count += len(claimed)
            await self._jobs.resume()
        return count

    async def _run(self, job_id: int) -> None:
        snapshot = await self._jobs.snapshot(job_id)
        declaration = snapshot.declaration()
        self._journal.info("Задача взята в работу", job_id, declaration)
        await self._logbook.open(job_id)
        try:
            await asyncio.wait_for(self._stages(snapshot), self._settings.timeout())
        except LostError as error:
            self._journal.warning(f"Попытка прекращена: {error}", job_id, declaration)
        except WaitingError as error:
            await self._jobs.wait(job_id, str(error))
            await self._logbook.close(job_id, Waited())
            self._journal.info(f"Задача ждёт: {error}", job_id, declaration)
        except TimeoutError as error:
            self._journal.error(f"Задача не выполнена: {error}", job_id, declaration)
            await self._jobs.fail(job_id, f"{type(error).__name__}: {error}")
            await self._logbook.close(job_id, TimedOut())
        except Exception as error:
            self._journal.error(f"Задача не выполнена: {error}", job_id, declaration)
            await self._jobs.fail(job_id, f"{type(error).__name__}: {error}")
            await self._logbook.close(job_id, Failed(error))
        else:
            await self._jobs.finish(job_id)
            await self._logbook.close(job_id, Succeeded())
            self._journal.info("Задача выполнена", job_id, declaration)

    async def _stages(self, job: Snapshot) -> None:
        stages = self._pipelines.stages(job.kind)
        for index, stage in enumerate(stages):
            await self._jobs.advance(job.id, stage.name(), 100 * index // len(stages))
            started = time.perf_counter()
            await stage.run(job)
            elapsed = time.perf_counter() - started
            await self._jobs.time(job.id, stage.name(), elapsed)
            self._journal.info(
                f"Стадия {stage.name()} заняла {elapsed:.3f} с", job.id, job.declaration()
            )
