import asyncio
from pathlib import Path

from hamcrest import assert_that, equal_to

from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.database import Database
from app.jobs.models import Base
from app.jobs.queue import Queue, Snapshot
from app.jobs.stages import Pending, Stage
from app.jobs.worker import Shift


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
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


def settings(folder: Path, jobs: int) -> EnvSettings:
    (folder / ".env").write_text(
        f"WORKER_MAX_JOBS={jobs}\nWORKER_POLL_INTERVAL=0.05\nWORKER_JOB_TIMEOUT=5\n",
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
        Shift(queue, pipelines, config, Silent()).drain(),
        Shift(queue, pipelines, config, Silent()).drain(),
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
    await Shift(queue, pipelines, settings(tmp_path, 1), Silent()).drain()
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
    await Shift(queue, Fixed((Broken(),)), settings(tmp_path, 1), Silent()).drain()
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
    worker = Shift(queue, Fixed((Pending("ingest", Silent()),)), settings(tmp_path, 1), Silent())
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
