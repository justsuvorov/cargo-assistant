from pathlib import Path
from typing import Final, Protocol, final

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.declaration import Declaration
from app.domain.status import Match, Mismatch, Review
from tools.eval.fields import Forms

_WIDTHS = (14, 34, 46, 20, 18, 46, 13, 40)
_RULES = (
    "Разметка эталона: как заполнять",
    "",
    "Один файл — одна декларация. Строка — одна перевозка и одно поле формы ответа.",
    "1. Записывайте правильный ответ сами, по документам пакета полиса (ГП, ДС, особые условия, "
    "перечень перевозчиков), не глядя на ответ системы.",
    "2. «Ожидаемый статус» — один из трёх: совпадает, не совпадает, требует проверки.",
    "3. Для «не совпадает» обязательны «Пункт ГП / ДС» (например «п. 12 ГП», «п. 1 ДС 4») и "
    "«Причина».",
    "4. «Требует проверки» ставится, только если по документам пакета без дополнительных "
    "сведений решить нельзя; «Причина» обязательна.",
    "5. «Причина» — одно предложение: что именно не так или чего не хватает.",
    "6. «Уверенность»: уверен или спорно. Если правило сверки неясно — «спорно» и вопрос в "
    "«Примечании», а не догадка. Спорные строки не входят в расчёт точности, пока их не "
    "разрешат.",
    "7. Одинаковое значение в разных строках одной декларации получает одинаковый ответ.",
    "8. Принятые решения соблюдаются: например, сумма в валюте, отличной от валюты лимита, — "
    "«требует проверки» (D-22).",
    "9. Колонки «Номер декларации/строки» и «Наименование поля» не меняйте, строки не "
    "добавляйте и не удаляйте. «Значение в декларации» — как его прочитала система, только для "
    "справки; если оно прочитано неверно, напишите об этом в «Примечании».",
    "10. Запишите ниже время разметки этой декларации.",
    "",
    "Время разметки, минут:",
)


class Heading(Protocol):
    """Columns of the marking template: their titles in order and the levels of confidence."""

    def titles(self) -> tuple[str, ...]: ...

    def levels(self) -> dict[str, str]: ...


class Form(Protocol):
    """Marking template that FSC experts fill in for one declaration, written as a file."""

    def write(self, path: Path) -> None: ...


@final
class Columns:
    """Heading of the template after section 3 of the gold requirements."""

    __slots__ = ()

    def titles(self) -> tuple[str, ...]:
        return (
            "Номер декларации/строки",
            "Наименование поля",
            "Значение в декларации",
            "Ожидаемый статус",
            "Пункт ГП / ДС",
            "Причина",
            "Уверенность",
            "Примечание",
        )

    def levels(self) -> dict[str, str]:
        return {"уверен": "sure", "спорно": "disputed"}


@final
class Template:
    """Excel template in the shape of the result: one row per shipment and field of the form.

    The rows follow the form of the declaration (D-14) and the numbering of its shipments:
    «200» for a single shipment, «200/N» for several. The columns that the expert fills in are
    empty; status and confidence are chosen from lists. The second sheet is the instruction.
    """

    __slots__ = ("_declaration", "_forms")

    def __init__(self, declaration: Declaration, forms: Forms) -> None:
        self._declaration: Final = declaration
        self._forms: Final = forms

    def write(self, path: Path) -> None:
        book = openpyxl.Workbook()
        sheet = book.worksheets[0]
        sheet.title = "Разметка"
        sheet.append(Columns().titles())
        fields = self._forms.fields(self._declaration.form())
        for shipment in self._declaration.shipments():
            for key, title in fields:
                sheet.append((shipment.number(), title, shipment.field(key).text()))
        self._dress(sheet)
        rules = book.create_sheet("Инструкция")
        for line in _RULES:
            rules.append((line,))
        rules.column_dimensions["A"].width = 120
        rules.column_dimensions["B"].width = 20
        rules["A1"].font = Font(bold=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        book.save(path)

    def _dress(self, sheet: Worksheet) -> None:
        last = max(sheet.max_row, 2)
        for column, width in zip("ABCDEFGH", _WIDTHS, strict=True):
            sheet.column_dimensions[column].width = width
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                cell.number_format = "@"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for column, choices in (
            ("D", tuple(status.text() for status in (Match(), Mismatch(), Review()))),
            ("G", tuple(Columns().levels())),
        ):
            listed = DataValidation(
                type="list",
                formula1=f'"{",".join(choices)}"',
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="Недопустимое значение",
                error=f"Выберите одно из значений: {', '.join(choices)}",
            )
            sheet.add_data_validation(listed)
            listed.add(f"{column}2:{column}{last}")
