from datetime import date
from typing import Final, Protocol, final

from app.domain.fact import Fact
from app.domain.money import Money


class Clause(Fact, Protocol):
    """Policy clause in the revision that governs a shipment, with a reference to its source."""

    def reference(self) -> str: ...


@final
class Absent:
    """Policy clause that the approved profile does not contain."""

    __slots__ = ("_key",)

    def __init__(self, key: str) -> None:
        self._key: Final = key

    def reference(self) -> str:
        return f"пункт «{self._key}» не найден в профиле полиса"

    def text(self) -> str:
        return ""

    def dates(self) -> tuple[date, ...]:
        return ()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return ()
