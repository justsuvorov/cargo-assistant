from datetime import date
from typing import Final, final

from app.declarations.layout import Layout, Record
from app.declarations.psg import Psg
from app.declarations.vertical import Vertical
from app.domain.errors import UnreadableError
from app.domain.field import Field
from app.domain.shipment import Shipment
from app.ingest.book import Book

_FIT = 5


@final
class Numbered:
    """Shipment of a declaration: numbered 200 if it is the only one, else 200/N by its row."""

    __slots__ = ("_count", "_declaration", "_record")

    def __init__(self, declaration: str, count: int, record: Record) -> None:
        self._declaration: Final = declaration
        self._count: Final = count
        self._record: Final = record

    def number(self) -> str:
        if self._count == 1:
            return self._declaration
        return f"{self._declaration}/{self._record.label()}"

    def declaration(self) -> str:
        return self._declaration

    def field(self, key: str) -> Field:
        return self._record.field(key)

    def start(self) -> date:
        return self._record.start()


@final
class Declared:
    """Declaration read from a book without any model: its best fitting sheet gives all.

    The book is read and its sheets are ranked on the first question only; the chosen layout
    is then remembered, so every next question is answered from it.
    """

    __slots__ = ("_book", "_chosen")

    def __init__(self, book: Book) -> None:
        self._book: Final = book
        self._chosen: Final[list[Layout]] = []

    def number(self) -> str:
        return self._layout().number()

    def form(self) -> str:
        return self._layout().form()

    def policy(self) -> str:
        return self._layout().policy()

    def shipments(self) -> tuple[Shipment, ...]:
        layout = self._layout()
        records = layout.records()
        number = layout.number()
        if not records:
            raise UnreadableError("В декларации не найдено ни одной строки перевозки")
        return tuple(Numbered(number, len(records), record) for record in records)

    def _layout(self) -> Layout:
        if not self._chosen:
            self._chosen.append(self._ranked())
        return self._chosen[0]

    def _ranked(self) -> Layout:
        ranked = sorted(
            (layout for sheet in self._book.sheets() for layout in (Vertical(sheet), Psg(sheet))),
            key=lambda layout: -layout.score(),
        )
        if not ranked or ranked[0].score() < _FIT:
            raise UnreadableError("В файле не найден лист с декларацией")
        return ranked[0]
