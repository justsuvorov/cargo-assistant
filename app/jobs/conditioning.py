import asyncio
import time
from typing import Final, Protocol, final

from app.core.journal import Journal
from app.domain.declaration import Declaration as Filed
from app.jobs.building import Cell
from app.jobs.database import Sessions
from app.jobs.folios import Taken
from app.jobs.models import Declaration, Workspace
from app.jobs.ownership import Holding
from app.jobs.queue import Snapshot
from app.policy.conditions import ClientFile, Condition, Joined, SpecialConditions
from app.policy.outcome import Outcome

_FIRST = "выше"
_USUAL = "обычный"


class Found(Protocol):
    """Special conditions found for one declaration, told as the sheet of the report, the notes
    of the prompt and the record kept with the declaration."""

    def rows(self) -> tuple[tuple[str, str, str], ...]: ...

    def problems(self) -> tuple[str, ...]: ...

    def notes(self) -> tuple[str, ...]: ...

    def table(self) -> list[list[str]]: ...


@final
class Listed:
    """Outcome of the lookup of special conditions with the reasons that came from reading the
    file of the client; a condition of the client file has the priority «выше»."""

    __slots__ = ("_outcome", "_problems")

    def __init__(self, outcome: Outcome[Condition], problems: tuple[str, ...]) -> None:
        self._outcome: Final = outcome
        self._problems: Final = problems

    def rows(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(
            (item.text(), item.source(), _FIRST if item.prevails() else _USUAL)
            for item in self._outcome.items()
        )

    def problems(self) -> tuple[str, ...]:
        return self._outcome.problems() + self._problems

    def notes(self) -> tuple[str, ...]:
        return tuple(
            f"{text} (источник: {source}; приоритет: {priority})"
            for text, source, priority in self.rows()
        )

    def table(self) -> list[list[str]]:
        return [list(row) for row in self.rows()]


@final
class Lines:
    """Lines of the special conditions file of the client as they were read when the session
    was opened."""

    __slots__ = ("_lines",)

    def __init__(self, lines: tuple[str, ...]) -> None:
        self._lines: Final = lines

    def conditions(self) -> tuple[str, ...]:
        return self._lines


@final
class Conditioning:
    """Stage that looks for the special conditions of the declaration once: in the file of the
    client of its session and in the shared file of the insurer, by the number of the policy and
    the insurant of its profile, and by those of the declaration when the profile lacks them.

    The conditions are kept with the declaration and left to the next stages, the semantic
    judge and the report. They change no status of a field.
    """

    __slots__ = ("_docket", "_journal", "_sessions", "_shared")

    def __init__(
        self,
        sessions: Sessions,
        shared: SpecialConditions,
        docket: tuple[Cell[Filed], Cell[Taken], Cell[Found]],
        journal: Journal,
    ) -> None:
        self._sessions: Final = sessions
        self._shared: Final = shared
        self._docket: Final = docket
        self._journal: Final = journal

    def name(self) -> str:
        return "conditions"

    async def run(self, job: Snapshot) -> None:
        declaration, taken, found = self._docket
        lines, problems = await self._client(job.declaration())
        number = taken.get().policy.number() or declaration.get().policy()
        who = taken.get().insurer or next(
            (row.field("insurer").text() for row in declaration.get().shipments()), ""
        )
        started = time.perf_counter()
        listed = Listed(
            await asyncio.to_thread(
                Joined((ClientFile(Lines(lines)), self._shared)).find,
                number,
                who,
            ),
            problems,
        )
        spent = time.perf_counter() - started
        async with self._sessions.session() as session:
            await Holding(session).owned(job)
            row = await session.get(Declaration, job.declaration())
            if row is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            row.conditions = listed.table()
            row.conditions_problems = list(listed.problems())
            await session.commit()
        # @todo #45:60min Подключить найденные условия к accepted.<поле> карточек после решения П-35; статусы полей они пока не меняют
        found.put(listed)
        self._journal.info(
            f"Особые условия найдены за {spent:.3f} с: условий {len(listed.rows())}, "
            f"причин без условий {len(listed.problems())}",
            job.id,
            job.declaration(),
        )

    async def _client(self, declaration_id: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
        async with self._sessions.session() as session:
            row = await session.get(Declaration, declaration_id)
            workspace = (
                await session.get(Workspace, row.workspace_id)
                if row is not None and row.workspace_id is not None
                else None
            )
        return (
            (tuple(workspace.client_lines), tuple(workspace.client_problems))
            if workspace is not None
            else ((), ("сессия декларации не найдена, файл особых условий клиента не прочитан",))
        )
