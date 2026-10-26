from collections.abc import Callable
from pathlib import Path
from typing import Final, final

from xlrd import open_workbook
from xlrd.sheet import Cell as Sheetcell
from xlrd.sheet import Sheet as Worksheet

from app.ingest.book import Page, Series, Sheet, Written
from app.ingest.figure import Figure, Serial


@final
class Xls:
    """Book read from a legacy xls file; date cells become DD.MM.YYYY text."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def sheets(self) -> tuple[Sheet, ...]:
        book = open_workbook(str(self._path))
        return tuple(self._page(sheet, book.datemode) for sheet in book.sheets())

    def _page(self, sheet: Worksheet, mode: int) -> Sheet:
        return Page(
            sheet.name,
            tuple(
                Series(
                    number,
                    tuple(
                        Written(column, self._text(cell, mode))
                        for column, cell in enumerate(sheet.row(number - 1))
                    ),
                )
                for number in range(1, sheet.nrows + 1)
            ),
        )

    def _text(self, cell: Sheetcell, mode: int) -> str:
        kinds: dict[int, Callable[[], str]] = {
            1: lambda: str(cell.value),
            2: lambda: Figure(cell.value).text(),
            3: lambda: Serial(float(cell.value), mode).text(),
        }
        return kinds.get(cell.ctype, lambda: "")()
