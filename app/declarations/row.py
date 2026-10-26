from collections.abc import Mapping
from datetime import date
from typing import Final, final

from app.declarations.schema import Schema
from app.domain.errors import UnreadableError
from app.domain.fact import Fact
from app.domain.field import Field


@final
class Row:
    """Shipment row: cell texts per field key, the schema that reads them and the start day."""

    __slots__ = ("_label", "_schema", "_start", "_texts")

    def __init__(
        self, label: str, texts: Mapping[str, tuple[str, ...]], schema: Schema, start: Fact
    ) -> None:
        self._label: Final = label
        self._texts: Final = texts
        self._schema: Final = schema
        self._start: Final = start

    def label(self) -> str:
        return self._label

    def field(self, key: str) -> Field:
        return self._schema.field(key, self._texts.get(key, ()))

    def start(self) -> date:
        days = self._start.dates()
        if not days:
            raise UnreadableError(
                f"Не найдена дата начала периода страхования в строке {self._label}"
            )
        return days[0]
