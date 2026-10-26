from pathlib import Path
from typing import Final, final

from openpyxl import load_workbook
from openpyxl.cell import Cell as Sheetcell
from openpyxl.cell import MergedCell
from openpyxl.worksheet.worksheet import Worksheet

from app.ingest.book import Page, Series, Sheet, Written
from app.ingest.figure import Day, Figure


@final
class Xlsx:
    """Book read from an xlsx file with cached values of formulas."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def sheets(self) -> tuple[Sheet, ...]:
        book = load_workbook(self._path, data_only=True)
        return tuple(self._page(sheet) for sheet in book.worksheets)

    def _page(self, sheet: Worksheet) -> Sheet:
        return Page(
            sheet.title,
            tuple(
                Series(
                    number,
                    tuple(Written(column, self._text(cell)) for column, cell in enumerate(row)),
                )
                for number, row in enumerate(sheet.iter_rows(), start=1)
            ),
        )

    def _text(self, cell: Sheetcell | MergedCell) -> str:
        value = cell.value or ""
        return {
            "n": lambda: Figure(value).text(),
            "d": lambda: Day(str(value)).text(),
        }.get(cell.data_type, lambda: str(value))()
