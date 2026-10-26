from pathlib import Path

import openpyxl
from hamcrest import assert_that, contains_exactly, raises

from tools.eval.draft import Draft
from tools.eval.fields import Cards
from tools.eval.rulings import Rulings
from tools.eval.sheet import Workbooks


def test_draft_settles_plain_right_and_asks_about_the_rest(tmp_path: Path) -> None:
    (tmp_path / "97").mkdir()
    book = openpyxl.Workbook()
    sheet = book.create_sheet("Лист1", 0)
    sheet.append(("Номер", "Поле", "Пункт", "Результат", "Комментарий", "ФСЦ"))
    sheet.append(("97", "Страховая сумма", "Лимит", "не совпадает", "текст", "верно"))
    sheet.append(("97", "Груз", "п. 5", "совпадает", "текст", "почему соответствует?"))
    book.save(tmp_path / "97" / "97 – результат проверки.xlsx")
    assert_that(
        [
            entry.kind()
            for entry in Draft(
                Workbooks(tmp_path, ("97",)),
                Cards(
                    {"sum": {"vertical": "Страховая сумма"}, "cargo": {"vertical": "Груз"}},
                    {"forms": {"97": "vertical"}, "unmapped": {}},
                ),
                Rulings((), {}),
            ).entries()
        ],
        contains_exactly("gold", "question"),
        "Draft does not settle a plain right and ask about the rest",
    )


def test_draft_applies_ruling_to_its_row(tmp_path: Path) -> None:
    (tmp_path / "97").mkdir()
    book = openpyxl.Workbook()
    sheet = book.create_sheet("Лист1", 0)
    sheet.append(("Номер", "Поле", "Пункт", "Результат", "Комментарий", "ФСЦ"))
    sheet.append(("97", "Страховая сумма", "Лимит", "не совпадает", "текст", "Верно, но"))
    book.save(tmp_path / "97" / "97 – результат проверки.xlsx")
    assert_that(
        Draft(
            Workbooks(tmp_path, ("97",)),
            Cards(
                {"sum": {"vertical": "Страховая сумма"}},
                {"forms": {"97": "vertical"}, "unmapped": {}},
            ),
            Rulings(
                ({"shipment": "97", "field": "sum", "status": "mismatch", "basis": "D-23"},), {}
            ),
        )
        .entries()[0]
        .cells(),
        contains_exactly("97", "97", "sum", "mismatch", "D-23", ""),
        "Draft does not apply a ruling to its row",
    )


def test_draft_refuses_ruling_without_row(tmp_path: Path) -> None:
    (tmp_path / "97").mkdir()
    book = openpyxl.Workbook()
    sheet = book.create_sheet("Лист1", 0)
    sheet.append(("Номер", "Поле", "Пункт", "Результат", "Комментарий", "ФСЦ"))
    sheet.append(("97", "Страховая сумма", "Лимит", "не совпадает", "текст", "верно"))
    book.save(tmp_path / "97" / "97 – результат проверки.xlsx")
    assert_that(
        lambda: Draft(
            Workbooks(tmp_path, ("97",)),
            Cards(
                {"sum": {"vertical": "Страховая сумма"}},
                {"forms": {"97": "vertical"}, "unmapped": {}},
            ),
            Rulings(({"shipment": "97", "field": "cargo", "ask": "x"},), {}),
        ).entries(),
        raises(ValueError),
        "Draft does not refuse a ruling that matches no row",
    )
