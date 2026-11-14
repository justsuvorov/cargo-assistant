import asyncio
import shutil
import time
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, final

from sqlalchemy import delete

from app.core.journal import Journal
from app.declarations.declared import Declared
from app.domain.card import Card
from app.domain.declaration import Declaration as Filed
from app.domain.policy import Policy, Unbound
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Question, Semantics
from app.domain.shipment import Shipment
from app.domain.status import Review
from app.domain.verdict import Ruling, Verdict
from app.ingest.source import Source
from app.jobs.building import Bench, Cell
from app.jobs.database import Sessions
from app.jobs.errors import MissingProfileError
from app.jobs.folios import Folio, Taken
from app.jobs.models import CheckResult, Declaration
from app.jobs.ownership import Holding
from app.jobs.queue import Snapshot
from app.jobs.versions import Versions
from app.llm.errors import MisconfiguredError
from app.reconcile.reconciliation import Carded, Findings, Reconciliation
from app.rules.cards import Cards

_UNNUMBERED = "без номера"

type Signature = tuple[tuple[str, ...], ...]


@final
class Retained:
    """Declaration whose header and shipment rows were read once and are kept in memory, so that
    every rule card sees the same rows without reading the file again."""

    __slots__ = ("_form", "_number", "_policy", "_shipments")

    def __init__(
        self, number: str, form: str, policy: str, shipments: tuple[Shipment, ...]
    ) -> None:
        self._number: Final = number
        self._form: Final = form
        self._policy: Final = policy
        self._shipments: Final = shipments

    def number(self) -> str:
        return self._number

    def form(self) -> str:
        return self._form

    def policy(self) -> str:
        return self._policy

    def shipments(self) -> tuple[Shipment, ...]:
        return self._shipments


class Standing(Protocol):
    """Profile that a declaration is checked by: the one of the policy it is bound to, or, when
    that policy has no profile, a policy that refuses every clause with the reason profile."""

    async def taken(self, declaration_id: int, number: str) -> Taken: ...


@final
class Bound:
    """Standing that follows the binding written to the declaration by the stage that binds."""

    __slots__ = ("_folio", "_sessions")

    def __init__(self, folio: Folio, sessions: Sessions) -> None:
        self._folio: Final = folio
        self._sessions: Final = sessions

    async def taken(self, declaration_id: int, number: str) -> Taken:
        async with self._sessions.session() as session:
            row = await session.get(Declaration, declaration_id)
        if row is None:
            raise LookupError(f"Декларация {declaration_id} не найдена")
        if row.policy_id is None:
            raise LookupError(f"Декларация {declaration_id} не прошла привязку к полису")
        try:
            return await self._folio.taken(row.policy_id)
        except MissingProfileError:
            return Taken(Unbound("policy_profile", number), 0, "missing", ())


@final
class Postponed:
    """Semantic judge that asks nobody: every question stays «требует проверки» with the code
    semantic.pending, and no model is called."""

    __slots__ = ()

    def version(self) -> str:
        return "none"

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        return tuple(
            Ruling(
                question.place(),
                Review(),
                Cause("semantic.pending", "rule"),
                Note("Смысловая проверка не выполнена, нужна проверка человеком", ""),
            )
            for question in questions
        )


class Judge(Semantics, Protocol):
    """Semantic judge that also knows the version of the prompts it asks with."""

    def version(self) -> str: ...


class Judges(Protocol):
    """Source of the semantic judge for a job, asked only when a stage really needs it."""

    def judge(self, job_id: int) -> Judge: ...


@final
class Postponing:
    """Judges whose judge is always the postponed one, until a real judge is connected."""

    __slots__ = ()

    def judge(self, _job_id: int) -> Judge:
        return Postponed()


@final
class Unconfigured:
    """Judges that fall back to the postponed judge when the primary ones cannot build theirs
    because the model gateway is not configured, so the reconciliation goes on."""

    __slots__ = ("_primary",)

    def __init__(self, primary: Judges) -> None:
        self._primary: Final = primary

    def judge(self, job_id: int) -> Judge:
        try:
            return self._primary.judge(job_id)
        except MisconfiguredError:
            return Postponed()


def signature(questions: tuple[Question, ...]) -> Signature:
    return tuple(
        (
            question.place().shipment(),
            question.place().field(),
            question.value(),
            question.rule(),
            question.clause().reference(),
            question.clause().text(),
        )
        for question in questions
    )


class Recording(Semantics, Protocol):
    """Semantic judge that remembers the batches of questions and postpones their answers."""

    def batches(self) -> tuple[tuple[Question, ...], ...]: ...


