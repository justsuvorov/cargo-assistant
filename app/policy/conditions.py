import re
import zipfile
from pathlib import Path
from typing import Final, Protocol, final

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.policy.outcome import Outcome, Result


class Condition(Protocol):
    """Special condition of a policy: its text, where it was found and whether it prevails."""

    def text(self) -> str: ...

    def source(self) -> str: ...

    def prevails(self) -> bool: ...


class Written(Protocol):
    """Lines of the special conditions file that the client put into the policy folder."""

    def conditions(self) -> tuple[str, ...]: ...


class SpecialConditions(Protocol):
    """Special conditions of a policy looked up by its number and the insurant.

    An empty insurant means that the name is unknown. The reasons of a lookup that found nothing
    are problems of the outcome, never an exception.
    """

    def find(self, number: str, insurant: str) -> Outcome[Condition]: ...


class Page(Protocol):
    """Sheet of a workbook whose columns are told apart by the title in the first row."""

    def absence(self) -> tuple[str, ...]: ...

    def has(self, title: str) -> bool: ...

    def lines(self) -> range: ...

    def cell(self, line: int, title: str) -> str: ...


@final
class Found:
    """Special condition with the place it was found in."""

    __slots__ = ("_prevails", "_source", "_text")

    def __init__(self, text: str, source: str, *, prevails: bool) -> None:
        self._text: Final = text
        self._source: Final = source
        self._prevails: Final = prevails

    def text(self) -> str:
        return self._text

    def source(self) -> str:
        return self._source

    def prevails(self) -> bool:
        return self._prevails


@final
class Spelling:
    """Text of a cell compared without case, spaces and quotes."""

    __slots__ = ("_raw",)

    def __init__(self, raw: str) -> None:
        self._raw: Final = raw

    def title(self) -> str:
        return "".join(self._raw.lower().split())

    def number(self) -> str:
        return "".join(self._raw.upper().split())

    def name(self) -> str:
        return " ".join(re.sub(r"[«»\"']", "", self._raw).lower().split())


@final
class Table:
    """Rows of a sheet that exists; the first row holds the titles of the columns."""

    __slots__ = ("_rows",)

    def __init__(self, rows: tuple[tuple[str, ...], ...]) -> None:
        self._rows: Final = rows

    def absence(self) -> tuple[str, ...]:
        return ()

    def has(self, title: str) -> bool:
        return self._column(title) >= 0

    def lines(self) -> range:
        return range(1, len(self._rows))

    def cell(self, line: int, title: str) -> str:
        column = self._column(title)
        row = self._rows[line]
        return row[column] if 0 <= column < len(row) else ""

    def _column(self, title: str) -> int:
        return next(
            (
                index
                for index, cell in enumerate(next(iter(self._rows), ()))
                if Spelling(cell).title() == Spelling(title).title()
            ),
            -1,
        )


