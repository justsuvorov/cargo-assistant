import random
from pathlib import Path

import openpyxl
from hamcrest import assert_that, equal_to, raises

from tools.eval.shelf import Catalog, Shelf


def _declaration(path: Path, number: str) -> None:
    book = openpyxl.Workbook()
    sheet = book.worksheets[0]
    head: dict[tuple[int, int], str | int] = {
        (8, 1): "Декларация №",
        (8, 5): number,
        (14, 1): "№ п/п",
        (14, 4): "Наименование груза",
        (14, 13): "Страховая сумма",
        (14, 14): "Валюта",
        (15, 2): "начало",
        (15, 3): "окончание",
        (16, 1): 1,
        (16, 2): "14.09.2026",
    }
    for (row, column), value in head.items():
        sheet.cell(row=row, column=column, value=value)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def test_catalog_finds_file_by_digits_of_number(tmp_path: Path) -> None:
    path = tmp_path / "a.xlsx"
    assert_that(
        Catalog(tmp_path, {"70": (path,)}, ()).path("070"),
        equal_to(path),
        "Catalog does not find a file by the digits of the declaration number",
    )


def test_catalog_refuses_two_files_of_one_number(tmp_path: Path) -> None:
    assert_that(
        lambda: Catalog(tmp_path, {"5": (tmp_path / "a.xls", tmp_path / "b.xls")}, ()).path("5"),
        raises(LookupError),
        "Catalog does not refuse a number that two files claim",
    )


def test_catalog_names_unread_files_of_missing_declaration(tmp_path: Path) -> None:
    assert_that(
        lambda: Catalog(tmp_path, {}, ("broken.xls (формат)",)).path("97"),
        raises(LookupError, "broken.xls"),
        "Catalog does not name the unread files when a declaration is missing",
    )


def test_shelf_indexes_files_by_number_in_header(tmp_path: Path) -> None:
    number = random.randint(10, 999)
    _declaration(tmp_path / "folder" / "copy.xlsx", f"Р-0{number}")
    assert_that(
        Shelf(tmp_path).catalog().path(str(number)).name,
        equal_to("copy.xlsx"),
        "Shelf does not index a file by the number in its header",
    )


def test_shelf_skips_result_sheets(tmp_path: Path) -> None:
    _declaration(tmp_path / "35 – результат проверки.xlsx", "35")
    assert_that(
        lambda: Shelf(tmp_path).catalog().path("35"),
        raises(LookupError),
        "Shelf does not skip result sheets of the old MVP",
    )


def test_shelf_refuses_missing_folder(tmp_path: Path) -> None:
    assert_that(
        lambda: Shelf(tmp_path / "absent").catalog(),
        raises(FileNotFoundError, "EVAL_REAL_DIR"),
        "Shelf does not refuse a missing folder with a hint about the variable",
    )
