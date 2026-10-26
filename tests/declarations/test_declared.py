import random
import string
import time
from datetime import date, datetime
from pathlib import Path

import xlwt
from docx import Document
from hamcrest import assert_that, contains_exactly, equal_to, raises
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.declarations.declared import Declared
from app.domain.errors import UnreadableError
from app.ingest.source import Source

_KEYS = (
    "insurer",
    "policy",
    "cargo",
    "packaging",
    "beneficiary",
    "sum",
    "transport",
    "departure",
    "transshipment",
    "destination",
    "period",
    "period_start",
    "period_end",
    "document",
    "document_number",
    "document_date",
    "carrier",
    "sealing",
    "other",
)


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def _put(sheet: Worksheet, row: int, cells: dict[int, str | float | datetime]) -> None:
    for column, value in cells.items():
        sheet.cell(row=row, column=column + 1, value=value)


def _vertical(sheet: Worksheet, start: datetime | str) -> None:
    _put(sheet, 1, {5: "Приложение № 2 к Генеральному Полису"})
    _put(sheet, 2, {7: "№ 0000T00GR0000 от 26.08.2026 г."})
    _put(sheet, 4, {7: "От ООО «Тест»"})
    _put(sheet, 8, {0: "Декларация", 3: "№ Р-005", 4: "об отгрузке"})
    _put(sheet, 16, {1: "1.", 2: "Полное наименование груза", 6: "мясо, сыр"})
    _put(sheet, 17, {1: "2.", 2: "Род упаковки", 6: "коробки"})
    _put(sheet, 19, {1: "3.", 2: "Выгодоприобретатель", 6: "ООО «Получатель»"})
    _put(sheet, 20, {1: "4.", 2: "Страховая сумма", 6: 7492870, 8: "рублей"})
    _put(sheet, 21, {1: "5.", 2: "Транспорт", 6: "Авто"})
    _put(sheet, 22, {1: "6.", 2: "Пункт отправления", 6: "г. Первый"})
    _put(sheet, 24, {1: "8.", 2: "Пункт назначения", 6: "г. Второй"})
    _put(sheet, 25, {1: "9.", 2: "Период страхования", 6: start, 7: "по", 8: "30.09.2026"})
    _put(sheet, 26, {1: "10.", 2: "Товарно-транспортная накладная №", 6: "13444-2/Р"})


def _table(sheet: Worksheet, rows: tuple[dict[int, str | float | datetime], ...]) -> None:
    _put(sheet, 1, {9: "Приложение № 1 к Генеральному полису"})
    _put(sheet, 2, {9: "№ 0000T00GR0000 от 26.08.2026 г."})
    _put(sheet, 7, {0: "Декларация №", 4: 35, 5: "перевозок начавшихся", 9: "14.09.2026"})
    _put(sheet, 10, {0: "Страхователь", 3: "ООО «Тест»"})
    _put(
        sheet,
        13,
        {
            0: "№ п/п",
            1: "Период страхования",
            3: "Наименование груза",
            12: "Страховая сумма",
            13: "Валюта",
        },
    )
    _put(sheet, 14, {1: "начало", 2: "окончание"})
    for number, row in enumerate(rows, start=15):
        _put(sheet, number, row)


def _row(number: int, start: str | datetime) -> dict[int, str | float | datetime]:
    return {
        0: number,
        1: start,
        2: "30.09.2026",
        3: _word(),
        12: random.randint(1, 10**6),
        13: "рублей",
    }


def test_reads_number_form_policy_and_shipment_of_a_vertical_file(tmp_path: Path) -> None:
    book = Workbook()
    _vertical(book.create_sheet("Декларация"), datetime(2026, 9, 21))
    book.save(tmp_path / "a.xlsx")
    declared = Declared(Source(tmp_path / "a.xlsx"))
    assert_that(
        (declared.number(), declared.form(), declared.policy(), len(declared.shipments())),
        equal_to(("Р-005", "vertical", "0000T00GR0000", 1)),
        "Declared does not read the number, form, policy and the only shipment of a vertical file",
    )


def test_single_shipment_is_numbered_like_the_declaration(tmp_path: Path) -> None:
    book = Workbook()
    _table(book.create_sheet("Декларация"), (_row(1, datetime(2026, 9, 14)),))
    book.save(tmp_path / "a.xlsx")
    shipment = Declared(Source(tmp_path / "a.xlsx")).shipments()[0]
    assert_that(
        (shipment.number(), shipment.declaration()),
        equal_to(("35", "35")),
        "Declared does not number a single shipment of a table form like its declaration",
    )


def test_several_shipments_are_numbered_by_their_row_number(tmp_path: Path) -> None:
    book = Workbook()
    _table(
        book.create_sheet("Декларация"),
        (_row(1, "14.09.2026"), _row(2, "14.09.2026"), _row(7, "14.09.2026")),
    )
    book.save(tmp_path / "a.xlsx")
    assert_that(
        tuple(shipment.number() for shipment in Declared(Source(tmp_path / "a.xlsx")).shipments()),
        contains_exactly("35/1", "35/2", "35/7"),
        "Declared does not number several shipments as the declaration slash the row number",
    )


