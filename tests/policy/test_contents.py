import random
import string
from pathlib import Path

from docx import Document
from hamcrest import assert_that, equal_to, raises

from app.domain.errors import UnreadableError
from app.policy.contents import Contents


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_reads_txt_in_utf8(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Первая\nВторая", encoding="utf-8")
    assert_that(
        Contents(tmp_path / "a.txt").text(),
        equal_to("Первая\nВторая"),
        "Contents does not read a txt file in utf-8",
    )


def test_reads_txt_in_utf8_with_byte_order_mark(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Условие", encoding="utf-8-sig")
    assert_that(
        Contents(tmp_path / "a.txt").text(),
        equal_to("Условие"),
        "Contents does not drop the byte order mark of a txt file",
    )


def test_reads_txt_in_cp1251(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Перевозчик", encoding="cp1251")
    assert_that(
        Contents(tmp_path / "a.txt").text(),
        equal_to("Перевозчик"),
        "Contents does not fall back to cp1251 for a txt file",
    )


def test_reads_docx_paragraphs_as_lines(tmp_path: Path) -> None:
    first, second = _word(), _word()
    document = Document()
    document.add_paragraph(first)
    document.add_paragraph(second)
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        Contents(tmp_path / "a.docx").text(),
        equal_to(f"{first}\n{second}"),
        "Contents does not give the paragraphs of a docx file as lines",
    )


def test_gives_empty_text_for_empty_docx(tmp_path: Path) -> None:
    Document().save(str(tmp_path / "a.docx"))
    assert_that(
        Contents(tmp_path / "a.docx").text(),
        equal_to(""),
        "Contents does not give an empty text for a document without paragraphs",
    )


def test_refuses_file_that_is_not_a_document(tmp_path: Path) -> None:
    (tmp_path / "a.docx").write_bytes(b"")
    assert_that(
        lambda: Contents(tmp_path / "a.docx").text(),
        raises(UnreadableError),
        "Contents does not refuse a docx file that cannot be opened",
    )
