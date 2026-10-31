from typing import Final, Protocol, final

from app.domain.clause import Absent, Clause
from app.domain.shipment import Shipment


class Policy(Protocol):
    """Approved profile of a general policy with its amendments and special conditions."""

    def number(self) -> str: ...

    def clause(self, key: str, shipment: Shipment) -> Clause: ...

    def conditions(self) -> tuple[str, ...]: ...


@final
class Vacant:
    """Policy cited by a declaration whose profile is not loaded or not approved yet."""

    __slots__ = ("_number",)

    def __init__(self, number: str) -> None:
        self._number: Final = number

    def number(self) -> str:
        return self._number

    def clause(self, key: str, _shipment: Shipment) -> Clause:
        return Absent(key)

    def conditions(self) -> tuple[str, ...]:
        return ()
