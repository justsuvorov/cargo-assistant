import random
import string
from pathlib import Path

from docx import Document
from hamcrest import assert_that, contains_exactly, equal_to

from app.ingest.docx import Docx


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_reads_paragraphs_as_lines_with_one_cell(tmp_path: Path) -> None:
    word = _word()
    document = Document()
    document.add_paragraph(word)
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        Docx(tmp_path / "a.docx").sheets()[0].lines()[0].text(0),
        equal_to(word),
        "Docx does not read a paragraph as a line with one cell",
    )


def test_reads_table_rows_keeping_grid_columns(tmp_path: Path) -> None:
    first, second = _word(), _word()
    document = Document()
    table = document.add_table(rows=1, cols=4)
    table.cell(0, 0).merge(table.cell(0, 1)).text = first
    table.cell(0, 3).text = second
    document.save(str(tmp_path / "a.docx"))
    line = Docx(tmp_path / "a.docx").sheets()[0].lines()[-1]
    assert_that(
        tuple((cell.column(), cell.text()) for cell in line.cells()),
        contains_exactly((0, first), (3, second)),
        "Docx does not read a merged cell once at the grid column where it starts",
    )
