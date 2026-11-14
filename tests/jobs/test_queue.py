import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path

from hamcrest import assert_that, equal_to
from sqlalchemy import select

from app.core.clock import Utc
from app.jobs.database import Database
from app.jobs.models import Base, Declaration, Job, JobRun, Policy, PolicyProfile
from app.jobs.queue import Queue


class Moving:
    """Test double named moving."""

    def __init__(self) -> None:
        self.moment = datetime(2026, 1, 1)

    def now(self) -> datetime:
        return self.moment


async def prepare(path: Path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{path / 'q.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        await session.commit()
    return database


async def add(database: Database, queue: Queue, count: int) -> tuple[int, ...]:
    async with database.session() as session:
        ids = tuple([await queue.add(session, "reconcile", {"n": n}) for n in range(count)])
        await session.commit()
    return ids


async def claims_each_job_once_for_two_concurrent_workers(tmp_path: Path) -> list[int]:
    first = await prepare(tmp_path)
    second = Database(f"sqlite+aiosqlite:///{tmp_path / 'q.db'}")
    await add(first, Queue(first, Utc()), 30)
    taken = await asyncio.gather(Queue(first, Utc()).claim(30), Queue(second, Utc()).claim(30))
    await first.close()
    await second.close()
    return [*taken[0], *taken[1]]


def test_claims_each_job_once_for_two_concurrent_workers(tmp_path: Path) -> None:
    claimed = asyncio.run(
        asyncio.wait_for(claims_each_job_once_for_two_concurrent_workers(tmp_path), 30)
    )
    assert_that(
        sorted(claimed),
        equal_to(list(range(1, 31))),
        "Some job is claimed twice or not claimed at all",
    )


async def claims_no_more_than_the_limit(tmp_path: Path) -> int:
    database = await prepare(tmp_path)
    queue = Queue(database, Utc())
    await add(database, queue, 5)
    count = len(await queue.claim(2))
    await database.close()
    return count


def test_claims_no_more_than_the_limit(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(claims_no_more_than_the_limit(tmp_path), 30)),
        equal_to(2),
        "Claim does not stop at the limit",
    )


async def counts_attempt_on_claim(tmp_path: Path) -> int:
    database = await prepare(tmp_path)
    queue = Queue(database, Utc())
    (job,) = await add(database, queue, 1)
    await queue.claim(1)
    attempts = (await queue.snapshot(job)).attempts
    await database.close()
    return attempts


def test_counts_attempt_on_claim(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(counts_attempt_on_claim(tmp_path), 30)),
        equal_to(1),
        "Claim does not count the attempt",
    )


async def returns_stuck_job_to_queue(tmp_path: Path) -> tuple[str, int]:
    database = await prepare(tmp_path)
    clock = Moving()
    queue = Queue(database, clock)
    (job,) = await add(database, queue, 1)
    await queue.claim(1)
    clock.moment += timedelta(seconds=100)
    revived = await queue.revive(50, 3)
    status = (await queue.snapshot(job)).status
    await database.close()
    return status, revived


def test_returns_stuck_job_to_queue(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(returns_stuck_job_to_queue(tmp_path), 30)),
        equal_to(("queued", 1)),
        "Stuck job is not returned to the queue",
    )


async def keeps_fresh_job_running(tmp_path: Path) -> str:
    database = await prepare(tmp_path)
    clock = Moving()
    queue = Queue(database, clock)
    (job,) = await add(database, queue, 1)
    await queue.claim(1)
    clock.moment += timedelta(seconds=10)
    await queue.revive(50, 3)
    status = (await queue.snapshot(job)).status
    await database.close()
    return status


def test_keeps_fresh_job_running(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(keeps_fresh_job_running(tmp_path), 30)),
        equal_to("running"),
        "Fresh job is not left with its worker",
    )


async def fails_job_after_last_attempt(tmp_path: Path) -> str:
    database = await prepare(tmp_path)
    clock = Moving()
    queue = Queue(database, clock)
    (job,) = await add(database, queue, 1)
    for _ in range(2):
        await queue.claim(1)
        clock.moment += timedelta(seconds=100)
        await queue.revive(50, 2)
    status = (await queue.snapshot(job)).status
    await database.close()
    return status


def test_fails_job_after_last_attempt(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(fails_job_after_last_attempt(tmp_path), 30)),
        equal_to("failed"),
        "Job is not failed after the last attempt",
    )


