from typing import Final, Protocol, final


class Cell(Protocol):
    """Cell of a sheet: its zero-based column and the text written in it."""

    def column(self) -> int: ...

    def text(self) -> str: ...


class Line(Protocol):
    """Row of a sheet seen as the cells that carry some text."""

    def number(self) -> int: ...

    def cells(self) -> tuple[Cell, ...]: ...

    def text(self, column: int) -> str: ...

    def after(self, column: int) -> tuple[str, ...]: ...


class Sheet(Protocol):
    """Named grid of lines, the neutral form of a spreadsheet page or a document body."""

    def name(self) -> str: ...

    def lines(self) -> tuple[Line, ...]: ...


class Book(Protocol):
    """Neutral model of a document file: an ordered set of sheets."""

    def sheets(self) -> tuple[Sheet, ...]: ...


@final
class Written:
    """Cell with raw text that is cleaned of non-breaking spaces and escaped line breaks."""

    __slots__ = ("_column", "_raw")

    def __init__(self, column: int, raw: str) -> None:
        self._column: Final = column
        self._raw: Final = raw

    def column(self) -> int:
        return self._column

    def text(self) -> str:
        return (
            self._raw.replace("_x000D_", "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\xa0", " ")
            .strip()
        )


@final
class Series:
    """Line of a sheet that hides the cells whose text is empty."""

    __slots__ = ("_cells", "_number")

    def __init__(self, number: int, cells: tuple[Cell, ...]) -> None:
        self._number: Final = number
        self._cells: Final = cells

    def number(self) -> int:
        return self._number

    def cells(self) -> tuple[Cell, ...]:
        return tuple(cell for cell in self._cells if cell.text())

    def text(self, column: int) -> str:
        return "".join(cell.text() for cell in self.cells() if cell.column() == column)

    def after(self, column: int) -> tuple[str, ...]:
        return tuple(cell.text() for cell in self.cells() if cell.column() > column)


@final
class Page:
    """Sheet that keeps its name and its lines in reading order."""

    __slots__ = ("_lines", "_name")

    def __init__(self, name: str, lines: tuple[Line, ...]) -> None:
        self._name: Final = name
        self._lines: Final = lines

    def name(self) -> str:
        return self._name

    def lines(self) -> tuple[Line, ...]:
        return tuple(line for line in self._lines if line.cells())


@final
class Folder:
    """Book assembled from sheets that are already read."""

    __slots__ = ("_sheets",)

    def __init__(self, sheets: tuple[Sheet, ...]) -> None:
        self._sheets: Final = sheets

    def sheets(self) -> tuple[Sheet, ...]:
        return self._sheets
