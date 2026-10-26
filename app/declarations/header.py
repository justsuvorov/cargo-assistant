import re
from typing import Final, Protocol, final

from app.domain.errors import UnreadableError
from app.ingest.book import Sheet

_TITLE = re.compile(
    r"(?:декларац\w*|declaration)\D*?(?:№|\bno\b\.?|\bn°|#)\s*([\w\-/]*\d[\w\-/]*)",
    re.IGNORECASE,
)
_POLICY = re.compile(
    r"(?:№|\bno\b\.?)?\s*([^\s№]*\d[^\s]*)\s+(?:от|dated|from)\s+\d{1,2}[./]\d{1,2}[./]\d{2,4}",
    re.IGNORECASE,
)


class Header(Protocol):
    """Facts of the top of a declaration sheet: its number and the policy it cites."""

    def number(self) -> str: ...

    def policy(self) -> str: ...

    def citation(self) -> str: ...


@final
class Title:
    """Header read from the sheet text: the number is taken from the title, not the file name."""

    __slots__ = ("_sheet",)

    def __init__(self, sheet: Sheet) -> None:
        self._sheet: Final = sheet

    def number(self) -> str:
        found = tuple(
            match[1]
            for line in self._sheet.lines()
            if (match := _TITLE.search(" ".join(cell.text() for cell in line.cells())))
        )
        if not found:
            raise UnreadableError(f"В шапке листа {self._sheet.name()} не найден номер декларации")
        # @todo #2:30min Решить с пользователем, отбрасывать ли префикс «Р-» в номере «Р-005» (D-21)
        return found[0]

    def policy(self) -> str:
        found = self._found()
        return found[0][1] if found else ""

    def citation(self) -> str:
        found = self._found()
        return found[0][0] if found else ""

    def _found(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (cell.text(), match[1])
            for line in self._sheet.lines()
            for cell in line.cells()
            if (match := _POLICY.search(cell.text()))
        )
