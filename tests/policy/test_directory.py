from datetime import date
from pathlib import Path

from docx import Document
from hamcrest import assert_that, contains_exactly, equal_to, raises

from app.domain.errors import UnreadableError
from app.policy.directory import Directory


def _write(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(str(path))


def _policy(path: Path) -> None:
    _write(path, "Генеральный полис № 9X13GR0001 страхования грузов", "г. Город", "Условия")


def _agreement(
    path: Path, number: int, effective: str = "27.11.2020", declarations: str = ""
) -> None:
    _write(
        path,
        f"Дополнительное соглашение № 9X13GR0001-D{number:05d}",
        "к Генеральному полису страхования грузов № 9X13GR0001 от 20.10.20217 г.",
        "г. Город\t\t«26» ноября 2020 г.",
        declarations or "Пункт 6 принять в следующей редакции:",
        f"Настоящее Дополнительное соглашение вступает в силу с {effective} г.",
    )


def test_reads_policy_lying_directly_in_the_folder(tmp_path: Path) -> None:
    _policy(tmp_path / "ГП полис.docx")
    _write(tmp_path / "Приложение 3.docx", "Приложение № 3 к Генеральному полису № 9X13GR0001")
    assert_that(
        Directory(tmp_path).package().policy().reference(),
        equal_to("ГП полис.docx"),
        "Directory does not read the policy that lies directly in the policy folder",
    )


def test_reads_policy_from_subfolder_gp(tmp_path: Path) -> None:
    _policy(tmp_path / "ГП" / "polis.docx")
    assert_that(
        Directory(tmp_path).package().policy().reference(),
        equal_to("ГП/polis.docx"),
        "Directory does not read the policy from the subfolder GP",
    )


def test_reads_amendments_with_scope_from_nested_folders(tmp_path: Path) -> None:
    _policy(tmp_path / "p.docx")
    _agreement(
        tmp_path / "ДС" / "ДС 2 (к декл 5)" / "x.docx",
        2,
        declarations="по декларации № 5 об отгрузке:",
    )
    _agreement(tmp_path / "ДС" / "ДС 1" / "inner" / "y.docx", 1, effective="01.02.2021")
    package = Directory(tmp_path).package()
    assert_that(
        [(item.number(), item.effective(), item.scope()) for item in package.amendments()],
        contains_exactly((1, date(2021, 2, 1), ()), (2, date(2020, 11, 27), ("5",))),
        "Directory does not read the number, entry into force and scope of nested amendments",
    )


def test_reads_special_conditions_and_carriers(tmp_path: Path) -> None:
    _policy(tmp_path / "p.docx")
    (tmp_path / "Особые условия").mkdir()
    (tmp_path / "Особые условия" / "o.txt").write_text("Условие 1\nУсловие 2", encoding="cp1251")
    (tmp_path / "Перевозчики").mkdir()
    (tmp_path / "Перевозчики" / "c.txt").write_text("Перевозчик 1", encoding="utf-8")
    package = Directory(tmp_path).package()
    assert_that(
        (package.conditions(), package.carriers()),
        equal_to((("Условие 1", "Условие 2"), ("Перевозчик 1",))),
        "Directory does not read special conditions and carriers by lines",
    )


def test_collects_problems_of_all_parts_in_one_list(tmp_path: Path) -> None:
    _policy(tmp_path / "p.docx")
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 1)
    _write(
        tmp_path / "ДС" / "2" / "d.docx",
        "Дополнительное соглашение № 9X13GR0001-D00002",
        "к Генеральному полису № 9X13GR0001",
        "г. Город\t\t«   »   2026 г.",
        "Настоящее Дополнительное соглашение вступает в силу с   .  .2026 г.",
    )
    (tmp_path / "Перевозчики").mkdir()
    (tmp_path / "Перевозчики" / "c.pdf").write_bytes(b"%PDF")
    assert_that(
        len(Directory(tmp_path).package().problems()),
        equal_to(2),
        "Directory does not collect the problems of amendments and carriers in one list",
    )


def test_refuses_folder_without_policy_text(tmp_path: Path) -> None:
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 1)
    assert_that(
        lambda: Directory(tmp_path).package(),
        raises(UnreadableError, "не найден текст Генерального полиса"),
        "Directory does not refuse a folder where the policy text is missing",
    )


def test_refuses_missing_folder(tmp_path: Path) -> None:
    assert_that(
        lambda: Directory(tmp_path / "absent").package(),
        raises(UnreadableError, "не найдена"),
        "Directory does not refuse a folder that is missing",
    )


def test_reads_every_amendment_of_a_package(tmp_path: Path) -> None:
    _policy(tmp_path / "p.docx")
    for number in range(1, 9):
        _agreement(tmp_path / "ДС" / f"ДС {number}" / f"{number}.docx", number)
    assert_that(
        sorted(item.number() for item in Directory(tmp_path).package().amendments()),
        equal_to(list(range(1, 9))),
        "Directory does not read every amendment of a package",
    )


def test_reads_english_policy_and_amendment(tmp_path: Path) -> None:
    _write(tmp_path / "p.docx", "General Cargo Policy No. 9X13GR0001", "Terms")
    _write(
        tmp_path / "DS" / "1" / "a.docx",
        "Additional agreement No. 9X13GR0001-D00003",
        "to the General Policy No. 9X13GR0001",
        "City		26 November 2020",
        "For shipments under declarations No. 12 and No. 13:",
        "This agreement enters into force on 27.11.2020 and is valid until 01.01.2022",
    )
    package = Directory(tmp_path).package()
    assert_that(
        [(item.number(), item.effective(), item.scope()) for item in package.amendments()],
        equal_to([(3, date(2020, 11, 27), ("12", "13"))]),
        "Directory does not read an English policy folder",
    )
