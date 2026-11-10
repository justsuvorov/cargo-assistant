import asyncio
from pathlib import Path

from hamcrest import assert_that, equal_to
from sqlalchemy import select

from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.database import Database
from app.jobs.errors import WaitingError
from app.jobs.logbook import Blank, Careful, Journaled, Local, Verdict
from app.jobs.models import Base, JobRun, WorkerHeartbeat
from app.jobs.queue import Queue, Snapshot
from app.jobs.retention import Monthly
from app.jobs.stages import Pending, Stage
from app.jobs.versions import Stamp
from app.jobs.worker import Shift


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass


class Counting:
    """Test double named counting."""

    def __init__(self, name: str, seen: list[int]) -> None:
        self._name = name
        self._seen = seen

    def name(self) -> str:
        return self._name

    async def run(self, job: Snapshot) -> None:
        self._seen.append(job.id)
        await asyncio.sleep(0.001)


class Fixed:
    """Test double named fixed."""

    def __init__(self, stages: tuple[Stage, ...]) -> None:
        self._stages = stages

    def stages(self, kind: str) -> tuple[Stage, ...]:
        if kind != "reconcile":
            raise KeyError(kind)
        return self._stages


class Broken:
    """Test double named broken."""

    def name(self) -> str:
        return "broken"

    async def run(self, job: Snapshot) -> None:
        raise RuntimeError(f"сбой {job.id}")


def settings(folder: Path, jobs: int, timeout: float = 5) -> EnvSettings:
    (folder / ".env").write_text(
        f"WORKER_MAX_JOBS={jobs}\nWORKER_POLL_INTERVAL=0.05\nWORKER_JOB_TIMEOUT={timeout}\n"
        "WORKER_BEAT_INTERVAL=0.05\nWORKER_PURGE_INTERVAL=1000\n",
        encoding="utf-8",
    )
    return EnvSettings(Environment(str(folder / ".env")))


async def prepare(path: Path, count: int) -> tuple[Database, Queue, tuple[int, ...]]:
    database = Database(f"sqlite+aiosqlite:///{path / 'w.db'}")
    queue = Queue(database, Utc())
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        ids = tuple([await queue.add(session, "reconcile", {}) for _ in range(count)])
        await session.commit()
    return database, queue, ids


async def runs_every_stage_once_per_job_with_two_workers(tmp_path: Path) -> list[int]:
    database, queue, _ = await prepare(tmp_path, 12)
    seen: list[int] = []
    pipelines = Fixed((Counting("one", seen), Counting("two", seen)))
    config = settings(tmp_path, 3)
    await asyncio.gather(
        Shift(queue, pipelines, config, Silent(), Blank()).drain(),
        Shift(queue, pipelines, config, Silent(), Blank()).drain(),
    )
    await database.close()
    return seen


def test_runs_every_stage_once_per_job_with_two_workers(tmp_path: Path) -> None:
    seen = asyncio.run(
        asyncio.wait_for(runs_every_stage_once_per_job_with_two_workers(tmp_path), 30)
    )
    assert_that(
        sorted(seen),
        equal_to(sorted(list(range(1, 13)) * 2)),
        "Some stage runs twice or does not run for a job",
    )


async def finishes_job_with_full_progress_and_stage_times(
    tmp_path: Path,
) -> tuple[str, int, list[str]]:
    database, queue, (job,) = await prepare(tmp_path, 1)
    pipelines = Fixed((Pending("ingest", Silent()), Pending("check", Silent())))
    await Shift(queue, pipelines, settings(tmp_path, 1), Silent(), Blank()).drain()
    snapshot = await queue.snapshot(job)
    await database.close()
    return snapshot.status, snapshot.progress, sorted(snapshot.timings)


def test_finishes_job_with_full_progress_and_stage_times(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(finishes_job_with_full_progress_and_stage_times(tmp_path), 30)
        ),
        equal_to(("done", 100, ["check", "ingest"])),
        "Finished job does not have full progress and stage times",
    )


async def fails_job_whose_stage_raises(tmp_path: Path) -> tuple[str, bool]:
    database, queue, (job,) = await prepare(tmp_path, 1)
    await Shift(queue, Fixed((Broken(),)), settings(tmp_path, 1), Silent(), Blank()).drain()
    snapshot = await queue.snapshot(job)
    await database.close()
    return snapshot.status, f"сбой {job}" in snapshot.error


def test_fails_job_whose_stage_raises(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(fails_job_whose_stage_raises(tmp_path), 30)),
        equal_to(("failed", True)),
        "Failing stage does not fail the job with its message",
    )


async def serves_until_stopped(tmp_path: Path) -> str:
    database, queue, (job,) = await prepare(tmp_path, 1)
    stop = asyncio.Event()
    worker = Shift(
        queue, Fixed((Pending("ingest", Silent()),)), settings(tmp_path, 1), Silent(), Blank()
    )
    task = asyncio.create_task(worker.serve(stop))
    while not (await queue.snapshot(job)).finished():
        await asyncio.sleep(0.01)
    stop.set()
    await task
    status = (await queue.snapshot(job)).status
    await database.close()
    return status


def test_serves_until_stopped(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(serves_until_stopped(tmp_path), 30)),
        equal_to("done"),
        "Serving worker does not finish the job",
    )


class Waiting:
    """Test double named waiting."""

    def name(self) -> str:
        return "profile"

    async def run(self, job: Snapshot) -> None:
        raise WaitingError(f"Ожидает профиль полиса{'' * job.id}")


