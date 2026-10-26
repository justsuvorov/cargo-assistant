from pathlib import Path
from typing import Final, Protocol, final

import openpyxl


class Mark(Protocol):
    """One row of an MVP answer that FSC experts marked as right or commented on."""

    def declaration(self) -> str: ...

    def shipment(self) -> str: ...

    def label(self) -> str: ...

    def answer(self) -> str: ...

    def remark(self) -> str: ...


class Marks(Protocol):
    """Rows of MVP answers marked by FSC experts, in the order of the source sheets."""

    def lines(self) -> tuple[Mark, ...]: ...


@final
class Line:
    """Row of an MVP result sheet: shipment, label, clause, status, comment and FSC remark."""

    __slots__ = ("_cells", "_declaration")

    def __init__(self, declaration: str, cells: tuple[str, ...]) -> None:
        self._declaration: Final = declaration
        self._cells: Final = cells

    def declaration(self) -> str:
        return self._declaration

    def shipment(self) -> str:
        return self._cells[0].strip()

    def label(self) -> str:
        return " ".join(self._cells[1].replace("\\n", "\n").split())

    def answer(self) -> str:
        words = {"совпадает": "match", "не совпадает": "mismatch"}
        status = " ".join(self._cells[3].lower().split())
        if status not in words:
            raise ValueError(
                f"Статус MVP «{status}» в строке {self.shipment()} декларации "
                f"{self._declaration} не распознан"
            )
        return words[status]

    def remark(self) -> str:
        return " ".join(self._cells[5].split())


@final
class Workbooks:
    """FSC-marked MVP answers, one «результат проверки» workbook per declaration folder."""

    __slots__ = ("_declarations", "_root")

    def __init__(self, root: Path, declarations: tuple[str, ...]) -> None:
        self._root: Final = root
        self._declarations: Final = declarations

    def lines(self) -> tuple[Mark, ...]:
        return tuple(
            Line(declaration, row)
            for declaration in self._declarations
            for row in self._rows(declaration)
        )

    def _rows(self, declaration: str) -> tuple[tuple[str, ...], ...]:
        books = sorted((self._root / declaration).glob("*результат проверки.xlsx"))
        if len(books) != 1:
            raise FileNotFoundError(
                f"В папке {self._root / declaration} ожидается один файл «результат проверки», "
                f"найдено {len(books)}"
            )
        sheet = openpyxl.load_workbook(books[0], data_only=True).worksheets[0]
        return tuple(
            tuple("" if cell is None else str(cell) for cell in (*row, *([None] * 6))[:6])
            for row in sheet.iter_rows(min_row=2, values_only=True)
            if row and row[0] is not None
        )
