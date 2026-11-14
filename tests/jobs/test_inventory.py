import random
import string
from pathlib import Path

from hamcrest import assert_that, equal_to
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.jobs.inventory import Inventory


def word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def put(root: Path, name: str, data: bytes | None = None) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else random.randbytes(8))


def test_lists_declarations_of_nested_folders_without_policy_files(tmp_path: Path) -> None:
    for name in (
        "ГП.docx",
        "ДС/ДС 1/ДС 1.docx",
        "ДС/Приложение к ДС.xls",
        "Особые условия/условия.docx",
        "Декларации/Июнь/508.xls",
        "Декларации/Июнь/511.xlsx",
        "Декларации/Июль/600.docx",
        "Декларации/Июнь/~$511.xlsx",
        "Декларации/Июнь/заметки.txt",
        "корень.xlsx",
    ):
        put(tmp_path, name)
    assert_that(
        Inventory(tmp_path).declarations(),
        equal_to(
            ("Декларации/Июль/600.docx", "Декларации/Июнь/508.xls", "Декларации/Июнь/511.xlsx")
        ),
        "Inventory does not list exactly the declarations outside the files of the policy",
    )


def test_ignores_declarations_when_signing_the_policy_files(tmp_path: Path) -> None:
    put(tmp_path, "ГП.docx", b"policy")
    before = Inventory(tmp_path).signature()
    put(tmp_path, "Декларации/a.xlsx")
    assert_that(
        Inventory(tmp_path).signature(),
        equal_to(before),
        "A declaration does not leave the signature of the policy files unchanged",
    )


def test_changes_signature_when_an_addendum_changes(tmp_path: Path) -> None:
    put(tmp_path, "ГП.docx", b"policy")
    put(tmp_path, "ДС/ДС 1.docx", b"one")
    before = Inventory(tmp_path).signature()
    put(tmp_path, "ДС/ДС 1.docx", b"two")
    assert_that(
        Inventory(tmp_path).signature() != before,
        equal_to(True),
        "Signature does not change after an addendum changed",
    )


def test_keeps_signature_for_the_same_files_in_another_folder(tmp_path: Path) -> None:
    data = {"ГП.docx": random.randbytes(8), "ДС/ДС 1.docx": random.randbytes(8)}
    for name, content in data.items():
        put(tmp_path / "one", name, content)
        put(tmp_path / "two" / "other", name, content)
    assert_that(
        Inventory(tmp_path / "one").signature(),
        equal_to(Inventory(tmp_path / "two" / "other").signature()),
        "Signature of the same files does not stay the same in another folder",
    )


def test_tells_a_file_moved_from_policy_to_addenda_by_signature(tmp_path: Path) -> None:
    put(tmp_path / "one", "ГП.docx", b"same")
    put(tmp_path / "two", "ДС/ГП.docx", b"same")
    assert_that(
        Inventory(tmp_path / "one").signature() != Inventory(tmp_path / "two").signature(),
        equal_to(True),
        "Signature does not tell a policy from an addendum",
    )


def declaration(path: Path) -> None:
    def put_cells(sheet: Worksheet, row: int, cells: dict[int, str]) -> None:
        for column, value in cells.items():
            sheet.cell(row=row, column=column + 1, value=value)

    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.create_sheet("Декларация")
    put_cells(sheet, 1, {5: "Приложение № 2 к Генеральному Полису"})
    put_cells(sheet, 2, {7: "№ AB123 от 26.08.2026 г."})
    put_cells(sheet, 4, {7: "От ООО «Тест»"})
    put_cells(sheet, 8, {0: "Декларация", 3: f"№ Р-{random.randint(100, 999)}", 4: "об отгрузке"})
    put_cells(sheet, 16, {1: "1.", 2: "Полное наименование груза", 6: "мясо, сыр"})
    put_cells(sheet, 20, {1: "4.", 2: "Страховая сумма", 6: "1000", 8: "рублей"})
    put_cells(sheet, 21, {1: "5.", 2: "Транспорт", 6: "Авто"})
    put_cells(sheet, 22, {1: "6.", 2: "Пункт отправления", 6: "г. Первый"})
    put_cells(sheet, 24, {1: "8.", 2: "Пункт назначения", 6: "г. Второй"})
    put_cells(sheet, 25, {1: "9.", 2: "Период страхования", 6: "01.09.2026", 7: "по", 8: "30.12.2026"})
    book.save(path)


def test_lists_declaration_lying_in_the_folder_of_addenda(tmp_path: Path) -> None:
    put(tmp_path, "ГП.docx", b"policy")
    put(tmp_path, "ДС/ДС 1.docx", b"one")
    put(tmp_path, "ДС/Приложение к ДС.xls", b"not a declaration")
    declaration(tmp_path / "ДС" / "Приложение № 1.xlsx")
    assert_that(
        Inventory(tmp_path).declarations(),
        equal_to(("ДС/Приложение № 1.xlsx",)),
        "Inventory does not list a declaration by its content from the folder of addenda",
    )


def test_keeps_signature_when_a_declaration_lies_in_the_folder_of_addenda(tmp_path: Path) -> None:
    put(tmp_path, "ГП.docx", b"policy")
    before = Inventory(tmp_path).signature()
    declaration(tmp_path / "ДС" / "Приложение.xlsx")
    assert_that(
        Inventory(tmp_path).signature(),
        equal_to(before),
        "A declaration of the folder of addenda does not leave the signature unchanged",
    )