@final
class Deferring:
    """Recording that lets the checks by code finish, keeps what the cards ask the judge and
    answers every question with a postponed verdict."""

    __slots__ = ("_batches",)

    def __init__(self) -> None:
        self._batches: Final[list[tuple[Question, ...]]] = []

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        self._batches.append(questions)
        return Postponed().verdicts(questions)

    def batches(self) -> tuple[tuple[Question, ...], ...]:
        return tuple(self._batches)


@final
class Replaying:
    """Semantic judge that returns the answers already received to the same batches of
    questions; a batch it was given no answers for is an error."""

    __slots__ = ("_answers",)

    def __init__(self, answers: Mapping[Signature, tuple[Verdict, ...]]) -> None:
        self._answers: Final = answers

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        key = signature(questions)
        if key not in self._answers:
            raise LookupError("Карточка задала смысловые вопросы, на которые нет ответа")
        return self._answers[key]


@final
class Settled:
    """Card whose verdicts are already known, so that a report does not ask the judge again."""

    __slots__ = ("_card", "_verdicts")

    def __init__(self, card: Card, verdicts: tuple[Verdict, ...]) -> None:
        self._card: Final = card
        self._verdicts: Final = verdicts

    def field(self) -> str:
        return self._card.field()

    def covers(self, form: str) -> bool:
        return self._card.covers(form)

    def title(self, form: str) -> str:
        return self._card.title(form)

    def subject(self) -> str:
        return self._card.subject()

    def verdicts(self, _declaration: Filed, _policy: Policy) -> tuple[Verdict, ...]:
        return tuple(
            verdict for verdict in self._verdicts if verdict.place().field() == self._card.field()
        )


class Cardfile(Protocol):
    """Source of the reconciliation for a given semantic judge, so that each stage can serve the
    same cards with the judge it needs."""

    def reconciliation(self, semantics: Semantics) -> Reconciliation: ...


@final
class Folder:
    """Cardfile of the rule cards in a folder, read afresh for every reconciliation."""

    __slots__ = ("_folder",)

    def __init__(self, folder: Path) -> None:
        self._folder: Final = folder

    def reconciliation(self, semantics: Semantics) -> Reconciliation:
        return Carded(Cards(self._folder, semantics))


class Results(Protocol):
    """Verdicts of a declaration kept in the database; a new run replaces the previous ones, and
    only the attempt that owns the job may write."""

    async def replace(self, job: Snapshot, findings: Findings) -> None: ...

    async def stamp(self, job: Snapshot, versions: Versions, taken: Taken) -> None: ...

    async def prompts(self, job: Snapshot, version: str) -> None: ...


@final
class Tabled:
    """Results in the table of check results, replaced together with the counts of the places.

    Expert corrections live in their own table and are left alone.
    """

    __slots__ = ("_sessions",)

    def __init__(self, sessions: Sessions) -> None:
        self._sessions: Final = sessions

    async def replace(self, job: Snapshot, findings: Findings) -> None:
        async with self._sessions.session() as session:
            await Holding(session).owned(job)
            declaration = await session.get(Declaration, job.declaration())
            if declaration is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            await session.execute(
                delete(CheckResult).where(CheckResult.declaration_id == job.declaration())
            )
            session.add_all(
                CheckResult(
                    declaration_id=job.declaration(),
                    line=verdict.place().shipment(),
                    field=verdict.place().field(),
                    status=verdict.status().key(),
                    reason=verdict.reason().code()[:64],
                    clause=verdict.remark().reference()[:255],
                    comment=verdict.remark().comment(),
                    source=verdict.reason().source(),
                )
                for verdict in findings.verdicts()
            )
            declaration.places_expected = findings.expected()
            declaration.places_answered = len(findings.verdicts())
            await session.commit()

    async def stamp(self, job: Snapshot, versions: Versions, taken: Taken) -> None:
        async with self._sessions.session() as session:
            await Holding(session).owned(job)
            declaration = await session.get(Declaration, job.declaration())
            if declaration is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            declaration.code_version = versions.code()[:64]
            declaration.cards_version = versions.cards()[:64]
            declaration.profile_version = taken.version
            declaration.profile_status = taken.status
            declaration.model = versions.model()[:128]
            await session.commit()

    async def prompts(self, job: Snapshot, version: str) -> None:
        async with self._sessions.session() as session:
            await Holding(session).owned(job)
            declaration = await session.get(Declaration, job.declaration())
            if declaration is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            declaration.prompts_version = version[:64]
            await session.commit()


@final
@dataclass(frozen=True)
class Docket:
    """Cells where the stages of a check leave the declaration, its policy, the judge that
    recorded the questions, the verdicts and the profile the check was made by for the next
    stage."""

    declaration: Cell[Filed]
    policy: Cell[Policy]
    recording: Cell[Recording]
    verdicts: Cell[tuple[Verdict, ...]]
    taken: Cell[Taken]


