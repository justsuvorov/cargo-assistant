import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from hamcrest import assert_that, equal_to
from sqlalchemy import select

from app.jobs.database import Database
from app.jobs.logbook import (
    Blank,
    Careful,
    Failed,
    Journaled,
    Local,
    Succeeded,
    TimedOut,
    Verdict,
    Waited,
)
from app.jobs.models import Base, Declaration, JobRun, Policy, PolicyProfile, WorkerHeartbeat
from app.jobs.queue import Queue
from app.jobs.retention import Monthly
from app.jobs.versions import Stamp


class Moving:
    """Test double named moving."""

    def __init__(self) -> None:
        self.moment = datetime(2026, 1, 1, 12, 0)

    def now(self) -> datetime:
        return self.moment


class Recording:
    """Test double named recording."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, int, int]] = []

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        self.lines.append((message, job_id, declaration_id))

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        self.lines.append((message, job_id, declaration_id))

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        self.lines.append((message, job_id, declaration_id))


class Broken:
    """Test double named broken."""

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


async def prepare(path: Path, clock: Moving) -> tuple[Database, Journaled, Queue, int]:
    database = Database(f"sqlite+aiosqlite:///{path / 'b.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        session.add(Policy(id=3, access_group="g"))
        session.add(
            Declaration(id=5, policy_id=3, access_group="g", file_name="n", created_at=clock.moment)
        )
        for version, status in ((1, "replaced"), (2, "approved"), (3, "draft")):
            session.add(PolicyProfile(policy_id=3, version=version, status=status))
        await session.commit()
    queue = Queue(database, clock)
    async with database.session() as session:
        job = await queue.add(session, "reconcile", {"declaration_id": 5})
        await session.commit()
    logbook = Journaled(
        database,
        clock,
        Local("v1"),
        Stamp("code", "cards", "prompts", "model"),
        Monthly(database, clock, 3),
    )
    return database, logbook, queue, job


async def signals_of_worker(tmp_path: Path) -> list[tuple[int, bool, bool]]:
    clock = Moving()
    database, logbook, _, _ = await prepare(tmp_path, clock)
    found: list[tuple[int, bool, bool]] = []
    await logbook.hello()
    clock.moment += timedelta(seconds=30)
    await logbook.beat(2)
    async with database.session() as session:
        row = (await session.scalars(select(WorkerHeartbeat))).one()
        found.append((row.running, row.last_seen == clock.moment, row.stopped_at is None))
    await logbook.bye()
    async with database.session() as session:
        row = (await session.scalars(select(WorkerHeartbeat))).one()
        found.append((row.running, row.last_seen == clock.moment, row.stopped_at is None))
    await database.close()
    return found


def test_records_start_signal_and_stop_of_worker(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(signals_of_worker(tmp_path), 30)),
        equal_to([(2, True, True), (0, True, False)]),
        "Worker row does not show the signal with running jobs and then the stop",
    )


async def recreates_worker_row_on_signal(tmp_path: Path) -> int:
    clock = Moving()
    database, logbook, _, _ = await prepare(tmp_path, clock)
    await logbook.beat(1)
    async with database.session() as session:
        count = len((await session.scalars(select(WorkerHeartbeat))).all())
    await database.close()
    return count


def test_recreates_worker_row_when_the_first_signal_was_lost(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(recreates_worker_row_on_signal(tmp_path), 30)),
        equal_to(1),
        "Signal of a worker without a row does not create the row",
    )


async def attempt_after(
    tmp_path: Path, verdict: Verdict
) -> tuple[str, str, str, int, str, bool, bool]:
    clock = Moving()
    database, logbook, queue, job = await prepare(tmp_path, clock)
    await logbook.hello()
    await queue.claim(1)
    clock.moment += timedelta(seconds=2)
    await logbook.open(job)
    await queue.time(job, "ingest", 0.5)
    clock.moment += timedelta(seconds=7)
    await logbook.close(job, verdict)
    async with database.session() as session:
        run = (await session.scalars(select(JobRun))).one()
        found = (
            run.outcome,
            run.error_class,
            run.error_text,
            run.attempt,
            f"{run.code_version} {run.cards_version} {run.prompts_version} {run.model}",
            run.finished_at == clock.moment and run.timings == {"ingest": 0.5},
            run.queued_at == datetime(2026, 1, 1, 12, 0) and run.profile_version == 2,
        )
    await database.close()
    return found


def test_records_successful_attempt_with_versions_and_stage_times(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(attempt_after(tmp_path, Succeeded()), 30)),
        equal_to(("success", "", "", 1, "code cards prompts model", True, True)),
        "Successful attempt does not keep its outcome, versions, stage times and queue time",
    )


def test_records_class_and_text_of_the_error_of_failed_attempt(tmp_path: Path) -> None:
    found = asyncio.run(asyncio.wait_for(attempt_after(tmp_path, Failed(KeyError("поле"))), 30))
    assert_that(
        found[:3],
        equal_to(("error", "KeyError", "'поле'")),
        "Failed attempt does not keep the class and the text of the error",
    )


def test_records_timeout_of_attempt(tmp_path: Path) -> None:
    found = asyncio.run(asyncio.wait_for(attempt_after(tmp_path, TimedOut()), 30))
    assert_that(
        found[:2],
        equal_to(("timeout", "TimeoutError")),
        "Timed out attempt does not keep the timeout outcome and class",
    )


def test_records_waiting_of_attempt_for_profile(tmp_path: Path) -> None:
    found = asyncio.run(asyncio.wait_for(attempt_after(tmp_path, Waited()), 30))
    assert_that(
        found[:2],
        equal_to(("waiting", "")),
        "Attempt that waits for a profile does not keep the waiting outcome",
    )


async def survives_broken_journal() -> list[tuple[str, int, int]]:
    sink = Recording()
    careful = Careful(Broken(), sink)
    await careful.hello()
    await careful.beat(1)
    await careful.open(4)
    await careful.close(4, Succeeded())
    await careful.purge()
    await careful.bye()
    return sink.lines


def test_logs_failed_journal_write_and_does_not_raise() -> None:
    lines = asyncio.run(asyncio.wait_for(survives_broken_journal(), 30))
    assert_that(
        [(line[1], "ConnectionError" in line[0]) for line in lines],
        equal_to([(0, True), (0, True), (4, True), (4, True), (0, True), (0, True)]),
        "Broken journal is not logged with the job id for each write",
    )


async def does_nothing_when_blank() -> int:
    blank = Blank()
    await blank.hello()
    await blank.open(1)
    await blank.close(1, Succeeded())
    return await blank.purge()


def test_does_nothing_when_blank() -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(does_nothing_when_blank(), 30)),
        equal_to(0),
        "Blank journal does not stay silent",
    )
