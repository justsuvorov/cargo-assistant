import asyncio
import re
import shutil
from pathlib import Path
from typing import Final, final

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font

from app.core.journal import Journal
from app.jobs.building import Bench
from app.jobs.checking import Cardfile, Docket, Postponed, Settled
from app.jobs.database import Sessions
from app.jobs.folios import Taken
from app.jobs.models import Declaration
from app.jobs.ownership import Holding
from app.jobs.queue import Snapshot
from app.reports.report import Report
from app.storage.disk import Storage
from app.storage.layout import Layout


@final
class Footnote:
    """Sheet of the result workbook that tells which profile of the policy the check was made
    by: confirmed by the owner, only a draft, or none; and the problems found in the package of
    the policy."""

    __slots__ = ("_taken",)

    def __init__(self, taken: Taken) -> None:
        self._taken: Final = taken

    def add(self, path: Path) -> None:
        book = load_workbook(path)
        sheet = book.create_sheet("Профиль полиса")
        sheet.append((self._headline(),))
        sheet["A1"].font = Font(bold=True)
        if self._taken.problems:
            sheet.append(("Проблемы пакета полиса",))
            for problem in self._taken.problems:
                sheet.append((problem,))
        sheet.column_dimensions["A"].width = 120
        for line in sheet.iter_rows():
            for cell in line:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        book.save(path)

    def _headline(self) -> str:
        taken = self._taken
        if taken.status == "approved":
            return f"Профиль полиса подтверждён, версия {taken.version}"
        if taken.status == "draft":
            return (
                f"Профиль полиса не подтверждён, проверка выполнена по черновику версии "
                f"{taken.version}"
            )
        return "Профиль полиса не собран, пункты полиса не проверены"


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
            self._docket.conditions.get(),
        )
        data = await asyncio.to_thread(self._saved, report, Footnote(self._docket.taken.get()))
        _, storage, layout = self._files
        async with self._sessions.session() as session:
            await Holding(session).owned(job)
            row = await session.get(Declaration, job.declaration())
            if row is None or row.workspace_id is None:
                raise LookupError(f"Декларация {job.declaration()} не найдена в сессии")
            key = layout.result(
                row.owner,
                row.workspace_id,
                row.id,
                re.sub(r'[\\/:*?"<>|]', "_", declaration.number()),
            )
            storage.save(key, data)
            if row.result_key and row.result_key != key:
                storage.remove(row.result_key)
            row.result_key = key
            await session.commit()
        self._journal.info(f"Файл результата записан, {len(data)} байт", job.id, job.declaration())

    def _saved(self, report: Report, footnote: Footnote) -> bytes:
        folder = self._files[0].scratch()
        try:
            path = folder / report.name()
            report.save(path)
            footnote.add(path)
            return path.read_bytes()
        finally:
            shutil.rmtree(folder, ignore_errors=True)
