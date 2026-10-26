import random
import string
from pathlib import Path

import xlwt
from docx import Document
from hamcrest import assert_that, equal_to, raises
from openpyxl import Workbook

from app.domain.errors import UnreadableError
from app.ingest.source import Source


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_reads_xlsx_by_extension(tmp_path: Path) -> None:
    word = _word()
    book = Workbook()
    book.create_sheet("data").append([word])
    book.save(tmp_path / "a.XLSX")
    assert_that(
        Source(tmp_path / "a.XLSX").sheets()[-1].lines()[0].text(0),
        equal_to(word),
        "Source does not read an xlsx file by its extension",
    )


def test_reads_xls_by_extension(tmp_path: Path) -> None:
    word = _word()
    book = xlwt.Workbook()
    book.add_sheet("data").write(0, 0, word)
    book.save(str(tmp_path / "a.xls"))
    assert_that(
        Source(tmp_path / "a.xls").sheets()[0].lines()[0].text(0),
        equal_to(word),
        "Source does not read an xls file by its extension",
    )


def test_reads_docx_by_extension(tmp_path: Path) -> None:
    word = _word()
    document = Document()
    document.add_paragraph(word)
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        Source(tmp_path / "a.docx").sheets()[0].lines()[0].text(0),
        equal_to(word),
        "Source does not read a docx file by its extension",
    )


def test_refuses_unknown_extension(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    assert_that(
        lambda: Source(tmp_path / "a.pdf").sheets(),
        raises(UnreadableError, "не поддерживается"),
        "Source does not refuse a file of an unknown format",
    )


def test_refuses_broken_xlsx_with_one_sentence(tmp_path: Path) -> None:
    (tmp_path / "a.xlsx").write_bytes(b"not a workbook")
    assert_that(
        lambda: Source(tmp_path / "a.xlsx").sheets(),
        raises(UnreadableError, "не удалось прочитать"),
        "Source does not refuse a broken xlsx file with an understandable error",
    )
