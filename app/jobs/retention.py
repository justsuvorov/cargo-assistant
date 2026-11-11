import asyncio
import calendar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Protocol, final

from sqlalchemy import delete, func, select

from app.core.clock import Clock
from app.ingest.doc import Conversions
from app.jobs.database import Sessions
from app.jobs.models import JobRun, LLMCall, WorkerHeartbeat


class Retention(Protocol):
    """Deletion of journal rows that outlived their storage period."""

    async def purge(self) -> int: ...


@final
class Both:
    """Retention that runs two retentions one after another and adds up what they removed."""

    __slots__ = ("_first", "_second")

    def __init__(self, first: Retention, second: Retention) -> None:
        self._first: Final = first
        self._second: Final = second

    async def purge(self) -> int:
        return await self._first.purge() + await self._second.purge()


@final
class Cached:
    """Retention of the files that conversion of documents leaves in its home folder: a
    file changed earlier than the given number of days ago is removed with the idle profiles."""

    __slots__ = ("_clock", "_days", "_home")

    def __init__(self, home: Path, clock: Clock, days: int) -> None:
        self._home: Final = home
        self._clock: Final = clock
        self._days: Final = days

    async def purge(self) -> int:
        edge = (self._clock.now() - timedelta(days=self._days)).replace(tzinfo=UTC).timestamp()
        return await asyncio.to_thread(Conversions(self._home).sweep, edge)


@final
class Monthly:
    """Retention that keeps the journal for whole calendar months and deletes older rows of
    attempts, calls of the model and worker signals; declarations and results are never touched."""

    __slots__ = ("_clock", "_months", "_sessions")

    def __init__(self, sessions: Sessions, clock: Clock, months: int) -> None:
        self._sessions: Final = sessions
        self._clock: Final = clock
        self._months: Final = months

    async def purge(self) -> int:
        edge = self._edge()
        async with self._sessions.session() as session:
            runs = await session.execute(
                delete(JobRun)
                .where(func.coalesce(JobRun.finished_at, JobRun.started_at) < edge)
                .returning(JobRun.id)
            )
            calls = await session.execute(
                delete(LLMCall).where(LLMCall.created_at < edge).returning(LLMCall.id)
            )
            workers = await session.execute(
                delete(WorkerHeartbeat)
                .where(
                    WorkerHeartbeat.last_seen < edge,
                    WorkerHeartbeat.id.not_in(
                        select(JobRun.worker_id).where(JobRun.worker_id.is_not(None))
                    ),
                )
                .returning(WorkerHeartbeat.id)
            )
            await session.commit()
            return len(runs.all()) + len(calls.all()) + len(workers.all())

    def _edge(self) -> datetime:
        now = self._clock.now()
        index = now.year * 12 + now.month - 1 - self._months
        year, month = divmod(index, 12)
        return now.replace(
            year=year,
            month=month + 1,
            day=min(now.day, calendar.monthrange(year, month + 1)[1]),
        )
