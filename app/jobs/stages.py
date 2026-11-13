import asyncio
from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, final

from sqlalchemy import select

from app.core.journal import Journal
from app.jobs.binding import Binding, Ingesting, Matching, Numbering
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
from app.jobs.checking import Bound, Checking, Docket, Folder, Judges, Judging, Tabled
from app.jobs.database import Sessions
from app.jobs.folios import Folio
from app.jobs.models import Declaration
from app.jobs.packages import Packages
from app.jobs.queue import Snapshot
from app.jobs.reporting import Reporting
from app.jobs.versions import Versions
from app.policy.package import Package
from app.policy.schema.profile import Profile
from app.storage.disk import Storage
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
@dataclass(frozen=True)
class Kit:
    """What the pipeline of a declaration takes from outside: the folder of the rule cards, the
    storage of result files, the versions of a run, the source of the semantic judge
    and the pool of threads that its calls run in."""

    cards: Path
    storage: Storage
    versions: Versions
    judges: Judges
    pool: Executor


@final
class Standard:
    """Pipelines of the service: a declaration is read, bound to a policy, checked by the rule
    cards, given to the semantic judge and written to the result workbook.

    The semantic judge comes from outside; the one that answers «требует проверки» without
    calling a model is a valid choice until a real judge is connected.
    """

    __slots__ = ("_bench", "_folio", "_journal", "_kit", "_sessions")

    def __init__(
        self, journal: Journal, folio: Folio, sessions: Sessions, bench: Bench, kit: Kit
    ) -> None:
        self._journal: Final = journal
        self._folio: Final = folio
        self._sessions: Final = sessions
        self._bench: Final = bench
        self._kit: Final = kit

    def stages(self, kind: str) -> tuple[Stage, ...]:
        if kind != "reconcile":
            raise UnknownKindError(f"Для задач типа {kind} нет конвейера")
        policy: Shelf[str] = Shelf()
        docket = Docket(Shelf(), Shelf(), Shelf(), Shelf())
        cardfile = Folder(self._kit.cards)
        return (
            Ingesting(self._bench, self._sessions, policy, self._journal),
            *(Pending(name, self._journal) for name in ("fields", "normalize")),
            Binding(
                Matching(self._sessions, Numbering(self._kit.cards)),
                self._sessions,
                policy,
                self._journal,
            ),
            Profiled(self._folio, self._sessions),
            Checking(
                self._bench,
                self._sessions,
                (
                    Bound(self._folio, self._sessions),
                    cardfile,
                    Tabled(self._sessions),
                    self._kit.versions,
                ),
                docket,
                self._journal,
            ),
            Judging(
                (cardfile, Tabled(self._sessions), self._kit.judges),
                self._kit.pool,
                docket,
                self._journal,
            ),
            Reporting(
                (self._bench, self._kit.storage, Keys()),
                self._sessions,
                cardfile,
                docket,
                self._journal,
            ),
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
