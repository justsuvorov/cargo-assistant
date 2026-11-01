import csv
import io
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Protocol, final

import openpyxl

from app.domain.status import Match, Mismatch, Review
from tools.eval.gold import Scale
from tools.eval.mask import Mask
from tools.eval.number import Digits
from tools.eval.template import Columns

_REQUIRED = (
    "Номер декларации/строки",
    "Наименование поля",
    "Ожидаемый статус",
    "Пункт ГП / ДС",
    "Причина",
    "Уверенность",
)


class Answer(Protocol):
    """Row of a filled marking template: the expected status of one place and its grounds."""

    def where(self) -> str: ...

    def problems(self) -> tuple[str, ...]: ...

    def declaration(self) -> str: ...

    def spot(self) -> tuple[str, str, str]: ...

    def value(self) -> str: ...

    def status(self) -> str: ...

    def sure(self) -> bool: ...

    def cells(self) -> tuple[str, ...]: ...


class Batch(Protocol):
    """Filled marking templates of a folder: their rows and every mistake found in them."""

    def answers(self) -> tuple[Answer, ...]: ...

    def problems(self) -> tuple[str, ...]: ...


class Record(Protocol):
    """Gold files that the rows of filled templates are written into."""

    def write(self, answers: tuple[Answer, ...]) -> None: ...


@final
class Marked:
    """Row of a template read by column titles; field labels turn into keys of the form."""

    __slots__ = ("_cells", "_keys", "_where")

    def __init__(self, where: str, cells: Mapping[str, str], keys: Mapping[str, str]) -> None:
        self._where: Final = where
        self._cells: Final = cells
        self._keys: Final = keys

    def where(self) -> str:
        return self._where

    def problems(self) -> tuple[str, ...]:
        status = self._text("Ожидаемый статус")
        level = self._text("Уверенность")
        checks = (
            (not Digits(self._shipment()).text().replace("/", "").isdigit(), "нет номера"),
            (
                not self._key(),
                f"поле «{self._cell('Наименование поля')}» не из формы ответа",
            ),
            (not status, "не указан ожидаемый статус"),
            (
                bool(status) and status not in self._statuses(),
                f"статус «{status}» не из трёх: совпадает, не совпадает, требует проверки",
            ),
            (
                status == Mismatch().text() and not self._cell("Пункт ГП / ДС"),
                "для «не совпадает» не указан пункт ГП / ДС",
            ),
            (
                status in (Mismatch().text(), Review().text()) and not self._cell("Причина"),
                f"для «{status}» не указана причина",
            ),
            (not level, "не указана уверенность"),
            (
                bool(level) and level not in Columns().levels(),
                f"уверенность «{level}» не из двух: уверен, спорно",
            ),
        )
        return tuple(f"{self._where}: {text}" for broken, text in checks if broken)

    def declaration(self) -> str:
        return self._shipment().split("/")[0].strip()

    def spot(self) -> tuple[str, str, str]:
        return (Digits(self.declaration()).text(), Digits(self._shipment()).text(), self._key())

    def value(self) -> str:
        return " ".join(self._cell("Значение в декларации").casefold().split())

    def status(self) -> str:
        return self._statuses()[self._text("Ожидаемый статус")]

    def sure(self) -> bool:
        return Columns().levels()[self._text("Уверенность")] == "sure"

    def cells(self) -> tuple[str, ...]:
        return (
            self.declaration(),
            self._shipment(),
            self._key(),
            self.status(),
            Columns().levels()[self._text("Уверенность")],
            "fsc-expert",
            self._cell("Пункт ГП / ДС"),
            self._cell("Причина"),
            self._cell("Примечание"),
        )

    def _shipment(self) -> str:
        return self._cell("Номер декларации/строки")

    def _key(self) -> str:
        return self._keys.get(" ".join(self._cell("Наименование поля").split()), "")

    def _cell(self, title: str) -> str:
        return " ".join(self._cells.get(title, "").split())

    def _text(self, title: str) -> str:
        return self._cell(title).casefold().replace("ё", "е")

    def _statuses(self) -> dict[str, str]:
        return {status.text(): status.key() for status in (Match(), Mismatch(), Review())}


@final
class Broken:
    """Template file that cannot be read as a marking, kept as a row that only has a problem."""

    __slots__ = ("_problem", "_where")

    def __init__(self, where: str, problem: str) -> None:
        self._where: Final = where
        self._problem: Final = problem

    def where(self) -> str:
        return self._where

    def problems(self) -> tuple[str, ...]:
        return (f"{self._where}: {self._problem}",)

    def declaration(self) -> str:
        return ""

    def spot(self) -> tuple[str, str, str]:
        return ("", "", "")

    def value(self) -> str:
        return ""

    def status(self) -> str:
        return ""

    def sure(self) -> bool:
        return False

    def cells(self) -> tuple[str, ...]:
        raise ValueError(f"{self._where}: файл разметки не прочитан, писать в эталон нечего")


