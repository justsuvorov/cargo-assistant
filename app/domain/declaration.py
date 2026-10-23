from typing import Protocol

from app.domain.shipment import Shipment


class Declaration(Protocol):
    """Declaration file read into its number, form, policy number and shipment rows."""

    def number(self) -> str: ...

    def form(self) -> str: ...

    def policy(self) -> str: ...

    def shipments(self) -> tuple[Shipment, ...]: ...