def test_picks_the_declaration_sheet_among_policy_sheets(tmp_path: Path) -> None:
    book = Workbook()
    policy = book.create_sheet("Полис")
    _put(policy, 10, {0: "1.", 1: "Страхователь"})
    _put(policy, 12, {0: "2.", 1: "Выгодоприобретатель", 4: "ООО «Получатель»"})
    _put(policy, 29, {0: "11.", 1: "Страховая сумма", 4: "100 евро"})
    _vertical(book.create_sheet("декларация"), datetime(2026, 9, 21))
    _put(book.create_sheet("Счет на полис"), 2, {1: "Получатель", 6: "Сч. №"})
    book.save(tmp_path / "a.xlsx")
    assert_that(
        Declared(Source(tmp_path / "a.xlsx")).number(),
        equal_to("Р-005"),
        "Declared does not pick the declaration sheet among the policy sheets",
    )


def test_refuses_a_file_without_a_declaration_sheet(tmp_path: Path) -> None:
    book = Workbook()
    _put(book.create_sheet("Счет на полис"), 2, {1: "Получатель", 6: "Сч. №"})
    book.save(tmp_path / "a.xlsx")
    assert_that(
        lambda: Declared(Source(tmp_path / "a.xlsx")).number(),
        raises(UnreadableError, "не найден лист с декларацией"),
        "Declared does not refuse a file without a declaration sheet",
    )


def test_refuses_the_start_of_a_shipment_without_a_readable_date(tmp_path: Path) -> None:
    book = Workbook()
    _table(book.create_sheet("Декларация"), (_row(1, "скоро"),))
    book.save(tmp_path / "a.xlsx")
    assert_that(
        Declared(Source(tmp_path / "a.xlsx")).shipments()[0].start,
        raises(UnreadableError, "дата начала"),
        "Declared does not refuse the start of a shipment without a readable date",
    )


def test_reads_the_start_of_a_shipment_from_the_period(tmp_path: Path) -> None:
    book = Workbook()
    _vertical(book.create_sheet("Декларация"), "21.09.2026")
    book.save(tmp_path / "a.xlsx")
    assert_that(
        Declared(Source(tmp_path / "a.xlsx")).shipments()[0].start(),
        equal_to(date(2026, 9, 21)),
        "Declared does not read the start of a shipment from its period",
    )


def test_reads_a_legacy_xls_file_with_date_cells(tmp_path: Path) -> None:
    book = xlwt.Workbook()
    sheet = book.add_sheet("Декларация")
    style = xlwt.easyxf(num_format_str="DD.MM.YYYY")
    for row, column, value in (
        (0, 9, "№ 0000T00GR0000 от 26.08.2026 г."),
        (6, 0, "Декларация №"),
        (6, 4, 12),
        (12, 0, "№ п/п"),
        (12, 1, "Период страхования"),
        (12, 3, "Наименование груза"),
        (13, 1, "начало"),
        (13, 2, "окончание"),
        (13, 12, "Страховая сумма"),
        (13, 13, "Валюта"),
    ):
        sheet.write(row, column, value)
    sheet.write(14, 0, 1.0)
    sheet.write(14, 1, datetime(2026, 9, 21), style)
    sheet.write(14, 2, datetime(2026, 9, 25), style)
    sheet.write(14, 3, "Мясо")
    sheet.write(14, 12, 1500.5)
    sheet.write(14, 13, "евро")
    book.save(str(tmp_path / "a.xls"))
    shipment = Declared(Source(tmp_path / "a.xls")).shipments()[0]
    assert_that(
        (
            shipment.number(),
            shipment.start(),
            shipment.field("period_end").dates(),
            shipment.field("sum").amounts()[0].text(),
        ),
        equal_to(("12", date(2026, 9, 21), (date(2026, 9, 25),), "1 500,50 EUR")),
        "Declared does not read a legacy xls file with date cells",
    )


def test_reads_a_vertical_declaration_from_docx_tables(tmp_path: Path) -> None:
    document = Document()
    document.add_paragraph("Декларация № 77 об отгрузке")
    document.add_paragraph("№ 0000T00GR0000 от 26.08.2026 г.")
    rows = (
        ("1.", "Полное наименование груза", "мясо"),
        ("4.", "Страховая сумма", "1000"),
        ("5.", "Транспорт", "Авто"),
        ("6.", "Пункт отправления", "г. Первый"),
        ("8.", "Пункт назначения", "г. Второй"),
        ("9.", "Период страхования", "21.09.2026"),
        ("11.", "Перевозчик", "ООО «Перевозчик»"),
    )
    table = document.add_table(rows=len(rows), cols=3)
    for row, texts in enumerate(rows):
        for column, text in enumerate(texts):
            table.cell(row, column).text = text
    document.save(str(tmp_path / "a.docx"))
    declared = Declared(Source(tmp_path / "a.docx"))
    assert_that(
        (declared.number(), declared.form(), declared.shipments()[0].start()),
        equal_to(("77", "vertical", date(2026, 9, 21))),
        "Declared does not read a vertical declaration from docx tables",
    )


def test_parses_a_declaration_of_sixty_one_rows_in_less_than_a_second(tmp_path: Path) -> None:
    book = Workbook()
    _table(
        book.create_sheet("Декларация"),
        tuple(_row(number, "14.09.2026") for number in range(1, 62)),
    )
    book.save(tmp_path / "a.xlsx")
    begin = time.perf_counter()
    shipments = Declared(Source(tmp_path / "a.xlsx")).shipments()
    for shipment in shipments:
        shipment.start()
        for key in _KEYS:
            shipment.field(key).entries()
            shipment.field(key).dates()
            shipment.field(key).amounts()
    assert_that(
        len(shipments) == 61 and time.perf_counter() - begin < 1.0,
        equal_to(True),
        "Parsing of a declaration of sixty one rows is not faster than one second",
    )
