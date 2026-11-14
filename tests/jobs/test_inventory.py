import random
import string
from pathlib import Path

from hamcrest import assert_that, equal_to

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
        "A declaration changes the signature of the policy files",
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
        "Signature depends on the place of the folder",
    )


def test_tells_a_file_moved_from_policy_to_addenda_by_signature(tmp_path: Path) -> None:
    put(tmp_path / "one", "ГП.docx", b"same")
    put(tmp_path / "two", "ДС/ГП.docx", b"same")
    assert_that(
        Inventory(tmp_path / "one").signature() != Inventory(tmp_path / "two").signature(),
        equal_to(True),
        "Signature does not tell a policy from an addendum",
    )