@final
class Missing:
    """Sheet that the workbook does not have, which is told as the reason."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name: Final = name

    def absence(self) -> tuple[str, ...]:
        return (f"в общем файле особых условий нет листа «{self._name}»",)

    def has(self, _title: str) -> bool:
        return False

    def lines(self) -> range:
        return range(0)

    def cell(self, _line: int, _title: str) -> str:
        return ""


@final
class GeneralSheet:
    """Sheet of general policies where the row of the policy number holds its special conditions."""

    __slots__ = ("_book", "_page")

    def __init__(self, page: Page, book: str) -> None:
        self._page: Final = page
        self._book: Final = book

    def find(self, number: str, _insurant: str) -> Outcome[Condition]:
        if self._page.absence():
            return Result((), self._page.absence())
        if not (self._page.has("№ Генерального полиса") and self._page.has("Особые условия")):
            return Result((), ("на листе «ГП» общего файла нет колонок полиса и особых условий",))
        return Result(
            tuple(
                Found(
                    self._page.cell(line, "Особые условия"),
                    f"{self._book}, лист «ГП», строка {line + 1}",
                    prevails=False,
                )
                for line in self._page.lines()
                if number
                and Spelling(self._page.cell(line, "№ Генерального полиса")).number() == number
                and self._page.cell(line, "Особые условия")
            ),
            (),
        )


@final
class DefenseSheet:
    """Sheet of defense clients where the presence of a row is itself the special condition."""

    __slots__ = ("_book", "_page")

    def __init__(self, page: Page, book: str) -> None:
        self._page: Final = page
        self._book: Final = book

    def find(self, number: str, insurant: str) -> Outcome[Condition]:
        if self._page.absence():
            return Result((), self._page.absence())
        if not (self._page.has("Договор") or self._page.has("Страхователь")):
            return Result(
                (), ("на листе «ОБОРОННЫЙ» общего файла нет колонок договора и страхователя",)
            )
        return Result(
            tuple(
                Found(
                    self._text(line),
                    f"{self._book}, лист «ОБОРОННЫЙ», строка {line + 1}",
                    prevails=False,
                )
                for line in self._page.lines()
                if self._same(line, number, insurant)
            ),
            (),
        )

    def _text(self, line: int) -> str:
        who = self._page.cell(line, "Страхователь") or self._page.cell(line, "Договор")
        reinsurance = self._page.cell(line, "Перестрахование, при условии:")
        form = self._page.cell(line, "Форма работы")
        return (
            f"Оборонный сегмент: {who}, перестрахование при условии «{reinsurance}», "
            f"форма работы «{form}»"
        )

    def _same(self, line: int, number: str, insurant: str) -> bool:
        wanted = Spelling(insurant).name()
        return (bool(number) and Spelling(self._page.cell(line, "Договор")).number() == number) or (
            bool(wanted) and Spelling(self._page.cell(line, "Страхователь")).name() == wanted
        )


@final
class Joined:
    """Lookup that asks several lookups in order and keeps all found conditions and reasons."""

    __slots__ = ("_parts",)

    def __init__(self, parts: tuple[SpecialConditions, ...]) -> None:
        self._parts: Final = parts

    def find(self, number: str, insurant: str) -> Outcome[Condition]:
        outcomes = tuple(part.find(number, insurant) for part in self._parts)
        return Result(
            tuple(item for outcome in outcomes for item in outcome.items()),
            tuple(problem for outcome in outcomes for problem in outcome.problems()),
        )


@final
class ClientFile:
    """Lookup over the special conditions file of the client, whose lines prevail on conflict."""

    __slots__ = ("_package",)

    def __init__(self, package: Written) -> None:
        self._package: Final = package

    def find(self, _number: str, _insurant: str) -> Outcome[Condition]:
        lines = tuple(line.strip() for line in self._package.conditions() if line.strip())
        if not lines:
            return Result((), ("файл особых условий клиента не найден или пуст",))
        return Result(tuple(Found(line, "файл клиента", prevails=True) for line in lines), ())


@final
class SharedFile:
    """Lookup over the shared workbook of the insurer, of which only the matching rows are given.

    The sheets are told apart by name and the columns by the title, both without case and spaces.
    """

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def find(self, number: str, insurant: str) -> Outcome[Condition]:
        if self._path == Path(""):
            return Result((), ("путь к общему файлу особых условий не задан",))
        if not self._path.is_file():
            return Result((), (f"общий файл особых условий {self._path.name} не найден",))
        try:
            pages = self._pages()
        except (InvalidFileException, zipfile.BadZipFile, OSError):
            return Result((), (f"общий файл особых условий {self._path.name} не читается",))
        book = f"общий файл {self._path.name}"
        found = Joined(
            (
                GeneralSheet(pages[0], book),
                DefenseSheet(pages[1], book),
            )
        ).find(Spelling(number).number(), insurant)
        if found.items() or found.problems():
            return found
        return Result((), ("в общем файле особых условий нет строк для этого полиса",))

    def _pages(self) -> tuple[Page, Page]:
        workbook = load_workbook(self._path, read_only=True, data_only=True)
        try:
            tables = {
                Spelling(sheet.title).title(): Table(
                    tuple(
                        tuple(str(cell or "").strip() for cell in row)
                        for row in sheet.iter_rows(values_only=True)
                    )
                )
                for sheet in workbook.worksheets
            }
        finally:
            workbook.close()
        return (
            tables.get("гп", Missing("ГП")),
            tables.get("оборонный", Missing("ОБОРОННЫЙ")),
        )
