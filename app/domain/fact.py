from datetime import date
from typing import Protocol

from app.domain.money import Money


class Fact(Protocol):
    """Piece of text from a document together with the dates, sums and items read from it."""

    def text(self) -> str: ...

    def dates(self) -> tuple[date, ...]: ...

    def amounts(self) -> tuple[Money, ...]: ...

    def entries(self) -> tuple[str, ...]: ...
