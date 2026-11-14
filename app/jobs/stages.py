import asyncio
import contextvars
from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, final

from pydantic import BaseModel

from app.core.journal import Journal
from app.domain.semantics import Question, Semantics
from app.domain.verdict import Verdict
from app.jobs.binding import Binding, Ingesting
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
from app.jobs.checking import (
    Bound,
    Checking,
    Docket,
    Folder,
    Judge,
    Judges,
    Judging,
    Tabled,
)
from app.jobs.database import Sessions
from app.jobs.errors import MissingProfileError, WaitingError
from app.jobs.folios import Folio
from app.jobs.models import Declaration, Job, Policy
from app.jobs.packages import Packages
from app.jobs.queue import Snapshot
from app.jobs.reporting import Reporting
from app.jobs.versions import Versions
from app.llm.messages import Message
from app.llm.model import Model
from app.policy.package import Package
from app.policy.schema.profile import Profile
from app.semantic import bench
from app.semantic.brief import Brief, Prompt
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
    """Stage that lets a declaration go on as soon as its policy has a profile of any kind, the
    approved one or a draft: it does not wait for a person. While the profile is still being
    built the declaration waits for the build; when the build failed it goes on without a
    profile and every clause of the policy is refused with the reason profile."""

    __slots__ = ("_folio", "_sessions")

    def __init__(self, folio: Folio, sessions: Sessions) -> None:
        self._folio: Final = folio
        self._sessions: Final = sessions

    def name(self) -> str:
        return "profile"

    async def run(self, job: Snapshot) -> None:
        async with self._sessions.session() as session:
            declaration = await session.get(Declaration, job.declaration())
            policy = (
                await session.get(Policy, declaration.policy_id)
                if declaration is not None and declaration.policy_id is not None
                else None
            )
            build = (
                await session.get(Job, policy.job_id)
                if policy is not None and policy.job_id is not None
                else None
            )
        if policy is None:
            return
        try:
            await self._folio.taken(policy.id)
        except MissingProfileError:
            if build is not None and build.status not in {"done", "failed"}:
                raise WaitingError("Ожидает сборки профиля полиса") from None


@final
class Situated:
    """Model that answers in a copy of the context it was obtained in, so that a call made in
    another thread is still booked under the job that asked for the model."""

    __slots__ = ("_context", "_model")

    def __init__(self, model: Model, context: contextvars.Context) -> None:
        self._model: Final = model
        self._context: Final = context

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        return self._context.copy().run(self._model.answer, purpose, messages, schema)


@final
class Briefed:
    """Judge that answers by another semantic judge and tells the version of the prompt it
    asks the model with."""

    __slots__ = ("_prompt", "_semantics")

    def __init__(self, semantics: Semantics, prompt: Prompt) -> None:
        self._semantics: Final = semantics
        self._prompt: Final = prompt

    def version(self) -> str:
        return self._prompt.version()

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        return self._semantics.verdicts(questions)


@final
class Benches:
    """Judges that put the semantic questions of a job on the model gateway: the model is built
    when a job asks for its judge and answers in the context of that request, whatever thread
    calls it; every card gets at most the given number of packs of the given size, so a
    process without a gateway fails only when it really needs one."""

    __slots__ = ("_journal", "_models", "_packs", "_size")

    def __init__(self, models: Models, journal: Journal, packs: int, size: int) -> None:
        self._models: Final = models
        self._journal: Final = journal
        self._packs: Final = packs
        self._size: Final = size

    def judge(self, job_id: int) -> Judge:
        return Briefed(
            bench.Bench(
                Situated(self._models.model(job_id), contextvars.copy_context()),
                self._journal,
                self._packs,
                self._size,
            ),
            Brief(),
        )


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

    The semantic judge comes from outside: the one on the model gateway, or the one that
    answers «требует проверки» without calling a model when the gateway is not configured.
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
        docket = Docket(Shelf(), Shelf(), Shelf(), Shelf(), Shelf())
        cardfile = Folder(self._kit.cards)
        return (
            Ingesting(self._bench, self._sessions, self._journal),
            *(Pending(name, self._journal) for name in ("fields", "normalize")),
            Binding(self._sessions, self._journal),
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
            Fetching(self._bench, self._packages, folder),
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
