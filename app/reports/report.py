import re
from pathlib import Path
from typing import Final, Protocol, final

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.card import Card
from app.domain.declaration import Declaration
from app.domain.place import Spot
from app.domain.policy import Policy
from app.domain.verdict import Verdict
from app.reports.errors import ReportError

_HEADER = (
    "Номер декларации/строки",
    "Наименование поля в декларации",
    "С каким пунктом Ген. полиса сверено",
    "Результат проверки\n(совпадает/не совпадает)",
    "Комментарий по сверке",
)
_WIDTHS = (25, 50, 60, 25, 60)
_COLORS = {"match": "FFD6F0D6", "mismatch": "FFF0D6D6", "review": "FFFFF3CD"}
_STATUS = 4


class Result(Protocol):
    """Result file of the check of one declaration, in the layout of the answer form."""

    def name(self) -> str: ...

    def save(self, path: Path) -> None: ...


@final
class Report:
    """Result workbook: a row per shipment and per card of the declaration form, in the
    order of the cards, coloured by status, and a second sheet with the special conditions
    of the policy.

    Every card must give exactly one verdict per shipment, otherwise the report fails.
    """

    __slots__ = ("_cards", "_declaration", "_policy")

    def __init__(self, declaration: Declaration, policy: Policy, cards: tuple[Card, ...]) -> None:
        self._declaration: Final = declaration
        self._policy: Final = policy
        self._cards: Final = cards

    def name(self) -> str:
        number = re.sub(r'[\\/:*?"<>|]', "_", self._declaration.number())
        return f"{number} – результат проверки.xlsx"

    def save(self, path: Path) -> None:
        book = Workbook()
        book.remove(book.worksheets[0])
        self._result(book.create_sheet("Результат проверки"))
        conditions: Worksheet = book.create_sheet("Особые условия")
        conditions.append(("Особые условия",))
        for condition in self._policy.conditions():
            conditions.append((condition,))
        conditions.column_dimensions["A"].width = 120
        book.save(path)

    def _result(self, sheet: Worksheet) -> None:
        sheet.append(_HEADER)
        for index, width in enumerate(_WIDTHS):
            sheet.column_dimensions["ABCDE"[index]].width = width
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row, (card, verdict) in enumerate(self._rows(), start=2):
            sheet.append(
                (
                    verdict.place().shipment(),
                    card.title(self._declaration.form()),
                    card.subject(),
                    verdict.status().text(),
                    verdict.remark().comment(),
                )
            )
            sheet.cell(row, _STATUS).fill = PatternFill(
                "solid", fgColor=_COLORS[verdict.status().key()]
            )
        for line in sheet.iter_rows():
            for cell in line:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "A2"

    def _rows(self) -> tuple[tuple[Card, Verdict], ...]:
        form = self._declaration.form()
        chosen = tuple(card for card in self._cards if card.covers(form))
        if not chosen:
            raise ReportError(f"Ни одна карточка не относится к форме {form} декларации")
        verdicts = {card.field(): card.verdicts(self._declaration, self._policy) for card in chosen}
        return tuple(
            (card, self._one(verdicts[card.field()], shipment.number(), card.field()))
            for shipment in self._declaration.shipments()
            for card in chosen
        )

    def _one(self, verdicts: tuple[Verdict, ...], shipment: str, field: str) -> Verdict:
        found = tuple(
            verdict for verdict in verdicts if verdict.place().same(Spot(shipment, field))
        )
        if len(found) != 1:
            raise ReportError(
                f"Карточка {field} дала {len(found)} результатов "
                f"для строки {shipment}, а нужен один"
            )
        return found[0]
