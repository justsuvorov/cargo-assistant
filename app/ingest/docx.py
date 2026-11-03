import re
from collections.abc import Callable
from pathlib import Path
from typing import Final, Protocol, final

from docx import Document
from docx.document import Document as Opened
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import parse_xml
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.table import _Cell
from docx.text.paragraph import Paragraph

from app.ingest.book import Cell, Page, Series, Sheet, Written

_WORD: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_SPACES: Final = {"w": _WORD}

_ROMAN: Final = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)

_NO_NUMBER: Final = frozenset({"bullet", "none"})


def _roman(number: int) -> str:
    text = ""
    for value, symbol in _ROMAN:
        text += symbol * (number // value)
        number %= value
    return text


def _letters(number: int) -> str:
    return chr(ord("a") + (number - 1) % 26) * ((number - 1) // 26 + 1)


_FORMATS: Final[dict[str, Callable[[int], str]]] = {
    "decimalZero": lambda number: f"{number:02d}",
    "lowerLetter": _letters,
    "upperLetter": lambda number: _letters(number).upper(),
    "lowerRoman": _roman,
    "upperRoman": lambda number: _roman(number).upper(),
}


def _find(element: BaseOxmlElement, path: str) -> list[BaseOxmlElement]:
    return list(element.findall(path, _SPACES))


def _where(tag: str, attribute: str, value: str) -> str:
    return f'w:{tag}[@{{{_WORD}}}{attribute}="{"" if '"' in value else value}"]'


def _value(element: BaseOxmlElement, path: str, default: str = "") -> str:
    found = _find(element, path)
    return found[0].get(f"{{{_WORD}}}val", default) if found else default


def _whole(text: str, default: int) -> int:
    return int(text) if text.lstrip("-").isdigit() else default


class Labels(Protocol):
    """Numbers that Word shows before the paragraphs of a document, found in document order."""

    def of(self, paragraph: Paragraph) -> str: ...


@final
class Counting:
    """Numbers of list paragraphs computed from numbering.xml and styles.xml of a document.

    Word keeps the numbers out of the text, so they are counted here: the levels of a list, the
    start value, the restart of lower levels, the restart by a list override and the list that a
    paragraph style brings. A list that cannot be understood gives no number and does not fail.
    """

    __slots__ = ("_labels", "_numbering", "_styles")

    def __init__(
        self, body: BaseOxmlElement, numbering: BaseOxmlElement, styles: BaseOxmlElement
    ) -> None:
        self._numbering: Final = numbering
        self._styles: Final = styles
        self._labels: Final = self._count(body)

    def of(self, paragraph: Paragraph) -> str:
        return self._labels.get(paragraph.paragraph_format.element, "")

    def _count(self, body: BaseOxmlElement) -> dict[BaseOxmlElement, str]:
        counters: dict[str, dict[int, int]] = {}
        started: set[str] = set()
        labels: dict[BaseOxmlElement, str] = {}
        for paragraph in body.iter(f"{{{_WORD}}}p"):
            number, level = self._place(paragraph)
            if number:
                labels[paragraph] = self._label(counters, started, number, level)
        return labels

    def _place(self, paragraph: BaseOxmlElement) -> tuple[str, int]:
        number = _value(paragraph, "w:pPr/w:numPr/w:numId")
        level = _value(paragraph, "w:pPr/w:numPr/w:ilvl")
        names = self._chain(_value(paragraph, "w:pPr/w:pStyle"))
        for name in names:
            style = _find(self._styles, _where("style", "styleId", name))[0]
            number = number or _value(style, "w:pPr/w:numPr/w:numId")
            level = level or _value(style, "w:pPr/w:numPr/w:ilvl")
        if number in ("", "0"):
            return "", 0
        return number, _whole(level, self._linked(number, names))

    def _chain(self, name: str) -> list[str]:
        chain: list[str] = []
        while name and name not in chain and _find(self._styles, _where("style", "styleId", name)):
            chain.append(name)
            name = _value(_find(self._styles, _where("style", "styleId", name))[0], "w:basedOn")
        return chain

    def _linked(self, number: str, names: list[str]) -> int:
        for definition in _find(self._abstract(number), "w:lvl"):
            if _value(definition, "w:pStyle") in names:
                return _whole(definition.get(f"{{{_WORD}}}ilvl", ""), 0)
        return 0

    def _reference(self, number: str) -> str:
        return _value(
            next(iter(_find(self._numbering, _where("num", "numId", number))), self._numbering),
            "w:abstractNumId",
        )

    def _abstract(self, number: str) -> BaseOxmlElement:
        return next(
            iter(
                _find(
                    self._numbering, _where("abstractNum", "abstractNumId", self._reference(number))
                )
            ),
            self._numbering,
        )

    def _definition(self, number: str, level: int) -> list[BaseOxmlElement]:
        return _find(
            self._numbering,
            f"{_where('num', 'numId', number)}/{_where('lvlOverride', 'ilvl', str(level))}/w:lvl",
        ) or _find(self._abstract(number), _where("lvl", "ilvl", str(level)))

    def _label(
        self, counters: dict[str, dict[int, int]], started: set[str], number: str, level: int
    ) -> str:
        current = self._definition(number, level)
        if not current:
            return ""
        levels = counters.setdefault(self._reference(number), {})
        if number not in started:
            started.add(number)
            self._restart(number, levels)
        levels[level] = levels[level] + 1 if level in levels else self._start(current[0])
        self._reset(number, levels, level)
        return self._shown(number, levels, current[0])

    def _start(self, definition: BaseOxmlElement) -> int:
        return _whole(_value(definition, "w:start", "1"), 1)

    def _restart(self, number: str, levels: dict[int, int]) -> None:
        for override in _find(
            self._numbering, f"{_where('num', 'numId', number)}/w:lvlOverride[w:startOverride]"
        ):
            level = _whole(override.get(f"{{{_WORD}}}ilvl", ""), 0)
            for deeper in [key for key in levels if key > level]:
                del levels[deeper]
            levels[level] = _whole(_value(override, "w:startOverride"), 1) - 1

    def _reset(self, number: str, levels: dict[int, int], level: int) -> None:
        for deeper in [key for key in levels if key > level]:
            restart = _value(
                next(iter(self._definition(number, deeper)), self._numbering), "w:lvlRestart"
            )
            if restart != "0" and (not restart.isdigit() or level <= int(restart) - 1):
                del levels[deeper]

    def _shown(self, number: str, levels: dict[int, int], definition: BaseOxmlElement) -> str:
        if _value(definition, "w:numFmt", "decimal") in _NO_NUMBER:
            return ""
        return re.sub(
            r"%([1-9])",
            lambda found: self._digits(number, levels, int(found.group(1)) - 1),
            _value(definition, "w:lvlText"),
        ).strip()

    def _digits(self, number: str, levels: dict[int, int], level: int) -> str:
        definition = next(iter(self._definition(number, level)), self._numbering)
        return _FORMATS.get(_value(definition, "w:numFmt"), str)(
            levels.get(level, self._start(definition))
        )


@final
class Docx:
    """Book read from a docx file as one sheet: paragraphs first, then the rows of each table.

    A paragraph of a numbered list begins with the number that Word shows for it, for example
    "6.1.", because Word keeps that number out of the text of the paragraph.
    """

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def sheets(self) -> tuple[Sheet, ...]:
        # @todo #2:30min Читать абзацы и таблицы docx в порядке документа, а не по группам
        document = Document(str(self._path))
        labels = Counting(document.element.body, self._numbering(document), document.styles.element)
        rows = tuple(
            (Written(0, self._text(paragraph, labels)),) for paragraph in document.paragraphs
        ) + tuple(self._row(row.cells, labels) for table in document.tables for row in table.rows)
        return (
            Page(
                "document",
                tuple(Series(number, row) for number, row in enumerate(rows, start=1)),
            ),
        )

    def _numbering(self, document: Opened) -> BaseOxmlElement:
        return (
            document.part.numbering_part.element
            if any(
                relation.reltype == RELATIONSHIP_TYPE.NUMBERING
                for relation in document.part.rels.values()
            )
            else parse_xml(f'<w:numbering xmlns:w="{_WORD}"/>')
        )

    def _text(self, paragraph: Paragraph, labels: Labels) -> str:
        label = labels.of(paragraph)
        text = paragraph.text
        return (
            f"{label} {text}"
            if label and text.strip() and not text.lstrip().startswith(label)
            else text
        )

    def _row(self, cells: list[_Cell], labels: Labels) -> tuple[Cell, ...]:
        return tuple(
            Written(
                column,
                "\n".join(self._text(paragraph, labels) for paragraph in cell.paragraphs),
            )
            for column, cell in enumerate(cells)
            if column == 0 or cell is not cells[column - 1]
        )
