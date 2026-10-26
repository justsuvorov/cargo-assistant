import re
from itertools import takewhile
from typing import Final, final

from app.declarations.fields import Dating
from app.declarations.header import Title
from app.declarations.layout import Record
from app.declarations.row import Row
from app.declarations.schema import Fields
from app.declarations.terms import ColumnTerms, Terms
from app.ingest.book import Line, Sheet

type _Origin = tuple[int, int]
_BAND = 4
_KEYS = 5


@final
class Psg:
    """Table declaration: one shipment per numbered row, columns found by their RU or EN labels."""

    __slots__ = ("_sheet",)

    def __init__(self, sheet: Sheet) -> None:
        self._sheet: Final = sheet

    def form(self) -> str:
        return "psg"

    def score(self) -> int:
        return len(self._columns(self._origin()))

    def number(self) -> str:
        return Title(self._sheet).number()

    def policy(self) -> str:
        return Title(self._sheet).policy()

    def records(self) -> tuple[Record, ...]:
        origin = self._origin()
        columns = self._columns(origin)
        common = {
            "policy": (Title(self._sheet).citation(),),
            "insurer": self._insurer(origin),
        }
        return tuple(
            Row(
                line.text(origin[1]),
                {**self._texts(line, columns), **common},
                Fields(),
                Dating((line.text(columns.get("period_start", -1)),)),
            )
            for line in self._sheet.lines()[origin[0] + 1 :]
            if re.fullmatch(r"\d+", line.text(origin[1]))
        )

    def _origin(self) -> _Origin:
        candidates = (
            (index, cell.column())
            for index, line in enumerate(self._sheet.lines())
            for cell in line.cells()
            if ColumnTerms().key(cell.text()) == "number" and not re.search(r"\d", cell.text())
        )
        return next((each for each in candidates if len(self._columns(each)) >= _KEYS), (-1, -1))

    def _columns(self, origin: _Origin) -> dict[str, int]:
        columns: dict[str, int] = {}
        for line in self._band(origin):
            for cell in line.cells():
                key = ColumnTerms().key(cell.text())
                if key and key not in columns:
                    columns[key] = cell.column()
        return columns

    def _band(self, origin: _Origin) -> tuple[Line, ...]:
        index, column = origin
        return tuple(
            takewhile(
                lambda line: not re.fullmatch(r"\d+", line.text(column)),
                self._sheet.lines()[index : index + _BAND] if index >= 0 else (),
            )
        )

    def _texts(self, line: Line, columns: dict[str, int]) -> dict[str, tuple[str, ...]]:
        texts = {key: (line.text(column),) for key, column in columns.items()}
        value = line.text(columns.get("sum", -1))
        return {**texts, "sum": (value, line.text(columns.get("currency", -1))) if value else ()}

    def _insurer(self, origin: _Origin) -> tuple[str, ...]:
        terms = Terms({"insurer": ("страхователь", "insurer", "policyholder")})
        return next(
            (
                (line.after(cell.column())[0],)
                for line in self._sheet.lines()[: max(origin[0], 0)]
                for cell in line.cells()[:1]
                if terms.key(cell.text()) and line.after(cell.column())
            ),
            (),
        )
