from datetime import date
from typing import Protocol

from app.domain.field import Field


class Record(Protocol):
    """One shipment row of a declaration, labelled by its row number in the declaration."""

    def label(self) -> str: ...

    def field(self, key: str) -> Field: ...

    def start(self) -> date: ...


class Layout(Protocol):
    """Form of a declaration sheet: how well it fits, its number, its policy and its rows."""

    def form(self) -> str: ...

    def score(self) -> int: ...

    def number(self) -> str: ...

    def policy(self) -> str: ...

    def records(self) -> tuple[Record, ...]: ...
