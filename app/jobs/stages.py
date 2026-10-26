import asyncio
from typing import Final, Protocol, final

from app.core.journal import Journal
from app.jobs.queue import Snapshot


@final
class UnknownKindError(Exception):
    """Job kind that has no pipeline in this version of the service."""

    __slots__ = ()


class Stage(Protocol):
    """Step of a pipeline that runs for one job."""

    def name(self) -> str: ...

    async def run(self, job: Snapshot) -> None: ...


class Pipelines(Protocol):
    """Ordered stages for every kind of job."""

    def stages(self, kind: str) -> tuple[Stage, ...]: ...


@final
class Pending:
    """Stage whose real work is not connected yet, so it only yields to other tasks."""

    __slots__ = ("_journal", "_name")

    def __init__(self, name: str, journal: Journal) -> None:
        self._name: Final = name
        self._journal: Final = journal

    def name(self) -> str:
        return self._name

    async def run(self, job: Snapshot) -> None:
        self._journal.info(f"Стадия {self._name} пока не реализована", job.id, job.declaration())
        await asyncio.sleep(0)


@final
class Standard:
    """Pipelines of the service where the reconciliation stages are still empty."""

    __slots__ = ("_journal",)

    def __init__(self, journal: Journal) -> None:
        self._journal: Final = journal

    def stages(self, kind: str) -> tuple[Stage, ...]:
        if kind != "reconcile":
            raise UnknownKindError(f"Для задач типа {kind} нет конвейера")
        return tuple(
            Pending(name, self._journal)
            for name in ("ingest", "fields", "normalize", "bind", "check", "semantic", "report")
        )
