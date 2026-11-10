import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from hamcrest import assert_that, equal_to
from sqlalchemy import func, select

from app.jobs.database import Database
from app.jobs.models import (
    Base,
    CheckResult,
    Declaration,
    Job,
    JobRun,
    LLMCall,
    WorkerHeartbeat,
)
from app.jobs.retention import Monthly


class Fixed:
    """Test double named fixed."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


async def prepare(path: Path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{path / 'r.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        await session.commit()
    return database


async def count(database: Database, table: type[Base]) -> int:
    async with database.session() as session:
        return int(await session.scalar(select(func.count()).select_from(table)) or 0)


async def purges_by_boundary(
    tmp_path: Path, now: datetime, edge: datetime
) -> tuple[int, int, int, int, int]:
    database = await prepare(tmp_path)
    async with database.session() as session:
        session.add(Job(id=1, kind="reconcile", created_at=edge, updated_at=edge))
        session.add(Declaration(access_group="g", file_name="n", created_at=edge))
        session.add(
            CheckResult(
                declaration_id=1, line="1", field="f", status="s", reason="r", source="rule"
            )
        )
        for offset in (-1, 1):
            moment = edge + timedelta(minutes=offset)
            session.add(JobRun(job_id=1, started_at=moment, finished_at=moment, outcome="success"))
            session.add(LLMCall(purpose="p", prompt_hash="h", created_at=moment))
        for key, offset in (("old", -1), ("new", 1)):
            moment = edge + timedelta(minutes=offset)
            session.add(
                WorkerHeartbeat(
                    id=key, host="h", pid=1, started_at=moment, last_seen=moment, running=0
                )
            )
        await session.commit()
    removed = await Monthly(database, Fixed(now), 3).purge()
    found = (
        removed,
        await count(database, JobRun),
        await count(database, LLMCall),
        await count(database, WorkerHeartbeat),
        await count(database, Job)
        + await count(database, Declaration)
        + await count(database, CheckResult),
    )
    await database.close()
    return found


def test_deletes_journal_rows_older_than_three_months_and_keeps_newer(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(
                purges_by_boundary(
                    tmp_path, datetime(2026, 11, 10, 12, 0), datetime(2026, 8, 10, 12, 0)
                ),
                30,
            )
        ),
        equal_to((3, 1, 1, 1, 3)),
        "Purge does not cut the journal exactly at three months and keep the reconciliation data",
    )


def test_clamps_the_day_when_the_month_is_shorter(tmp_path: Path) -> None:
    found = asyncio.run(
        asyncio.wait_for(
            purges_by_boundary(
                tmp_path, datetime(2026, 5, 31, 12, 0), datetime(2026, 2, 28, 12, 0)
            ),
            30,
        )
    )
    assert_that(
        found,
        equal_to((3, 1, 1, 1, 3)),
        "Purge on the thirty first does not cut at the end of February",
    )
