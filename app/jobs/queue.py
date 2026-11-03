from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Protocol, final

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.jobs.database import Sessions
from app.jobs.models import Declaration, Job


@final
class MissingJobError(Exception):
    """Job that is not in the queue table."""

    __slots__ = ()


@final
@dataclass(frozen=True)
class Snapshot:
    """State of a job at the moment it was read."""

    id: int
    kind: str
    status: str
    stage: str
    progress: int
    attempts: int
    error: str
    timings: dict[str, float]
    payload: dict[str, object]

    @classmethod
    def of(cls, job: Job) -> "Snapshot":
        return cls(
            job.id,
            job.kind,
            job.status,
            job.stage,
            job.progress,
            job.attempts,
            job.error,
            dict(job.timings),
            dict(job.payload),
        )

    def declaration(self) -> int:
        return int(str(self.payload.get("declaration_id", 0)))

    def finished(self) -> bool:
        return self.status in {"done", "failed"}


class Jobs(Protocol):
    """Queue of jobs kept in the database and shared by processes."""

    async def add(self, session: AsyncSession, kind: str, payload: dict[str, object]) -> int: ...

    async def claim(self, limit: int) -> tuple[int, ...]: ...

    async def snapshot(self, job_id: int) -> Snapshot: ...

    async def advance(self, job_id: int, stage: str, progress: int) -> None: ...

    async def time(self, job_id: int, stage: str, seconds: float) -> None: ...

    async def finish(self, job_id: int) -> None: ...

    async def fail(self, job_id: int, error: str) -> None: ...

    async def wait(self, job_id: int, reason: str) -> None: ...

    async def release(self, policy_id: int) -> int: ...

    async def revive(self, idle: float, attempts: int) -> int: ...


@final
class Queue:
    """Job queue where a job is claimed by one atomic statement that skips locked rows."""

    __slots__ = ("_clock", "_sessions")

    def __init__(self, sessions: Sessions, clock: Clock) -> None:
        self._sessions: Final = sessions
        self._clock: Final = clock

    async def add(self, session: AsyncSession, kind: str, payload: dict[str, object]) -> int:
        job = Job(
            kind=kind,
            payload=payload,
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )
        session.add(job)
        await session.flush()
        return job.id

    async def claim(self, limit: int) -> tuple[int, ...]:
        claimed: list[int] = []
        async with self._sessions.session() as session:
            for _ in range(limit):
                first = (
                    select(Job.id)
                    .where(Job.status == "queued")
                    .order_by(Job.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                    .scalar_subquery()
                )
                found = await session.execute(
                    update(Job)
                    .where(Job.id == first, Job.status == "queued")
                    .values(
                        status="running",
                        stage="",
                        progress=0,
                        timings={},
                        error="",
                        attempts=Job.attempts + 1,
                        locked_at=self._clock.now(),
                        updated_at=self._clock.now(),
                    )
                    .returning(Job.id)
                    .execution_options(synchronize_session=False)
                )
                await session.commit()
                claimed.extend(found.scalars())
        return tuple(claimed)

    async def snapshot(self, job_id: int) -> Snapshot:
        async with self._sessions.session() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise MissingJobError(f"Задача {job_id} не найдена")
            return Snapshot.of(job)

    async def advance(self, job_id: int, stage: str, progress: int) -> None:
        await self._change(job_id, stage=stage, progress=progress, locked_at=self._clock.now())

    async def time(self, job_id: int, stage: str, seconds: float) -> None:
        async with self._sessions.session() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise MissingJobError(f"Задача {job_id} не найдена")
            job.timings = {**job.timings, stage: seconds}
            job.updated_at = self._clock.now()
            await session.commit()

    async def finish(self, job_id: int) -> None:
        await self._change(job_id, status="done", progress=100)

    async def fail(self, job_id: int, error: str) -> None:
        await self._change(job_id, status="failed", error=error)

    async def wait(self, job_id: int, reason: str) -> None:
        await self._change(job_id, status="waiting", error=reason, locked_at=None)

    async def release(self, policy_id: int) -> int:
        async with self._sessions.session() as session:
            found = await session.execute(
                update(Job)
                .where(
                    Job.status == "waiting",
                    Job.id.in_(
                        select(Declaration.job_id).where(Declaration.policy_id == policy_id)
                    ),
                )
                .values(status="queued", error="", attempts=0, updated_at=self._clock.now())
                .returning(Job.id)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            return len(found.all())

    async def revive(self, idle: float, attempts: int) -> int:
        limit = self._clock.now() - timedelta(seconds=idle)
        async with self._sessions.session() as session:
            stuck = update(Job).where(Job.status == "running", Job.locked_at < limit)
            again = await session.execute(
                stuck.where(Job.attempts < attempts)
                .values(status="queued", locked_at=None, updated_at=self._clock.now())
                .returning(Job.id)
                .execution_options(synchronize_session=False)
            )
            await session.execute(
                stuck.where(Job.attempts >= attempts)
                .values(
                    status="failed",
                    error="Превышено число попыток обработки задачи",
                    updated_at=self._clock.now(),
                )
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            return len(again.all())

    async def _change(self, job_id: int, **values: object) -> None:
        async with self._sessions.session() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(updated_at=self._clock.now(), **values)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
