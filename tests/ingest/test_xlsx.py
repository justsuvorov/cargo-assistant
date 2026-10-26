import random
import string
from datetime import datetime
from pathlib import Path

from hamcrest import assert_that, contains_exactly, equal_to
from openpyxl import Workbook

from app.ingest.xlsx import Xlsx


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_reads_text_numbers_and_dates_of_a_row(tmp_path: Path) -> None:
    word = _word()
    whole = random.randint(1, 10**6)
    book = Workbook()
    book.create_sheet("data").append([word, float(whole), datetime(2026, 9, 21)])
    book.save(tmp_path / "a.xlsx")
    assert_that(
        tuple(cell.text() for cell in Xlsx(tmp_path / "a.xlsx").sheets()[-1].lines()[0].cells()),
        contains_exactly(word, str(whole), "21.09.2026"),
        "Xlsx does not read text, number and date of a row as text",
    )


def test_keeps_columns_of_cells_after_an_empty_cell(tmp_path: Path) -> None:
    word = _word()
    book = Workbook()
    book.create_sheet("data").append(["", "", word])
    book.save(tmp_path / "a.xlsx")
    assert_that(
        Xlsx(tmp_path / "a.xlsx").sheets()[-1].lines()[0].text(2),
        equal_to(word),
        "Xlsx does not keep the column of a cell that follows empty cells",
    )


def test_returns_every_sheet_with_its_name(tmp_path: Path) -> None:
    first, second = _word(), _word()
    book = Workbook()
    book.create_sheet(first).append([_word()])
    book.create_sheet(second).append([_word()])
    book.save(tmp_path / "a.xlsx")
    assert_that(
        tuple(sheet.name() for sheet in Xlsx(tmp_path / "a.xlsx").sheets())[-2:],
        contains_exactly(first, second),
        "Xlsx does not return every sheet with its name",
    )