@final
class Counted:
    """Count of verdicts by status, told in one Russian sentence for the journal."""

    __slots__ = ("_verdicts",)

    def __init__(self, verdicts: tuple[Verdict, ...]) -> None:
        self._verdicts: Final = verdicts

    def text(self) -> str:
        counts = Counter(verdict.status().key() for verdict in self._verdicts)
        return (
            f"совпадает {counts['match']}, не совпадает {counts['mismatch']}, "
            f"требует проверки {counts['review']}"
        )


@final
class Checking:
    """Stage that reads the declaration file once and checks every field by its rule card.

    Semantic questions are not answered here: they are recorded and postponed for the next stage.
    """

    __slots__ = ("_bench", "_docket", "_journal", "_parts", "_sessions")

    def __init__(
        self,
        bench: Bench,
        sessions: Sessions,
        parts: tuple[Standing, Cardfile, Results, Versions],
        docket: Docket,
        journal: Journal,
    ) -> None:
        self._bench: Final = bench
        self._sessions: Final = sessions
        self._parts: Final = parts
        self._docket: Final = docket
        self._journal: Final = journal

    def name(self) -> str:
        return "check"

    async def run(self, job: Snapshot) -> None:
        standing, cardfile, results, versions = self._parts
        started = time.perf_counter()
        declaration = await asyncio.to_thread(self._read, await self._key(job.declaration()))
        parsed = time.perf_counter() - started
        taken = await standing.taken(job.declaration(), declaration.policy())
        policy = taken.policy
        recording = Deferring()
        started = time.perf_counter()
        findings = await asyncio.to_thread(
            cardfile.reconciliation(recording).findings, declaration, policy
        )
        checked = time.perf_counter() - started
        await results.replace(job, findings)
        await results.stamp(job, versions, taken)
        self._docket.taken.put(taken)
        self._docket.declaration.put(declaration)
        self._docket.policy.put(policy)
        self._docket.recording.put(recording)
        self._docket.verdicts.put(findings.verdicts())
        self._journal.info(
            f"Декларация разобрана за {parsed:.3f} с, проверки кодом заняли {checked:.3f} с: "
            f"мест {len(findings.verdicts())} из {findings.expected()}, "
            f"{Counted(findings.verdicts()).text()}",
            job.id,
            job.declaration(),
        )

    async def _key(self, declaration_id: int) -> str:
        async with self._sessions.session() as session:
            row = await session.get(Declaration, declaration_id)
        if row is None:
            raise LookupError(f"Декларация {declaration_id} не найдена")
        return row.file_key

    def _read(self, key: str) -> Filed:
        path = self._bench.copy(key)
        try:
            read = Declared(Source(path))
            return Retained(
                read.number() or _UNNUMBERED, read.form(), read.policy(), read.shipments()
            )
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)


@final
class Judging:
    """Stage that gives the recorded semantic questions to the judge, one batch per card, in a
    pool of threads of its own, and then rebuilds the verdicts of the declaration with the answers.

    A declaration without semantic questions passes through without touching the judge. The pool
    is separate from the one that reads declarations, so slow model calls delay no other job.
    """

    __slots__ = ("_docket", "_journal", "_parts", "_pool")

    def __init__(
        self,
        parts: tuple[Cardfile, Results, Judges],
        pool: Executor,
        docket: Docket,
        journal: Journal,
    ) -> None:
        self._parts: Final = parts
        self._pool: Final = pool
        self._docket: Final = docket
        self._journal: Final = journal

    def name(self) -> str:
        return "semantic"

    async def run(self, job: Snapshot) -> None:
        cardfile, results, judges = self._parts
        semantics = judges.judge(job.id)
        await results.prompts(job, semantics.version())
        batches = self._docket.recording.get().batches()
        if not batches:
            self._journal.info(
                "Смысловых вопросов нет, модель не вызывалась", job.id, job.declaration()
            )
            return
        loop = asyncio.get_running_loop()
        replies = await asyncio.gather(
            *(loop.run_in_executor(self._pool, semantics.verdicts, batch) for batch in batches)
        )
        replaying = Replaying(
            {signature(batch): reply for batch, reply in zip(batches, replies, strict=True)}
        )
        findings = await asyncio.to_thread(
            cardfile.reconciliation(replaying).findings,
            self._docket.declaration.get(),
            self._docket.policy.get(),
        )
        await results.replace(job, findings)
        self._docket.verdicts.put(findings.verdicts())
        self._journal.info(
            f"Смысловых групп вопросов {len(batches)}, итог: {Counted(findings.verdicts()).text()}",
            job.id,
            job.declaration(),
        )
