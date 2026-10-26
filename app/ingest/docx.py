from pathlib import Path
from typing import Final, final

from docx import Document
from docx.table import _Cell

from app.ingest.book import Cell, Page, Series, Sheet, Written


@final
class Docx:
    """Book read from a docx file as one sheet: paragraphs first, then the rows of each table."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def sheets(self) -> tuple[Sheet, ...]:
        # @todo #2:30min Читать абзацы и таблицы docx в порядке документа, а не по группам
        document = Document(str(self._path))
        rows = tuple((Written(0, paragraph.text),) for paragraph in document.paragraphs) + tuple(
            self._row(row.cells) for table in document.tables for row in table.rows
        )
        return (
            Page(
                "document",
                tuple(Series(number, row) for number, row in enumerate(rows, start=1)),
            ),
        )

    def _row(self, cells: list[_Cell]) -> tuple[Cell, ...]:
        return tuple(
            Written(column, cell.text)
            for column, cell in enumerate(cells)
            if column == 0 or cell is not cells[column - 1]
        )
