import os
import socket
import uuid
from typing import Final, Protocol, final

from sqlalchemy import func, select

from app.core.clock import Clock
from app.core.journal import Journal
from app.jobs.database import Sessions
from app.jobs.models import Declaration, Job, JobRun, PolicyProfile, WorkerHeartbeat
from app.jobs.retention import Retention
from app.jobs.versions import Versions

_TEXT = 2000


class Process(Protocol):
    """Worker process as the journal knows it."""

    def key(self) -> str: ...

    def host(self) -> str: ...

    def pid(self) -> int: ...

    def version(self) -> str: ...


@final
class Local:
    """The running process, named by a random key generated when the process starts."""

    __slots__ = ("_key", "_version")

    def __init__(self, version: str) -> None:
        self._key: Final = uuid.uuid4().hex
        self._version: Final = version

    def key(self) -> str:
        return self._key

    def host(self) -> str:
        return socket.gethostname()

    def pid(self) -> int:
        return os.getpid()

    def version(self) -> str:
        return self._version


class Verdict(Protocol):
    """How one attempt to run a job ended."""

    def outcome(self) -> str: ...

    def error_class(self) -> str: ...

    def error_text(self) -> str: ...


@final
class Succeeded:
    """Attempt that ran every stage."""

    __slots__ = ()

    def outcome(self) -> str:
        return "success"

    def error_class(self) -> str:
        return ""

    def error_text(self) -> str:
        return ""


@final
class Waited:
    """Attempt that stopped to wait for something outside the job, such as a profile."""

    __slots__ = ()

    def outcome(self) -> str:
        return "waiting"

    def error_class(self) -> str:
        return ""

    def error_text(self) -> str:
        return ""


@final
class TimedOut:
    """Attempt that did not fit into the time limit of a job."""

    __slots__ = ()

    def outcome(self) -> str:
        return "timeout"

    def error_class(self) -> str:
        return "TimeoutError"

    def error_text(self) -> str:
        return ""


@final
class Failed:
    """Attempt that ended with an error; only its class goes to the views, the text stays in the
    table because it may name a file."""

    __slots__ = ("_error",)

    def __init__(self, error: Exception) -> None:
        self._error: Final = error

    def outcome(self) -> str:
        return "error"

    def error_class(self) -> str:
        return self._error.__class__.__name__

    def error_text(self) -> str:
        return str(self._error)[:_TEXT]


class Logbook(Protocol):
    """Journal of workers and attempts that the monitoring views are built on."""

    async def hello(self) -> None: ...

    async def beat(self, running: int) -> None: ...

    async def bye(self) -> None: ...

    async def open(self, job_id: int) -> None: ...

    async def close(self, job_id: int, verdict: Verdict) -> None: ...

    async def purge(self) -> int: ...


@final
class Blank:
    """Logbook that writes nothing."""

    __slots__ = ()

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
        return 0


@final
class Journaled:
    """Logbook in the database: one row per worker process and one per attempt of a job."""

    __slots__ = ("_clock", "_process", "_retention", "_sessions", "_versions")

    def __init__(
        self,
        sessions: Sessions,
        clock: Clock,
        process: Process,
        versions: Versions,
        retention: Retention,
    ) -> None:
        self._sessions: Final = sessions
        self._clock: Final = clock
        self._process: Final = process
        self._versions: Final = versions
        self._retention: Final = retention

    async def hello(self) -> None:
        async with self._sessions.session() as session:
            await session.merge(self._row(running=0))
            await session.commit()

    async def beat(self, running: int) -> None:
        async with self._sessions.session() as session:
            row = await session.get(WorkerHeartbeat, self._process.key())
            if row is None:
                await session.merge(self._row(running=running))
            else:
                row.last_seen = self._clock.now()
                row.running = running
            await session.commit()

    async def bye(self) -> None:
        async with self._sessions.session() as session:
            row = await session.get(WorkerHeartbeat, self._process.key())
            if row is not None:
                row.stopped_at = self._clock.now()
                row.last_seen = self._clock.now()
                row.running = 0
            await session.commit()

    async def open(self, job_id: int) -> None:
        async with self._sessions.session() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise LookupError(f"Задача {job_id} не найдена для записи попытки")
            profile = await session.scalar(
                select(func.max(PolicyProfile.version))
                .join(Declaration, Declaration.policy_id == PolicyProfile.policy_id)
                .where(
                    Declaration.id == int(str(job.payload.get("declaration_id", 0))),
                    PolicyProfile.status == "approved",
                )
            )
            session.add(
                JobRun(
                    job_id=job_id,
                    attempt=job.attempts,
                    worker_id=self._process.key(),
                    queued_at=job.queued_at,
                    started_at=self._clock.now(),
                    outcome="running",
                    code_version=self._versions.code(),
                    cards_version=self._versions.cards(),
                    profile_version=profile or 0,
                    prompts_version=self._versions.prompts(),
                    model=self._versions.model(),
                )
            )
            await session.commit()

    async def close(self, job_id: int, verdict: Verdict) -> None:
        async with self._sessions.session() as session:
            job = await session.get(Job, job_id)
            run = await session.scalar(
                select(JobRun)
                .where(JobRun.job_id == job_id, JobRun.finished_at.is_(None))
                .order_by(JobRun.id.desc())
                .limit(1)
            )
            if job is None or run is None:
                raise LookupError(f"У задачи {job_id} нет открытой попытки")
            run.finished_at = self._clock.now()
            run.outcome = verdict.outcome()
            run.error_class = verdict.error_class()
            run.error_text = verdict.error_text()
            run.timings = dict(job.timings)
            await session.commit()

    async def purge(self) -> int:
        return await self._retention.purge()

    def _row(self, running: int) -> WorkerHeartbeat:
        return WorkerHeartbeat(
            id=self._process.key(),
            host=self._process.host()[:128],
            pid=self._process.pid(),
            version=self._process.version()[:64],
            started_at=self._clock.now(),
            last_seen=self._clock.now(),
            running=running,
        )


@final
class Careful:
    """Logbook whose failures go to the log: a lost journal row never stops a reconciliation."""

    __slots__ = ("_journal", "_logbook")

    def __init__(self, logbook: Logbook, journal: Journal) -> None:
        self._logbook: Final = logbook
        self._journal: Final = journal

    async def hello(self) -> None:
        try:
            await self._logbook.hello()
        except Exception as error:
            self._lost("регистрация воркера", error, 0)

    async def beat(self, running: int) -> None:
        try:
            await self._logbook.beat(running)
        except Exception as error:
            self._lost("сигнал воркера", error, 0)

    async def bye(self) -> None:
        try:
            await self._logbook.bye()
        except Exception as error:
            self._lost("остановка воркера", error, 0)

    async def open(self, job_id: int) -> None:
        try:
            await self._logbook.open(job_id)
        except Exception as error:
            self._lost("начало попытки", error, job_id)

    async def close(self, job_id: int, verdict: Verdict) -> None:
        try:
            await self._logbook.close(job_id, verdict)
        except Exception as error:
            self._lost("конец попытки", error, job_id)

    async def purge(self) -> int:
        try:
            return await self._logbook.purge()
        except Exception as error:
            self._lost("очистка журнала", error, 0)
            return 0

    def _lost(self, what: str, error: Exception, job_id: int) -> None:
        self._journal.error(
            f"Запись журнала не удалась ({what}), {error.__class__.__name__}: {error}", job_id, 0
        )
