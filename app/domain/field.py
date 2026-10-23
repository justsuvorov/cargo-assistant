from datetime import date
from typing import Final, Protocol, final

from app.domain.fact import Fact
from app.domain.money import Money


class Field(Fact, Protocol):
    """Value of one declaration field in one shipment row, read and normalised."""

    def key(self) -> str: ...

    def filled(self) -> bool: ...


@final
class Blank:
    """Declaration field that is absent or left empty by the client."""

    __slots__ = ("_key",)

    def __init__(self, key: str) -> None:
        self._key: Final = key

    def key(self) -> str:
        return self._key

    def filled(self) -> bool:
        return False

    def text(self) -> str:
        return ""

    def dates(self) -> tuple[date, ...]:
        return ()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return ()
