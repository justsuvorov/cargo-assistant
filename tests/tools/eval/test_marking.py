import uuid
from pathlib import Path

import openpyxl
from hamcrest import assert_that, contains_exactly, contains_string, empty, equal_to, raises

from tools.eval.marking import Additions, Broken, Marked, Markings
from tools.eval.mask import Anonymity


def _cells(status: str, clause: str, reason: str, confidence: str) -> dict[str, str]:
    return {
        "Номер декларации/строки": "113/2",
        "Наименование поля": "Страховая сумма",
        "Значение в декларации": "100 000",
        "Ожидаемый статус": status,
        "Пункт ГП / ДС": clause,
        "Причина": reason,
        "Уверенность": confidence,
        "Примечание": "",
    }


def _book(path: Path, rows: tuple[tuple[str, ...], ...]) -> None:
    book = openpyxl.Workbook()
    sheet = book.worksheets[0]
    sheet.title = "Разметка"
    sheet.append(
        (
            "Номер декларации/строки",
            "Наименование поля",
            "Значение в декларации",
            "Ожидаемый статус",
            "Пункт ГП / ДС",
            "Причина",
            "Уверенность",
            "Примечание",
        )
    )
    for row in rows:
        sheet.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def test_marked_row_with_full_grounds_has_no_problems() -> None:
    assert_that(
        Marked(
            "a.xlsx, строка 2",
            _cells("Не совпадает", "п. 12 ГП", "Сумма выше лимита", "уверен"),
            {"Страховая сумма": "sum"},
        ).problems(),
        empty(),
        "Marked row with a clause and a reason for a mismatch does not pass",
    )


def test_marked_row_refuses_status_outside_three() -> None:
    assert_that(
        Marked(
            "a.xlsx, строка 2", _cells("верно", "", "", "уверен"), {"Страховая сумма": "sum"}
        ).problems(),
        contains_exactly(
            "a.xlsx, строка 2: статус «верно» не из трёх: совпадает, не совпадает, требует проверки"
        ),
        "Marked row does not refuse a status outside the three statuses",
    )


def test_marked_mismatch_needs_clause() -> None:
    assert_that(
        Marked(
            "a.xlsx, строка 4",
            _cells("не совпадает", "", "Сумма выше лимита", "уверен"),
            {"Страховая сумма": "sum"},
        ).problems(),
        contains_exactly("a.xlsx, строка 4: для «не совпадает» не указан пункт ГП / ДС"),
        "Marked mismatch does not ask for a clause of the policy",
    )


def test_marked_review_needs_reason() -> None:
    assert_that(
        Marked(
            "a.xlsx, строка 3",
            _cells("требует проверки", "", "", "спорно"),
            {"Страховая сумма": "sum"},
        ).problems(),
        contains_exactly("a.xlsx, строка 3: для «требует проверки» не указана причина"),
        "Marked review does not ask for a reason",
    )


def test_marked_row_needs_confidence() -> None:
    assert_that(
        Marked(
            "a.xlsx, строка 5", _cells("совпадает", "", "", ""), {"Страховая сумма": "sum"}
        ).problems(),
        contains_exactly("a.xlsx, строка 5: не указана уверенность"),
        "Marked row does not ask for the confidence of the expert",
    )


def test_marked_row_refuses_field_outside_form() -> None:
    assert_that(
        Marked("a.xlsx, строка 2", _cells("совпадает", "", "", "уверен"), {}).problems(),
        contains_exactly("a.xlsx, строка 2: поле «Страховая сумма» не из формы ответа"),
        "Marked row does not refuse a field label outside the form",
    )


def test_marked_row_gives_gold_cells() -> None:
    assert_that(
        Marked(
            "a.xlsx, строка 2",
            _cells("Требует  проверки", "", "Валюта другая", "Спорно"),
            {"Страховая сумма": "sum"},
        ).cells(),
        equal_to(
            ("113", "113/2", "sum", "review", "disputed", "fsc-expert", "", "Валюта другая", "")
        ),
        "Marked row does not give the cells of a gold line",
    )


def test_broken_file_refuses_to_give_cells() -> None:
    assert_that(
        lambda: Broken("a.xlsx", "нет колонок").cells(),
        raises(ValueError),
        "Broken file does not refuse to give gold cells",
    )