@final
class Markings:
    """Batch of every filled template in a folder, checked row by row and across rows.

    Across rows, one place must be marked once, and equal non-empty values of one field in
    one declaration must get one status among sure rows (rule 3 of section 3).
    """

    __slots__ = ("_folder", "_keys")

    def __init__(self, folder: Path, keys: Mapping[str, str]) -> None:
        self._folder: Final = folder
        self._keys: Final = keys

    def answers(self) -> tuple[Answer, ...]:
        files = sorted(
            path for path in self._folder.glob("*.xlsx") if not path.name.startswith("~$")
        )
        if not files:
            raise FileNotFoundError(f"В каталоге {self._folder} нет файлов разметки xlsx")
        return tuple(answer for path in files for answer in self._rows(path))

    def problems(self) -> tuple[str, ...]:
        answers = self.answers()
        sound = tuple(answer for answer in answers if not answer.problems())
        return (
            *(problem for answer in answers for problem in answer.problems()),
            *self._twins(sound),
            *self._discrepancies(tuple(answer for answer in sound if answer.sure())),
        )

    def _rows(self, path: Path) -> tuple[Answer, ...]:
        book = openpyxl.load_workbook(path, data_only=True)
        sheet = book["Разметка"] if "Разметка" in book.sheetnames else book.worksheets[0]
        rows = tuple(
            tuple("" if cell is None else str(cell) for cell in row)
            for row in sheet.iter_rows(values_only=True)
        )
        titles = tuple(" ".join(title.split()) for title in (rows or ((),))[0])
        lost = tuple(title for title in _REQUIRED if title not in titles)
        if lost:
            return (Broken(path.name, f"нет колонок {', '.join(lost)}"),)
        return tuple(
            Marked(
                f"{path.name}, строка {number}", dict(zip(titles, row, strict=False)), self._keys
            )
            for number, row in enumerate(rows[1:], start=2)
            if any(cell.strip() for cell in row)
        )

    def _twins(self, answers: tuple[Answer, ...]) -> tuple[str, ...]:
        spots = tuple(dict.fromkeys(answer.spot() for answer in answers))
        return tuple(
            f"{'; '.join(a.where() for a in same)}: место {spot[1]} × {spot[2]} размечено "
            f"{len(same)} раза"
            for spot in spots
            for same in (tuple(a for a in answers if a.spot() == spot),)
            if len(same) > 1
        )

    def _discrepancies(self, answers: tuple[Answer, ...]) -> tuple[str, ...]:
        groups = tuple(
            dict.fromkeys(
                (answer.spot()[0], answer.spot()[2], answer.value())
                for answer in answers
                if answer.value()
            )
        )
        return tuple(
            f"{'; '.join(a.where() for a in same)}: расхождение — одинаковое значение поля "
            f"{group[1]} с разными статусами "
            f"({', '.join(sorted({Scale().status(a.status()).text() for a in same}))}); "
            f"дайте одинаковый ответ или отметьте строки «спорно» с пояснением"
            for group in groups
            for same in (
                tuple(a for a in answers if (a.spot()[0], a.spot()[2], a.value()) == group),
            )
            if len({a.status() for a in same}) > 1
        )


@final
class Additions:
    """Gold CSV files written for new declarations only; an existing declaration is refused.

    A declaration already in the gold changes only with consent of the user (rule 8), so its
    file is replaced by hand together with a record in the change log of the manifest.
    """

    __slots__ = ("_folder", "_mask")

    def __init__(self, folder: Path, mask: Mask) -> None:
        self._folder: Final = folder
        self._mask: Final = mask

    def write(self, answers: tuple[Answer, ...]) -> None:
        declarations = tuple(dict.fromkeys(answer.declaration() for answer in answers))
        present = {Digits(path.stem).text(): path.name for path in self._folder.glob("*.csv")}
        taken = tuple(
            present[Digits(number).text()]
            for number in declarations
            if Digits(number).text() in present
        )
        if taken:
            raise FileExistsError(
                f"Декларации уже есть в эталоне {self._folder}: {', '.join(taken)}; замена — "
                f"только с согласия пользователя и записью в журнале версий"
            )
        self._folder.mkdir(parents=True, exist_ok=True)
        for number in declarations:
            (self._folder / f"{number}.csv").write_text(
                self._table(tuple(a for a in answers if a.declaration() == number)),
                encoding="utf-8",
            )

    def _table(self, answers: tuple[Answer, ...]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            (
                "declaration",
                "shipment",
                "field",
                "status",
                "confidence",
                "basis",
                "clause",
                "reason",
                "note",
            )
        )
        writer.writerows(tuple(map(self._mask.hide, answer.cells())) for answer in answers)
        return buffer.getvalue()
