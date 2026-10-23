from typing import Protocol

from app.domain.clause import Clause
from app.domain.shipment import Shipment


class Policy(Protocol):
    """Approved profile of a general policy with its amendments and special conditions."""

    def number(self) -> str: ...

    def clause(self, key: str, shipment: Shipment) -> Clause: ...

    def conditions(self) -> tuple[str, ...]: ...
