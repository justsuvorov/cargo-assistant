from pathlib import Path

from docx import Document
from hamcrest import assert_that, contains_exactly, equal_to

from app.policy.amendments import Amendments


def _write(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(str(path))


def _agreement(path: Path, number: int, note: str = "") -> None:
    _write(
        path,
        f"Дополнительное соглашение № 9X13GR0001-D{number:05d}",
        "к Генеральному полису страхования грузов № 9X13GR0001 от 20.10.2017 г.",
        "г. Город\t\t«26» ноября 2020 г.",
        note or "Пункт 6 принять в следующей редакции:",
        "Настоящее Дополнительное соглашение вступает в силу с 27.11.2020 г.",
    )


def _survey(root: Path, *names: str) -> Amendments:
    return Amendments(tuple(root / name for name in names), root)


def test_takes_number_from_text_and_not_from_file_name(tmp_path: Path) -> None:
    _agreement(tmp_path / "ДС" / "ДС 10" / "ДС 9.docx", 10)
    outcome = _survey(tmp_path, "ДС/ДС 10/ДС 9.docx").survey()
    assert_that(
        [(item.number(), item.reference()) for item in outcome.items()],
        contains_exactly((10, "ДС/ДС 10/ДС 9.docx")),
        "Amendments do not take the number from the text of the file",
    )


def test_gives_amendments_in_order_of_numbers(tmp_path: Path) -> None:
    for number in (12, 3, 7):
        _agreement(tmp_path / "ДС" / f"{number}" / "a.docx", number)
    outcome = _survey(tmp_path, "ДС/12/a.docx", "ДС/3/a.docx", "ДС/7/a.docx").survey()
    assert_that(
        [item.number() for item in outcome.items()],
        contains_exactly(3, 7, 12),
        "Amendments do not come in the order of their numbers",
    )


def test_skips_attachment_that_is_not_an_amendment(tmp_path: Path) -> None:
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 1)
    _write(tmp_path / "ДС" / "1" / "note.docx", "Согласование", "Просим согласовать")
    outcome = _survey(tmp_path, "ДС/1/a.docx", "ДС/1/note.docx").survey()
    assert_that(
        ([item.number() for item in outcome.items()], outcome.problems()),
        equal_to(([1], ())),
        "Amendments do not skip an attachment quietly",
    )


def test_drops_both_files_with_one_number_and_different_text(tmp_path: Path) -> None:
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 5, "Первая редакция")
    _agreement(tmp_path / "ДС" / "2" / "b.docx", 5, "Вторая редакция")
    outcome = _survey(tmp_path, "ДС/1/a.docx", "ДС/2/b.docx").survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(
            (
                (),
                (
                    "ДС 5 найдено в нескольких файлах с разным текстом"
                    " (ДС/1/a.docx, ДС/2/b.docx), ни один не взят",
                ),
            )
        ),
        "Amendments do not name two files with one number in problems",
    )


def test_keeps_one_of_two_copies_with_the_same_text(tmp_path: Path) -> None:
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 5)
    _agreement(tmp_path / "ДС" / "2" / "copy.docx", 5)
    outcome = _survey(tmp_path, "ДС/1/a.docx", "ДС/2/copy.docx").survey()
    assert_that(
        ([item.reference() for item in outcome.items()], outcome.problems()),
        equal_to((["ДС/1/a.docx"], ())),
        "Amendments do not keep one copy of the same amendment",
    )


def test_names_folder_where_no_amendment_text_was_found(tmp_path: Path) -> None:
    (tmp_path / "ДС" / "ДС 0").mkdir(parents=True)
    (tmp_path / "ДС" / "ДС 0" / "sheet.xls").write_bytes(b"x")
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 1)
    outcome = _survey(tmp_path, "ДС/ДС 0/sheet.xls", "ДС/1/a.docx").survey()
    assert_that(
        outcome.problems(),
        contains_exactly("В папке ДС/ДС 0 не найден текст ДС"),
        "Amendments do not name a folder where the amendment text is missing",
    )


def test_does_not_name_folder_that_holds_folders_with_amendments(tmp_path: Path) -> None:
    (tmp_path / "ДС").mkdir()
    (tmp_path / "ДС" / "list.xls").write_bytes(b"x")
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 1)
    outcome = _survey(tmp_path, "ДС/list.xls", "ДС/1/a.docx").survey()
    assert_that(
        outcome.problems(),
        equal_to(()),
        "Amendments do not leave alone a folder that holds subfolders with amendments",
    )


def test_names_empty_document_in_problems(tmp_path: Path) -> None:
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 1)
    _write(tmp_path / "ДС" / "1" / "empty.docx")
    outcome = _survey(tmp_path, "ДС/1/a.docx", "ДС/1/empty.docx").survey()
    assert_that(
        outcome.problems(),
        contains_exactly("Документ empty.docx пустой, текста нет"),
        "Amendments do not name an empty document in problems",
    )


def test_names_draft_and_keeps_signed_amendments(tmp_path: Path) -> None:
    _agreement(tmp_path / "ДС" / "1" / "a.docx", 1)
    _write(
        tmp_path / "ДС" / "2" / "d.docx",
        "Дополнительное соглашение № 9X13GR0001-D00002",
        "к Генеральному полису № 9X13GR0001 от 20.10.20217 г.",
        "г. Город\t\t«    »    2026 г.",
        "Настоящее Дополнительное соглашение вступает в силу с   .  .2026 г.",
    )
    outcome = _survey(tmp_path, "ДС/1/a.docx", "ДС/2/d.docx").survey()
    assert_that(
        ([item.number() for item in outcome.items()], len(outcome.problems())),
        equal_to(([1], 1)),
        "Amendments do not exclude a draft and name it in problems",
    )
