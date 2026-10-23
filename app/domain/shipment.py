from datetime import date
from typing import Protocol

from app.domain.field import Field


class Shipment(Protocol):
    """One shipment row of a declaration, numbered 200 or 200/N in the result."""

    def number(self) -> str: ...

    def declaration(self) -> str: ...

    def field(self, key: str) -> Field: ...

    def start(self) -> date: ...
