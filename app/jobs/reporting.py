import asyncio
import re
import shutil
from typing import Final, final

from app.core.journal import Journal
from app.jobs.building import Bench
from app.jobs.checking import Cardfile, Docket, Postponed, Settled
from app.jobs.database import Sessions
from app.jobs.models import Declaration
from app.jobs.ownership import Holding
from app.jobs.queue import Snapshot
from app.reports.report import Report
from app.storage.disk import Storage
from app.storage.layout import Layout


@final
class Reporting:
    """Stage that writes the result workbook of the declaration to the storage and remembers
    its key in the declaration; the report takes the verdicts of the earlier stages as they are
    and never asks the semantic judge again."""

    __slots__ = ("_cardfile", "_docket", "_files", "_journal", "_sessions")

    def __init__(
        self,
        files: tuple[Bench, Storage, Layout],
        sessions: Sessions,
        cardfile: Cardfile,
        docket: Docket,
        journal: Journal,
    ) -> None:
        self._files: Final = files
        self._sessions: Final = sessions
        self._cardfile: Final = cardfile
        self._docket: Final = docket
        self._journal: Final = journal

    def name(self) -> str:
        return "report"

    async def run(self, job: Snapshot) -> None:
        declaration = self._docket.declaration.get()
        verdicts = self._docket.verdicts.get()
        report = Report(
            declaration,
            self._docket.policy.get(),
            tuple(
                Settled(card, verdicts)
                for card in self._cardfile.reconciliation(Postponed()).cards(declaration.form())
            ),
        )
        data = await asyncio.to_thread(self._saved, report)
        _, storage, layout = self._files
        key = layout.result(job.declaration(), re.sub(r'[\\/:*?"<>|]', "_", declaration.number()))
        async with self._sessions.session() as session:
            await Holding(session).owned(job)
            storage.save(key, data)
            row = await session.get(Declaration, job.declaration())
            if row is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена")
            if row.result_key and row.result_key != key:
                storage.remove(row.result_key)
            row.result_key = key
            await session.commit()
        self._journal.info(f"Файл результата записан, {len(data)} байт", job.id, job.declaration())

    def _saved(self, report: Report) -> bytes:
        folder = self._files[0].scratch()
        try:
            path = folder / report.name()
            report.save(path)
            return path.read_bytes()
        finally:
            shutil.rmtree(folder, ignore_errors=True)
