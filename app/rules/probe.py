from typing import Final, Protocol, final

from app.domain.clause import Clause
from app.domain.field import Field
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Status
from app.rules.outcome import Finding, Gap, Outcome
from app.rules.presence import Stated
from app.rules.tokens import Tokens


class Probe(Protocol):
    """Check of one field of one shipment, which may ask the policy for its clauses."""

    def outcome(self, field: Field, shipment: Shipment, policy: Policy) -> Outcome: ...


class Measure(Protocol):
    """Check of one field of one shipment against a policy clause that is known to exist."""

    def outcome(
        self, field: Field, clause: Clause, shipment: Shipment, policy: Policy
    ) -> Outcome: ...


@final
class Emptied:
    """Probe that gives the status of the card for an empty field or a field that holds only
    a blank word such as «нет», and runs the inner probe otherwise."""

    __slots__ = ("_probe", "_status", "_words")

    def __init__(self, words: tuple[str, ...], status: Status, probe: Probe) -> None:
        self._words: Final = words
        self._status: Final = status
        self._probe: Final = probe

    def outcome(self, field: Field, shipment: Shipment, policy: Policy) -> Outcome:
        folded = field.text().strip().casefold().strip(" .")
        if not field.filled() or not folded or folded in {word.casefold() for word in self._words}:
            return Finding(self._status, "empty", {"entry": field.text()})
        return self._probe.outcome(field, shipment, policy)


@final
class Accepted:
    """Probe that matches a field whose value the special conditions of the client accept,
    found in the clause accepted.<field>, and runs the inner probe otherwise."""

    __slots__ = ("_key", "_probe")

    def __init__(self, key: str, probe: Probe) -> None:
        self._key: Final = key
        self._probe: Final = probe

    def outcome(self, field: Field, shipment: Shipment, policy: Policy) -> Outcome:
        clause = policy.clause(f"accepted.{self._key}", shipment)
        value = Tokens(field.text(), {})
        if any(Tokens(entry, {}).same(value) for entry in (*clause.entries(), clause.text())):
            return Finding(
                Match(), "accepted", {"reference": clause.reference(), "entry": field.text()}
            )
        return self._probe.outcome(field, shipment, policy)


@final
class Grounded:
    """Probe that fetches the policy clause of the shipment and measures the field against
    it, or asks a person when the profile has no such clause."""

    __slots__ = ("_key", "_measure")

    def __init__(self, key: str, measure: Measure) -> None:
        self._key: Final = key
        self._measure: Final = measure

    def outcome(self, field: Field, shipment: Shipment, policy: Policy) -> Outcome:
        clause = policy.clause(self._key, shipment)
        if not Stated(clause).exists():
            return Gap(clause)
        return self._measure.outcome(field, clause, shipment, policy)


@final
class Constant:
    """Probe that gives one status whatever the field says, such as for an optional field."""

    __slots__ = ("_name", "_status")

    def __init__(self, status: Status, name: str) -> None:
        self._status: Final = status
        self._name: Final = name

    def outcome(self, field: Field, _shipment: Shipment, _policy: Policy) -> Outcome:
        return Finding(self._status, self._name, {"entry": field.text()})
