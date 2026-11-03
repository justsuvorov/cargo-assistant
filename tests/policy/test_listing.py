from pathlib import Path

from docx import Document
from hamcrest import assert_that, contains_exactly, equal_to

from app.policy.listing import Listing


def test_gives_each_non_blank_line_of_txt_in_utf8(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Первое условие\n\n  Второе условие  \n", encoding="utf-8")
    assert_that(
        Listing((tmp_path / "a.txt",), tmp_path).survey().items(),
        contains_exactly("Первое условие", "Второе условие"),
        "Listing does not give each non-blank line of a txt file",
    )


def test_reads_txt_in_cp1251(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Перевозчик один\nПеревозчик два", encoding="cp1251")
    assert_that(
        Listing((tmp_path / "a.txt",), tmp_path).survey().items(),
        contains_exactly("Перевозчик один", "Перевозчик два"),
        "Listing does not read a txt file in cp1251",
    )


def test_reads_docx_by_paragraphs(tmp_path: Path) -> None:
    document = Document()
    document.add_paragraph("Условие А")
    document.add_paragraph("Условие Б")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        Listing((tmp_path / "a.docx",), tmp_path).survey().items(),
        contains_exactly("Условие А", "Условие Б"),
        "Listing does not read a docx file by paragraphs",
    )


def test_joins_lines_of_several_files_in_given_order(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Один", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Два", encoding="utf-8")
    assert_that(
        Listing((tmp_path / "a.txt", tmp_path / "b.txt"), tmp_path).survey().items(),
        contains_exactly("Один", "Два"),
        "Listing does not join the lines of several files in the given order",
    )


def test_names_unsupported_file_in_problems(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    outcome = Listing((tmp_path / "a.pdf",), tmp_path).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(((), ("Формат файла a.pdf не поддерживается (a.pdf)",))),
        "Listing does not name a file whose format is not read",
    )


def test_names_empty_file_in_problems(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    outcome = Listing((tmp_path / "a.txt",), tmp_path).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(((), ("Документ a.txt пустой, текста нет",))),
        "Listing does not name an empty file in problems",
    )
