import csv
import io
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Final, Protocol, final

from tools.eval.entry import Entry
from tools.eval.gold import Scale
from tools.eval.mask import Mask

type Group = Callable[[Entry], str]


class Paper(Protocol):
    """File that eval writes from the entries of a draft gold."""

    def write(self, entries: tuple[Entry, ...]) -> None: ...


@final
class Cases:
    """Gold files: one CSV per declaration with masked cells and a header of column names.

    Lines of the draft come from FSC marks of MVP answers, so they are sure and have neither a
    clause nor a reason of the expert.
    """

    __slots__ = ("_folder", "_mask")

    def __init__(self, folder: Path, mask: Mask) -> None:
        self._folder: Final = folder
        self._mask: Final = mask

    def write(self, entries: tuple[Entry, ...]) -> None:
        gold = tuple(entry for entry in entries if entry.kind() == "gold")
        twins = [key for key, count in Counter(e.cells()[:3] for e in gold).items() if count > 1]
        if twins:
            raise ValueError(f"В эталоне повторяются места: {twins}")
        self._folder.mkdir(parents=True, exist_ok=True)
        for stale in self._folder.glob("*.csv"):
            stale.unlink()
        for declaration in dict.fromkeys(entry.declaration() for entry in gold):
            (self._folder / f"{declaration}.csv").write_text(
                self._table(tuple(e for e in gold if e.declaration() == declaration)),
                encoding="utf-8",
            )

    def _table(self, entries: tuple[Entry, ...]) -> str:
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
        writer.writerows(
            tuple(map(self._mask.hide, (*cells[:4], "sure", cells[4], "", "", cells[5])))
            for cells in (entry.cells() for entry in entries)
        )
        return buffer.getvalue()


@final
class Questions:
    """Markdown list of rows whose expected status needs an answer from the user or FSC."""

    __slots__ = ("_mask", "_path")

    def __init__(self, path: Path, mask: Mask) -> None:
        self._path: Final = path
        self._mask: Final = mask

    def write(self, entries: tuple[Entry, ...]) -> None:
        rows = Counter(
            tuple(self._mask.hide(cell).replace("|", "/") for cell in entry.cells())
            for entry in entries
            if entry.kind() == "question"
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            "\n".join(
                (
                    "# Вопросы по черновому эталону",
                    "",
                    "Файл собирает `python -m tools.eval gold`; руками его не правят. Сюда "
                    "попадают строки разметки ФСЦ, по которым ожидаемый статус не следует "
                    "однозначно. Ответ записывается в `tests/gold/rulings.yaml` (только с "
                    "согласия пользователя), после чего эталон пересобирается.",
                    "",
                    "Цитаты замечаний ФСЦ обезличены. «Строк» — сколько одинаковых строк MVP "
                    "дали этот вопрос.",
                    "",
                    "| № | Декл. | Строка | Поле | Ответ MVP | Замечание ФСЦ | Почему вопрос "
                    "| Предложение eval | Строк |",
                    "|---|---|---|---|---|---|---|---|---|",
                    *(
                        f"| В-{number} | {cells[0]} | {cells[1]} | {cells[2]} "
                        f"| {Scale().status(cells[3]).text()} | {cells[4] or '—'} | {cells[5]} "
                        f"| {cells[6] or '—'} | {count} |"
                        for number, (cells, count) in enumerate(rows.items(), start=1)
                    ),
                    "",
                )
            ),
            encoding="utf-8",
        )


@final
class Summary:
    """Markdown counts of MVP rows, FSC marks, gold lines, questions and exclusions."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def write(self, entries: tuple[Entry, ...]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            "\n".join(
                (
                    "# Сводка чернового эталона",
                    "",
                    "Файл собирает `python -m tools.eval gold`. «С отметкой» — строки MVP, у "
                    "которых есть комментарий ФСЦ; «Исключено» — поля, которых нет в форме "
                    "декларации (D-14).",
                    "",
                    "## По декларациям",
                    "",
                    *self._table("Декларация", entries, lambda entry: entry.declaration()),
                    "",
                    "## По полям",
                    "",
                    *self._table("Поле", entries, lambda entry: entry.field()),
                    "",
                )
            ),
            encoding="utf-8",
        )

    def _table(self, title: str, entries: tuple[Entry, ...], group: Group) -> tuple[str, ...]:
        names = tuple(dict.fromkeys(map(group, entries)))
        return (
            f"| {title} | Строк MVP | С отметкой | В эталоне | В вопросах | Исключено |",
            "|---|---|---|---|---|---|",
            *(self._row(name, tuple(e for e in entries if group(e) == name)) for name in names),
            self._row("**Итого**", entries),
        )

    def _row(self, name: str, entries: tuple[Entry, ...]) -> str:
        kinds = Counter(entry.kind() for entry in entries)
        return (
            f"| {name} | {len(entries)} | {sum(1 for e in entries if e.marked())} "
            f"| {kinds['gold']} | {kinds['question']} | {kinds['excluded']} |"
        )
