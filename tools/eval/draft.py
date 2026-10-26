from typing import Final, Protocol, final

from tools.eval.entry import Entry
from tools.eval.fields import Labels
from tools.eval.rulings import Book
from tools.eval.sheet import Marks


class Drafts(Protocol):
    """Draft gold derived from FSC marks: one entry per marked MVP row."""

    def entries(self) -> tuple[Entry, ...]: ...


@final
class Draft:
    """Draft gold: plain «верно» keeps the MVP status, everything else follows a ruling."""

    __slots__ = ("_book", "_labels", "_marks")

    def __init__(self, marks: Marks, labels: Labels, book: Book) -> None:
        self._marks: Final = marks
        self._labels: Final = labels
        self._book: Final = book

    def entries(self) -> tuple[Entry, ...]:
        lines = self._marks.lines()
        unused = self._book.unused(
            frozenset((mark.shipment(), self._labels.target(mark).field()) for mark in lines)
        )
        if unused:
            raise ValueError(
                f"Решения не относятся ни к одной строке разметки: {', '.join(unused)}"
            )
        return tuple(
            self._book.ruling(mark.shipment(), target.field()).entry(mark, target)
            for mark in lines
            for target in (self._labels.target(mark),)
        )
