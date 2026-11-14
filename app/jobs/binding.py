import asyncio
import shutil
from dataclasses import dataclass
from typing import Final, final

from app.core.journal import Journal
from app.declarations.declared import Declared
from app.domain.errors import UnreadableError
from app.domain.shipment import Shipment
from app.ingest.source import Source
from app.jobs.building import Bench
from app.jobs.database import Sessions
from app.jobs.models import Declaration, Workspace
from app.jobs.queue import Snapshot


@final
@dataclass(frozen=True)
class Facts:
    """What one reading of a declaration file gives: its number, form, rows and month."""

    number: str
    form: str
    shipments: int
    month: str


@final
class Ingesting:
    """Stage that reads the declaration file once and writes its number, form, rows and month."""

    __slots__ = ("_bench", "_journal", "_sessions")

    def __init__(self, bench: Bench, sessions: Sessions, journal: Journal) -> None:
        self._bench: Final = bench
        self._sessions: Final = sessions
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
    """Stage that links the declaration to the policy of its session, which is the policy of the
    folder the declaration lies in; there is nothing to look for, and the number of the policy
    that the declaration cites is checked by the card of the policy field."""

    __slots__ = ("_journal", "_sessions")

    def __init__(self, sessions: Sessions, journal: Journal) -> None:
        self._sessions: Final = sessions
        self._journal: Final = journal

    def name(self) -> str:
        return "bind"

    async def run(self, job: Snapshot) -> None:
        async with self._sessions.session() as session:
            declaration = await session.get(Declaration, job.declaration())
            if declaration is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            workspace = (
                await session.get(Workspace, declaration.workspace_id)
                if declaration.workspace_id is not None
                else None
            )
            if workspace is None or workspace.policy_id is None:
                raise LookupError(f"У декларации {job.declaration()} нет сессии с полисом")
            declaration.policy_id = workspace.policy_id
            declaration.binding = "bound"
            await session.commit()
        self._journal.info("Декларация привязана к полису своей папки", job.id, job.declaration())
