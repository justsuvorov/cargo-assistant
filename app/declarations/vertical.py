import re
from itertools import takewhile
from typing import Final, final

from app.declarations.fields import Dating
from app.declarations.header import Title
from app.declarations.layout import Record
from app.declarations.row import Row
from app.declarations.schema import Fields
from app.declarations.terms import VerticalTerms
from app.ingest.book import Line, Sheet

_LINK = r"от|по|до|from|to|until|dated"


@final
class Vertical:
    """Vertical declaration: one shipment whose fields are numbered lines of label and value."""

    __slots__ = ("_sheet",)

    def __init__(self, sheet: Sheet) -> None:
        self._sheet: Final = sheet

    def form(self) -> str:
        return "vertical"

    def score(self) -> int:
        return len(self._found())

    def number(self) -> str:
        return Title(self._sheet).number()

    def policy(self) -> str:
        return Title(self._sheet).policy()

    def records(self) -> tuple[Record, ...]:
        found = self._found()
        texts = {
            **found,
            "policy": (Title(self._sheet).citation(),),
            "insurer": self._insurer(),
        }
        return (Row("1", texts, Fields(), Dating(found.get("period", ())[:1])),)

    def _found(self) -> dict[str, tuple[str, ...]]:
        found: dict[str, tuple[str, ...]] = {}
        for line in self._sheet.lines():
            key, column = self._label(line)
            if key and key not in found:
                found[key] = tuple(
                    text for text in line.after(column) if not re.fullmatch(_LINK, text, re.I)
                )
        return found

    def _label(self, line: Line) -> tuple[str, int]:
        cells = line.cells()
        skip = 1 if cells and re.fullmatch(r"\d+\.?", cells[0].text()) else 0
        return next(
            ((VerticalTerms().key(cell.text()), cell.column()) for cell in cells[skip : skip + 1]),
            ("", -1),
        )

    def _insurer(self) -> tuple[str, ...]:
        head = takewhile(lambda line: not self._label(line)[0], self._sheet.lines())
        return next(
            (
                (found[1],)
                for line in head
                for cell in line.cells()
                if (found := re.fullmatch(r"(?:от|from)\s+(.+)", cell.text(), re.I | re.S))
            ),
            (),
        )
