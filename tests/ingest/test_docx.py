import random
import string
from pathlib import Path

from docx import Document
from docx.document import Document as Opened
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import parse_xml
from docx.table import _Cell
from hamcrest import assert_that, contains_exactly, equal_to

from app.ingest.docx import Docx

_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _level(index: int, fmt: str, text: str, start: int = 1) -> str:
    return (
        f'<w:lvl w:ilvl="{index}"><w:start w:val="{start}"/><w:numFmt w:val="{fmt}"/>'
        f'<w:lvlText w:val="{text}"/></w:lvl>'
    )


def _abstract(number: int, *levels: str) -> str:
    return f'<w:abstractNum {_NS} w:abstractNumId="{number}">{"".join(levels)}</w:abstractNum>'


def _num(number: int, abstract: int, extra: str = "") -> str:
    return f'<w:num {_NS} w:numId="{number}"><w:abstractNumId w:val="{abstract}"/>{extra}</w:num>'


def _lists(document: Opened, *parts: str) -> None:
    root = document.part.numbering_part.element
    for child in list(root):
        root.remove(child)
    for part in parts:
        root.append(parse_xml(part))


def _item(container: Opened | _Cell, number: int, level: int, text: str) -> None:
    container.add_paragraph(text).paragraph_format.element.get_or_add_pPr().append(
        parse_xml(f'<w:numPr {_NS}><w:ilvl w:val="{level}"/><w:numId w:val="{number}"/></w:numPr>')
    )


def _texts(path: Path) -> list[str]:
    return [line.text(0) for line in Docx(path).sheets()[0].lines()]


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


def test_numbers_multilevel_list_and_restarts_lower_levels(tmp_path: Path) -> None:
    document = Document()
    _lists(
        document,
        _abstract(1, _level(0, "decimal", "%1."), _level(1, "decimal", "%1.%2.")),
        _num(1, 1),
    )
    for level, text in ((0, "a"), (1, "b"), (1, "c"), (0, "d"), (1, "e")):
        _item(document, 1, level, text)
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[:5],
        contains_exactly("1. a", "1.1. b", "1.2. c", "2. d", "2.1. e"),
        "Docx does not number a multilevel list as Word shows it",
    )


def test_starts_numbering_from_the_start_value(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.", start=5)), _num(1, 1))
    _item(document, 1, 0, "a")
    _item(document, 1, 0, "b")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[:2],
        contains_exactly("5. a", "6. b"),
        "Docx does not begin a list at its start value",
    )


def test_restarts_list_by_start_override(tmp_path: Path) -> None:
    document = Document()
    override = '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="3"/></w:lvlOverride>'
    _lists(
        document,
        _abstract(1, _level(0, "decimal", "%1.")),
        _num(1, 1),
        _num(2, 1, override),
    )
    _item(document, 1, 0, "a")
    _item(document, 1, 0, "b")
    _item(document, 2, 0, "c")
    _item(document, 2, 0, "d")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[:4],
        contains_exactly("1. a", "2. b", "3. c", "4. d"),
        "Docx does not restart a list that has a start override",
    )


def test_continues_one_counter_for_lists_sharing_an_abstract_list(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1), _num(2, 1))
    _item(document, 1, 0, "a")
    _item(document, 2, 0, "b")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[:2],
        contains_exactly("1. a", "2. b"),
        "Docx does not continue the counter of lists that share one abstract list",
    )


def test_takes_numbering_from_paragraph_style(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1))
    style = document.styles.add_style("Clause", WD_STYLE_TYPE.PARAGRAPH)
    style.element.get_or_add_pPr().append(
        parse_xml(f'<w:numPr {_NS}><w:numId w:val="1"/></w:numPr>')
    )
    document.add_paragraph("a", style="Clause")
    document.add_paragraph("b", style="Clause")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[:2],
        contains_exactly("1. a", "2. b"),
        "Docx does not take the list of a paragraph from its style",
    )


def test_takes_numbering_from_the_style_that_the_paragraph_style_is_based_on(
    tmp_path: Path,
) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1))
    base = document.styles.add_style("Base", WD_STYLE_TYPE.PARAGRAPH)
    base.element.get_or_add_pPr().append(
        parse_xml(f'<w:numPr {_NS}><w:numId w:val="1"/></w:numPr>')
    )
    document.styles.add_style("Child", WD_STYLE_TYPE.PARAGRAPH).base_style = base
    document.add_paragraph("a", style="Child")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[0],
        equal_to("1. a"),
        "Docx does not take the list from the style that the paragraph style is based on",
    )


def test_numbers_paragraph_of_table_cell(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1))
    _item(document.add_table(rows=1, cols=1).cell(0, 0), 1, 0, "b")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[-1],
        equal_to("1. b"),
        "Docx does not number a paragraph of a table cell",
    )


def test_counts_table_cell_paragraph_before_the_paragraph_after_the_table(
    tmp_path: Path,
) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1))
    _item(document, 1, 0, "a")
    _item(document.add_table(rows=1, cols=1).cell(0, 0), 1, 0, "b")
    _item(document, 1, 0, "c")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx"),
        contains_exactly("1. a", "3. c", "2. b"),
        "Docx does not count the paragraphs of a document in the order of the document",
    )


def test_gives_no_number_to_bullets(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "bullet", "o")), _num(1, 1))
    _item(document, 1, 0, "a")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[0],
        equal_to("a"),
        "Docx does not leave a bulleted paragraph without number",
    )


def test_reads_list_of_unknown_number_format_without_failing(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "chineseCounting", "%1.")), _num(1, 1))
    _item(document, 1, 0, "a")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[0].endswith("a"),
        equal_to(True),
        "Docx does not read a list whose number format is unknown",
    )


def test_leaves_paragraph_without_number_when_its_list_is_missing(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1))
    _item(document, 7, 0, "a")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[0],
        equal_to("a"),
        "Docx does not leave a paragraph without number when its list is missing",
    )


def test_formats_letters_and_roman_numbers(tmp_path: Path) -> None:
    document = Document()
    _lists(
        document,
        _abstract(1, _level(0, "lowerLetter", "%1)"), _level(1, "upperRoman", "%2.")),
        _num(1, 1),
    )
    for level, text in ((0, "a"), (0, "b"), (1, "c"), (1, "d")):
        _item(document, 1, level, text)
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[:4],
        contains_exactly("a) a", "b) b", "I. c", "II. d"),
        "Docx does not format letters and roman numbers of a list",
    )


def test_does_not_double_number_written_in_the_text(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1))
    _item(document, 1, 0, "1. a")
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[0],
        equal_to("1. a"),
        "Docx does not keep one number when the text already begins with it",
    )


def test_keeps_text_of_paragraph_without_list_unchanged(tmp_path: Path) -> None:
    document = Document()
    _lists(document, _abstract(1, _level(0, "decimal", "%1.")), _num(1, 1))
    word = _word()
    document.add_paragraph(word)
    document.save(str(tmp_path / "a.docx"))
    assert_that(
        _texts(tmp_path / "a.docx")[0],
        equal_to(word),
        "Docx changes the text of a paragraph that is not in a list",
    )
