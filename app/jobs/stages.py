import asyncio
from pathlib import Path
from typing import Final, Protocol, final

from sqlalchemy import select

from app.core.journal import Journal
from app.jobs.building import (
    Bench,
    Converting,
    Extracting,
    Fetching,
    Models,
    Reading,
    Saving,
    Shelf,
)
from app.jobs.database import Sessions
from app.jobs.folios import Folio
from app.jobs.models import Declaration
from app.jobs.packages import Packages
from app.jobs.queue import Snapshot
from app.policy.package import Package
from app.policy.schema.profile import Profile
from app.storage.layout import Keys


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
class Profiled:
    """Stage that lets a declaration go on only when the profile of its policy is approved.

    A declaration that is not yet bound to a policy has nothing to wait for; binding by the
    number of the policy is the work of a later task.
    """

    __slots__ = ("_folio", "_sessions")

    def __init__(self, folio: Folio, sessions: Sessions) -> None:
        self._folio: Final = folio
        self._sessions: Final = sessions

    def name(self) -> str:
        return "profile"

    async def run(self, job: Snapshot) -> None:
        async with self._sessions.session() as session:
            policy_id = await session.scalar(
                select(Declaration.policy_id).where(Declaration.id == job.declaration())
            )
        if policy_id is not None:
            await self._folio.approved(policy_id)


@final
class Standard:
    """Pipelines of the service where the reconciliation stages are still empty."""

    __slots__ = ("_folio", "_journal", "_sessions")

    def __init__(self, journal: Journal, folio: Folio, sessions: Sessions) -> None:
        self._journal: Final = journal
        self._folio: Final = folio
        self._sessions: Final = sessions

    def stages(self, kind: str) -> tuple[Stage, ...]:
        if kind != "reconcile":
            raise UnknownKindError(f"Для задач типа {kind} нет конвейера")
        return (
            *(Pending(name, self._journal) for name in ("ingest", "fields", "normalize", "bind")),
            Profiled(self._folio, self._sessions),
            *(Pending(name, self._journal) for name in ("check", "semantic", "report")),
        )


@final
class Building:
    """Pipeline of a policy package: fetch, convert, read, extract with the model, save."""

    __slots__ = ("_bench", "_folio", "_journal", "_models", "_packages")

    def __init__(
        self, bench: Bench, folio: Folio, packages: Packages, models: Models, journal: Journal
    ) -> None:
        self._bench: Final = bench
        self._folio: Final = folio
        self._packages: Final = packages
        self._models: Final = models
        self._journal: Final = journal

    def stages(self, kind: str) -> tuple[Stage, ...]:
        if kind != "profile_build":
            raise UnknownKindError(f"Для задач типа {kind} нет конвейера")
        folder: Shelf[Path] = Shelf()
        package: Shelf[Package] = Shelf()
        profile: Shelf[Profile] = Shelf()
        return (
            Fetching(self._bench, Keys(), folder),
            Converting(self._bench, folder, self._journal),
            Reading(folder, package, self._journal),
            Extracting(self._models, package, profile),
            Saving(self._folio, self._packages, package, profile, self._journal),
        )


@final
class Routed:
    """Pipelines that ask the first one and, when it does not know the kind, the second."""

    __slots__ = ("_first", "_second")

    def __init__(self, first: Pipelines, second: Pipelines) -> None:
        self._first: Final = first
        self._second: Final = second

    def stages(self, kind: str) -> tuple[Stage, ...]:
        try:
            return self._first.stages(kind)
        except UnknownKindError:
            return self._second.stages(kind)