def test_markings_list_every_mistake_instead_of_stopping(tmp_path: Path) -> None:
    _book(
        tmp_path / "35.xlsx",
        (
            ("35", "Страховая сумма", "1", "так себе", "", "", "уверен", ""),
            ("35", "Наименование груза", "мебель", "не совпадает", "", "", "уверен", ""),
        ),
    )
    assert_that(
        len(
            Markings(tmp_path, {"Страховая сумма": "sum", "Наименование груза": "cargo"}).problems()
        ),
        equal_to(3),
        "Markings do not list every mistake of the files",
    )


def test_markings_report_file_without_columns(tmp_path: Path) -> None:
    book = openpyxl.Workbook()
    book.worksheets[0].append(("Номер", "Поле"))
    book.save(tmp_path / "x.xlsx")
    assert_that(
        Markings(tmp_path, {}).problems()[0],
        contains_string("x.xlsx: нет колонок"),
        "Markings do not report a file without the columns of the template",
    )


def test_markings_report_place_marked_twice(tmp_path: Path) -> None:
    _book(
        tmp_path / "35.xlsx",
        (
            ("35/1", "Страховая сумма", "1", "совпадает", "", "", "уверен", ""),
            ("035/1", "Страховая сумма", "1", "совпадает", "", "", "уверен", ""),
        ),
    )
    assert_that(
        Markings(tmp_path, {"Страховая сумма": "sum"}).problems(),
        contains_exactly("35.xlsx, строка 2; 35.xlsx, строка 3: место 35/1 × sum размечено 2 раза"),
        "Markings do not report a place marked twice",
    )


def test_markings_report_equal_values_with_different_statuses(tmp_path: Path) -> None:
    _book(
        tmp_path / "35.xlsx",
        (
            ("35/1", "Наименование груза", "Мебель", "совпадает", "", "", "уверен", ""),
            ("35/2", "Наименование груза", "мебель ", "не совпадает", "п. 5", "Нет", "уверен", ""),
        ),
    )
    assert_that(
        Markings(tmp_path, {"Наименование груза": "cargo"}).problems()[0],
        contains_string("расхождение"),
        "Markings do not report equal values of one field with different statuses",
    )


def test_markings_let_disputed_rows_differ(tmp_path: Path) -> None:
    _book(
        tmp_path / "35.xlsx",
        (
            ("35/1", "Наименование груза", "мебель", "совпадает", "", "", "уверен", ""),
            (
                "35/2",
                "Наименование груза",
                "мебель",
                "требует проверки",
                "",
                "Неясно",
                "спорно",
                "",
            ),
        ),
    )
    assert_that(
        Markings(tmp_path, {"Наименование груза": "cargo"}).problems(),
        empty(),
        "Markings do not let a disputed row differ from a sure one",
    )


def test_markings_refuse_folder_without_files(tmp_path: Path) -> None:
    assert_that(
        lambda: Markings(tmp_path, {}).answers(),
        raises(FileNotFoundError),
        "Markings do not refuse a folder without marking files",
    )


def test_additions_mask_reason(tmp_path: Path) -> None:
    name = f"ООО «{uuid.uuid4().hex}»"
    _book(
        tmp_path / "in" / "35.xlsx",
        (("35", "Страховая сумма", "1", "требует проверки", "", f"Спросить {name}", "уверен", ""),),
    )
    answers = Markings(tmp_path / "in", {"Страховая сумма": "sum"}).answers()
    Additions(tmp_path / "gold", Anonymity((), ())).write(answers)
    assert_that(
        name in (tmp_path / "gold" / "35.csv").read_text(encoding="utf-8"),
        equal_to(False),
        "Additions do not mask a company name in a reason",
    )


def test_additions_refuse_declaration_already_in_gold(tmp_path: Path) -> None:
    _book(
        tmp_path / "in" / "70.xlsx",
        (("070", "Страховая сумма", "1", "совпадает", "", "", "уверен", ""),),
    )
    (tmp_path / "gold").mkdir()
    (tmp_path / "gold" / "70.csv").write_text("declaration\n", encoding="utf-8")
    answers = Markings(tmp_path / "in", {"Страховая сумма": "sum"}).answers()
    assert_that(
        lambda: Additions(tmp_path / "gold", Anonymity((), ())).write(answers),
        raises(FileExistsError),
        "Additions do not refuse a declaration that the gold already has",
    )