async def parks_job_that_waits_for_profile(tmp_path: Path) -> tuple[str, str]:
    database, queue, (job,) = await prepare(tmp_path, 1)
    await Shift(queue, Fixed((Waiting(),)), settings(tmp_path, 1), Silent(), Blank()).drain()
    snapshot = await queue.snapshot(job)
    await database.close()
    return snapshot.status, snapshot.error


def test_parks_job_that_waits_for_profile(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(parks_job_that_waits_for_profile(tmp_path), 30)),
        equal_to(("waiting", "Ожидает профиль полиса")),
        "Job that waits for a profile is not parked but failed or finished",
    )


class Slow:
    """Test double named slow."""

    def name(self) -> str:
        return "slow"

    async def run(self, job: Snapshot) -> None:
        await asyncio.sleep(job.id + 10)


class Counted:
    """Test double named counted."""

    def __init__(self) -> None:
        self.purges = 0

    async def hello(self) -> None:
        pass

    async def beat(self, running: int) -> None:
        pass

    async def bye(self) -> None:
        pass

    async def open(self, job_id: int) -> None:
        pass

    async def close(self, job_id: int, verdict: Verdict) -> None:
        pass

    async def purge(self) -> int:
        self.purges += 1
        return 0


class Lost:
    """Test double named lost."""

    async def hello(self) -> None:
        raise ConnectionError("нет связи")

    async def beat(self, running: int) -> None:
        raise ConnectionError(f"нет связи {running}")

    async def bye(self) -> None:
        raise ConnectionError("нет связи")

    async def open(self, job_id: int) -> None:
        raise ConnectionError(f"нет связи {job_id}")

    async def close(self, job_id: int, verdict: Verdict) -> None:
        raise ConnectionError(f"нет связи {job_id} {verdict.outcome()}")

    async def purge(self) -> int:
        raise ConnectionError("нет связи")


def journaled(database: Database) -> Journaled:
    return Journaled(
        database, Utc(), Local("v1"), Stamp("c", "k", "p", "m"), Monthly(database, Utc(), 3)
    )


async def outcomes_of_attempts(tmp_path: Path, pipelines: Fixed, timeout: float) -> list[str]:
    database, queue, _ = await prepare(tmp_path, 1)
    logbook = journaled(database)
    await logbook.hello()
    await Shift(queue, pipelines, settings(tmp_path, 1, timeout), Silent(), logbook).drain()
    async with database.session() as session:
        found = [run.outcome for run in (await session.scalars(select(JobRun))).all()]
    await database.close()
    return found


def test_records_successful_attempt_of_a_job(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(
                outcomes_of_attempts(tmp_path, Fixed((Pending("a", Silent()),)), 5), 30
            )
        ),
        equal_to(["success"]),
        "Finished job does not leave a successful attempt in the journal",
    )


def test_records_failed_attempt_of_a_job(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(outcomes_of_attempts(tmp_path, Fixed((Broken(),)), 5), 30)),
        equal_to(["error"]),
        "Failed job does not leave a failed attempt in the journal",
    )


def test_records_waiting_attempt_of_a_job(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(outcomes_of_attempts(tmp_path, Fixed((Waiting(),)), 5), 30)),
        equal_to(["waiting"]),
        "Parked job does not leave a waiting attempt in the journal",
    )


def test_records_timed_out_attempt_of_a_job(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(outcomes_of_attempts(tmp_path, Fixed((Slow(),)), 0.1), 30)),
        equal_to(["timeout"]),
        "Job over the time limit does not leave a timed out attempt in the journal",
    )


async def worker_row_while_serving(tmp_path: Path) -> tuple[bool, bool, bool]:
    database, queue, (job,) = await prepare(tmp_path, 1)
    stop = asyncio.Event()
    worker = Shift(
        queue,
        Fixed((Pending("a", Silent()),)),
        settings(tmp_path, 1),
        Silent(),
        journaled(database),
    )
    task = asyncio.create_task(worker.serve(stop))
    while not (await queue.snapshot(job)).finished():
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.3)
    async with database.session() as session:
        row = (await session.scalars(select(WorkerHeartbeat))).one()
        live = row.stopped_at is None
        beaten = row.last_seen > row.started_at
    stop.set()
    await task
    async with database.session() as session:
        stopped = (await session.scalars(select(WorkerHeartbeat))).one().stopped_at is not None
    await database.close()
    return live, beaten, stopped


def test_signals_regularly_while_serving_and_marks_the_stop(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(worker_row_while_serving(tmp_path), 30)),
        equal_to((True, True, True)),
        "Serving worker does not signal regularly and mark its stop",
    )


async def purges_once_per_period(tmp_path: Path) -> int:
    database, queue, _ = await prepare(tmp_path, 0)
    counted = Counted()
    stop = asyncio.Event()
    task = asyncio.create_task(
        Shift(queue, Fixed(()), settings(tmp_path, 1), Silent(), counted).serve(stop)
    )
    await asyncio.sleep(0.4)
    stop.set()
    await task
    await database.close()
    return counted.purges


def test_purges_journal_once_at_start_and_not_every_poll(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(purges_once_per_period(tmp_path), 30)),
        equal_to(1),
        "Worker does not purge the journal exactly once per period",
    )


async def reconciles_with_lost_journal(tmp_path: Path) -> str:
    database, queue, (job,) = await prepare(tmp_path, 1)
    pipelines = Fixed((Pending("a", Silent()),))
    careful = Careful(Lost(), Silent())
    await Shift(queue, pipelines, settings(tmp_path, 1), Silent(), careful).drain()
    status = (await queue.snapshot(job)).status
    await database.close()
    return status


def test_finishes_job_when_the_journal_cannot_be_written(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(reconciles_with_lost_journal(tmp_path), 30)),
        equal_to("done"),
        "Job is not finished when the journal cannot be written",
    )
