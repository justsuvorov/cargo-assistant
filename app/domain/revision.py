from typing import Protocol

from app.domain.clause import Clause
from app.domain.shipment import Shipment


class Revision(Protocol):
    """Wording of one policy clause taken from the policy itself or from one amendment."""

    def governs(self, shipment: Shipment) -> bool: ...

    def supersedes(self, other: "Revision") -> bool: ...

    def clause(self) -> Clause: ...
