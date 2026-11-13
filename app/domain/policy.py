from typing import Final, Protocol, final

from app.domain.clause import Absent, Clause
from app.domain.errors import UnboundError
from app.domain.shipment import Shipment


class Policy(Protocol):
    """Approved profile of a general policy with its amendments and special conditions.

    A clause has three answers: a stated clause; Absent when the approved profile does not
    state it; UnboundError when the declaration is bound to no policy at all. Asking for a
    clause raises UnreadableError when its revision cannot be chosen, so that a card tells an
    unknown clause from an absent one and asks a person.
    """

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


@final
class Unbound:
    """Policy of a declaration that could not be bound to a loaded policy: every clause is
    refused with the reason code of the binding, the number is the one the declaration cites."""

    __slots__ = ("_number", "_reason")

    def __init__(self, reason: str, number: str) -> None:
        self._reason: Final = reason
        self._number: Final = number

    def number(self) -> str:
        return self._number

    def clause(self, _key: str, _shipment: Shipment) -> Clause:
        raise UnboundError(self._reason)

    def conditions(self) -> tuple[str, ...]:
        return ()
