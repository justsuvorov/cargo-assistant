import uuid
from pathlib import Path

import openpyxl
from hamcrest import assert_that, equal_to, has_length, raises

from tools.eval.sheet import Line, Workbooks


def test_workbooks_read_rows_with_shipment_number(tmp_path: Path) -> None:
    (tmp_path / "97").mkdir()
    book = openpyxl.Workbook()
    sheet = book.create_sheet("Лист1", 0)
    sheet.append(("Номер", "Поле", "Пункт", "Результат", "Комментарий", "ФСЦ"))
    sheet.append(("97", "Страховая сумма", "Лимит", "не совпадает", "текст", "верно"))
    sheet.append((None, None, None, None, None, None))
    sheet.append(("97", "Транспорт", "п. 8", "совпадает", "текст", None))
    book.save(tmp_path / "97" / "97 – результат проверки.xlsx")
    assert_that(
        Workbooks(tmp_path, ("97",)).lines(),
        has_length(2),
        "Workbooks do not read exactly the rows with a shipment number",
    )


def test_workbooks_keep_remark_of_unnamed_column(tmp_path: Path) -> None:
    (tmp_path / "164").mkdir()
    book = openpyxl.Workbook()
    sheet = book.create_sheet("Лист1", 0)
    sheet.append(("Номер", "Поле", "Пункт", "Результат", "Комментарий", None))
    sheet.append(("164", "Страхователь", "Страхователь", "совпадает", "текст", "верно"))
    book.save(tmp_path / "164" / "164 – результат проверки.xlsx")
    assert_that(
        Workbooks(tmp_path, ("164",)).lines()[0].remark(),
        equal_to("верно"),
        "Workbooks do not keep a remark from a column without a title",
    )


def test_workbooks_refuse_folder_without_workbook(tmp_path: Path) -> None:
    (tmp_path / "35").mkdir()
    assert_that(
        lambda: Workbooks(tmp_path, ("35",)).lines(),
        raises(FileNotFoundError),
        "Workbooks do not refuse a folder without a result workbook",
    )


def test_line_turns_mvp_status_into_key() -> None:
    assert_that(
        Line("97", ("97", "Сумма", "", " Не совпадает ", "", "")).answer(),
        equal_to("mismatch"),
        "Line does not turn the MVP status into a key",
    )


def test_line_refuses_unknown_mvp_status() -> None:
    assert_that(
        lambda: Line("97", ("97", "Сумма", "", uuid.uuid4().hex, "", "")).answer(),
        raises(ValueError),
        "Line does not refuse an unknown MVP status",
    )


def test_line_joins_label_lines_written_with_escape() -> None:
    assert_that(
        Line("114", ("114/4", "Маршрут\\nПункт  отправления", "", "", "", "")).label(),
        equal_to("Маршрут Пункт отправления"),
        "Line does not join label lines written with an escaped line break",
    )


def test_line_squeezes_spaces_of_remark() -> None:
    assert_that(
        Line("97", ("97", "", "", "", "", " верно \n")).remark(),
        equal_to("верно"),
        "Line does not squeeze spaces of a remark",
    )
