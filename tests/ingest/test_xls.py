import random
import string
from datetime import datetime
from pathlib import Path

import xlwt
from hamcrest import assert_that, contains_exactly, equal_to

from app.ingest.xls import Xls


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_reads_text_numbers_and_dates_of_a_row(tmp_path: Path) -> None:
    word = _word()
    whole = random.randint(1, 10**6)
    book = xlwt.Workbook()
    sheet = book.add_sheet("data")
    sheet.write(0, 0, word)
    sheet.write(0, 1, float(whole))
    sheet.write(0, 2, datetime(2026, 9, 21), xlwt.easyxf(num_format_str="DD.MM.YYYY"))
    book.save(str(tmp_path / "a.xls"))
    assert_that(
        tuple(cell.text() for cell in Xls(tmp_path / "a.xls").sheets()[0].lines()[0].cells()),
        contains_exactly(word, str(whole), "21.09.2026"),
        "Xls does not read text, number and date of a row as text",
    )


def test_keeps_columns_and_row_numbers_of_filled_cells(tmp_path: Path) -> None:
    word = _word()
    book = xlwt.Workbook()
    book.add_sheet("data").write(4, 3, word)
    book.save(str(tmp_path / "a.xls"))
    line = Xls(tmp_path / "a.xls").sheets()[0].lines()[0]
    assert_that(
        (line.number(), line.text(3)),
        equal_to((5, word)),
        "Xls does not keep the row number and the column of a filled cell",
    )


def test_returns_every_sheet_with_its_name(tmp_path: Path) -> None:
    first, second = _word(), _word()
    book = xlwt.Workbook()
    book.add_sheet(first).write(0, 0, _word())
    book.add_sheet(second).write(0, 0, _word())
    book.save(str(tmp_path / "a.xls"))
    assert_that(
        tuple(sheet.name() for sheet in Xls(tmp_path / "a.xls").sheets()),
        contains_exactly(first, second),
        "Xls does not return every sheet with its name",
    )
