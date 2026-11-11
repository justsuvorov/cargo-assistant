import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, final

from sqlalchemy import select

from app.core.journal import Journal
from app.declarations.declared import Declared
from app.domain.errors import UnreadableError
from app.domain.shipment import Shipment
from app.ingest.source import Source
from app.jobs.building import Bench, Cell
from app.jobs.database import Sessions
from app.jobs.models import Declaration, Policy
from app.jobs.queue import Snapshot
from app.rules.schema.card import spec


@final
@dataclass(frozen=True)
class Facts:
    """What one reading of a declaration file gives: its number, form, rows, month and the
    number of the general policy it cites."""

    number: str
    form: str
    shipments: int
    month: str
    policy: str


class Numbers(Protocol):
    """Comparison of numbers of the general policy as the card of the policy field compares them."""

    def blank(self, declared: str) -> bool: ...

    def same(self, declared: str, number: str) -> bool: ...


@final
class Numbering:
    """Numbers compared character by character without spaces and without the characters that
    the card of the policy field lists in its parameters; the card is read at every question,
    so a changed card applies without a restart."""

    __slots__ = ("_cards",)

    def __init__(self, cards: Path) -> None:
        self._cards: Final = cards

    def blank(self, declared: str) -> bool:
        return not self._stripped(declared).strip()

    def same(self, declared: str, number: str) -> bool:
        words = self._stripped(declared).split()
        wanted = re.sub(r"\s", "", self._stripped(number))
        return bool(wanted) and wanted in {
            "".join(words[start:end])
            for start in range(len(words))
            for end in range(start + 1, len(words) + 1)
        }

    def _stripped(self, text: str) -> str:
        ignore = spec(self._cards / "policy.yaml").params.ignore
        return "".join(" " if char in ignore else char for char in text)


class Outcome(Protocol):
    """Result of looking for the policy of a declaration, written to the declaration."""

    def code(self) -> str: ...

    def apply(self, declaration: Declaration) -> None: ...


@final
class Bound:
    """Outcome where exactly one policy of the group has the number."""

    __slots__ = ("_policy",)

    def __init__(self, policy: int) -> None:
        self._policy: Final = policy

    def code(self) -> str:
        return "bound"

    def apply(self, declaration: Declaration) -> None:
        declaration.policy_id = self._policy
        declaration.binding = self.code()


@final
class Unbound:
    """Outcome where the declaration goes on without a policy, for the reason of the code."""

    __slots__ = ("_code",)

    def __init__(self, code: str) -> None:
        self._code: Final = code

    def code(self) -> str:
        return self._code

    def apply(self, declaration: Declaration) -> None:
        declaration.policy_id = None
        declaration.binding = self._code


class Registry(Protocol):
    """Policies among which a declaration finds the one it cites."""

    async def find(self, group: str, declared: str) -> Outcome: ...


@final
class Matching:
    """Registry in the database that looks only at the policies of the access group."""

    __slots__ = ("_numbers", "_sessions")

    def __init__(self, sessions: Sessions, numbers: Numbers) -> None:
        self._sessions: Final = sessions
        self._numbers: Final = numbers

    async def find(self, group: str, declared: str) -> Outcome:
        if not declared.strip():
            return Unbound("policy_missing")
        if self._numbers.blank(declared):
            return Unbound("policy_unreadable")
        async with self._sessions.session() as session:
            rows = (
                await session.execute(
                    select(Policy.id, Policy.number).where(Policy.access_group == group)
                )
            ).all()
        found = [
            policy for policy, number in rows if number and self._numbers.same(declared, number)
        ]
        if not found:
            return Unbound("policy_unknown")
        if len(found) > 1:
            return Unbound("policy_ambiguous")
        return Bound(found[0])


@final
class Ingesting:
    """Stage that reads the declaration file once and writes its number, form, rows and month;
    the number of the policy it cites is left for the stage that binds."""

    __slots__ = ("_bench", "_journal", "_policy", "_sessions")

    def __init__(
        self, bench: Bench, sessions: Sessions, policy: Cell[str], journal: Journal
    ) -> None:
        self._bench: Final = bench
        self._sessions: Final = sessions
        self._policy: Final = policy
        self._journal: Final = journal

    def name(self) -> str:
        return "ingest"

    async def run(self, job: Snapshot) -> None:
        async with self._sessions.session() as session:
            declaration = await session.get(Declaration, job.declaration())
            if declaration is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            facts = await asyncio.to_thread(self._read, declaration.file_key)
            declaration.number = facts.number[:64]
            declaration.form = facts.form
            declaration.shipments = facts.shipments
            declaration.month = facts.month
            await session.commit()
        self._policy.put(facts.policy)
        self._journal.info(
            f"Декларация прочитана: форма {facts.form}, строк {facts.shipments}",
            job.id,
            job.declaration(),
        )
        if not facts.month:
            self._journal.warning(
                "Месяц декларации не определён, потому что дата начала перевозки не читается",
                job.id,
                job.declaration(),
            )

    def _read(self, key: str) -> Facts:
        path = self._bench.copy(key)
        try:
            declared = Declared(Source(path))
            shipments = declared.shipments()
            return Facts(
                declared.number(),
                declared.form(),
                len(shipments),
                self._month(shipments[0]),
                declared.policy(),
            )
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def _month(self, shipment: Shipment) -> str:
        try:
            return f"{shipment.start():%Y-%m}"
        except UnreadableError:
            return ""


@final
class Binding:
    """Stage that links the declaration to the policy of its group by the number of the policy;
    when there is none or there are several, the declaration goes on without a policy and the
    reason is written to the journal and to the declaration."""

    __slots__ = ("_journal", "_policy", "_registry", "_sessions")

    def __init__(
        self, registry: Registry, sessions: Sessions, policy: Cell[str], journal: Journal
    ) -> None:
        self._registry: Final = registry
        self._sessions: Final = sessions
        self._policy: Final = policy
        self._journal: Final = journal

    def name(self) -> str:
        return "bind"

    async def run(self, job: Snapshot) -> None:
        async with self._sessions.session() as session:
            declaration = await session.get(Declaration, job.declaration())
            if declaration is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            outcome = await self._registry.find(declaration.access_group, self._policy.get())
            outcome.apply(declaration)
            await session.commit()
        if outcome.code() == "bound":
            self._journal.info("Декларация привязана к полису", job.id, job.declaration())
        else:
            self._journal.warning(
                f"Декларация не привязана к полису, причина {outcome.code()}",
                job.id,
                job.declaration(),
            )
