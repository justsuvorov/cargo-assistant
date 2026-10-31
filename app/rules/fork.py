from typing import Final, Protocol, final

from app.domain.field import Field
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.rules.modes import Kinds
from app.rules.outcome import Outcome
from app.rules.presence import Stated
from app.rules.probe import Probe


class Condition(Protocol):
    """Fact about a shipment or its policy that chooses how a conditional card checks."""

    def holds(self, shipment: Shipment, policy: Policy) -> bool: ...


@final
class Flag:
    """Condition that the profile states a clause, such as a risk that needs a carrier list."""

    __slots__ = ("_key",)

    def __init__(self, key: str) -> None:
        self._key: Final = key

    def holds(self, shipment: Shipment, policy: Policy) -> bool:
        return Stated(policy.clause(self._key, shipment)).exists()


@final
class Mixed:
    """Condition that another field of the shipment declares a mixed carriage."""

    __slots__ = ("_key", "_kinds")

    def __init__(self, key: str, kinds: Kinds) -> None:
        self._key: Final = key
        self._kinds: Final = kinds

    def holds(self, shipment: Shipment, _policy: Policy) -> bool:
        return self._kinds.mixed(shipment.field(self._key).text())


@final
class Fork:
    """Probe that runs one probe when the condition holds and the other one when it does not."""

    __slots__ = ("_condition", "_otherwise", "_then")

    def __init__(self, condition: Condition, then: Probe, otherwise: Probe) -> None:
        self._condition: Final = condition
        self._then: Final = then
        self._otherwise: Final = otherwise

    def outcome(self, field: Field, shipment: Shipment, policy: Policy) -> Outcome:
        if self._condition.holds(shipment, policy):
            return self._then.outcome(field, shipment, policy)
        return self._otherwise.outcome(field, shipment, policy)