async def saves_stage_time_in_job(tmp_path: Path) -> dict[str, float]:
    database = await prepare(tmp_path)
    queue = Queue(database, Utc())
    (job,) = await add(database, queue, 1)
    seconds = random.random()
    await queue.time(job, "ingest", seconds)
    await queue.time(job, "fields", seconds)
    timings = (await queue.snapshot(job)).timings
    await database.close()
    return timings


def test_saves_stage_time_in_job(tmp_path: Path) -> None:
    assert_that(
        sorted(asyncio.run(asyncio.wait_for(saves_stage_time_in_job(tmp_path), 30))),
        equal_to(["fields", "ingest"]),
        "Stage times are not kept together in the job",
    )


async def journal_after_finish(tmp_path: Path, *, fail: bool) -> tuple[str, bool, bool]:
    database = await prepare(tmp_path)
    clock = Moving()
    queue = Queue(database, clock)
    (job,) = await add(database, queue, 1)
    await queue.claim(1)
    clock.moment += timedelta(seconds=5)
    if fail:
        await queue.fail(job, "KeyError: x")
    else:
        await queue.finish(job)
    async with database.session() as session:
        row = await session.get(Job, job)
        assert row is not None
        found = (row.outcome, row.finished_at == clock.moment, row.queued_at == Moving().moment)
    await database.close()
    return found


def test_records_success_and_finish_time_when_job_finishes(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(journal_after_finish(tmp_path, fail=False), 30)),
        equal_to(("success", True, True)),
        "Finished job does not keep its outcome, finish time and queue time",
    )


def test_records_error_and_finish_time_when_job_fails(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(journal_after_finish(tmp_path, fail=True), 30)),
        equal_to(("error", True, True)),
        "Failed job does not keep its outcome, finish time and queue time",
    )


async def attempt_after_revive(tmp_path: Path, attempts: int) -> tuple[str, str, str]:
    database = await prepare(tmp_path)
    clock = Moving()
    queue = Queue(database, clock)
    (job,) = await add(database, queue, 1)
    await queue.claim(1)
    async with database.session() as session:
        session.add(JobRun(job_id=job, attempt=1, started_at=clock.moment))
        await session.commit()
    clock.moment += timedelta(seconds=100)
    await queue.revive(50, attempts)
    async with database.session() as session:
        run = (await session.scalars(select(JobRun))).one()
        row = await session.get(Job, job)
        assert row is not None
        found = (run.outcome, run.error_class, row.outcome)
    await database.close()
    return found


def test_closes_open_attempt_as_requeued_when_job_is_revived(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(attempt_after_revive(tmp_path, 3), 30)),
        equal_to(("requeued", "", "")),
        "Revived job does not close its open attempt as requeued",
    )


def test_closes_open_attempt_as_error_when_attempts_are_exhausted(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(attempt_after_revive(tmp_path, 1), 30)),
        equal_to(("error", "AttemptsExceeded", "error")),
        "Exhausted job does not close its open attempt and session as errors",
    )


async def resumed_job_of_policy(tmp_path: Path, *, profile: bool, build: str) -> str:
    database = await prepare(tmp_path)
    queue = Queue(database, Utc())
    async with database.session() as session:
        built = await queue.add(session, "profile_build", {"policy_id": 1})
        waiting = await queue.add(session, "reconcile", {"declaration_id": 1})
        session.add(Policy(owner="u", package_sha="s", job_id=built))
        await session.flush()
        session.add(
            Declaration(
                owner="u",
                policy_id=1,
                job_id=waiting,
                file_name="a",
                created_at=datetime(2026, 1, 1),
            )
        )
        if profile:
            session.add(PolicyProfile(policy_id=1, version=1, body={}, status="draft"))
        await session.commit()
    await queue.claim(2)
    await queue.wait(waiting, "Ожидает сборки профиля полиса")
    if build == "failed":
        await queue.fail(built, "нет модели")
    await queue.resume()
    status = (await queue.snapshot(waiting)).status
    await database.close()
    return status


def test_resumes_waiting_job_when_policy_has_a_profile(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(resumed_job_of_policy(tmp_path, profile=True, build="running"), 30)
        ),
        equal_to("queued"),
        "Job is not resumed when the profile of its policy appeared",
    )


def test_resumes_waiting_job_when_build_of_the_profile_failed(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(resumed_job_of_policy(tmp_path, profile=False, build="failed"), 30)
        ),
        equal_to("queued"),
        "Job is not resumed when the build of the profile failed",
    )


def test_keeps_waiting_job_while_the_profile_is_being_built(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(resumed_job_of_policy(tmp_path, profile=False, build="running"), 30)
        ),
        equal_to("waiting"),
        "Job does not keep waiting while its profile is still being built",
    )
