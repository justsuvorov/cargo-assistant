from datetime import date
from typing import Final, final

from app.domain.clause import Clause
from app.domain.field import Field
from app.domain.money import Money
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.rules.outcome import Outcome, Pending
from app.rules.presence import Stated


@final
class Joint:
    """Clause made of the stated clauses among several, such as the object of insurance and
    its exclusions, joined in their order."""

    __slots__ = ("_clauses",)

    def __init__(self, clauses: tuple[Clause, ...]) -> None:
        self._clauses: Final = clauses

    def reference(self) -> str:
        return "; ".join(clause.reference() for clause in self._stated())

    def text(self) -> str:
        return "\n".join(clause.text() for clause in self._stated() if clause.text())

    def dates(self) -> tuple[date, ...]:
        return tuple(day for clause in self._stated() for day in clause.dates())

    def amounts(self) -> tuple[Money, ...]:
        return tuple(amount for clause in self._stated() for amount in clause.amounts())

    def entries(self) -> tuple[str, ...]:
        return tuple(entry for clause in self._stated() for entry in clause.entries())

    def _stated(self) -> tuple[Clause, ...]:
        return tuple(clause for clause in self._clauses if Stated(clause).exists())


@final
class Asking:
    """Measure that leaves the field to a semantic judge: the whole value, the clause joined
    with the clauses of its exclusions and the rule of the card make one question."""

    __slots__ = ("_exclusions", "_rule")

    def __init__(self, exclusions: tuple[str, ...], rule: str) -> None:
        self._exclusions: Final = exclusions
        self._rule: Final = rule

    def outcome(self, field: Field, clause: Clause, shipment: Shipment, policy: Policy) -> Outcome:
        return Pending(
            field.text(),
            Joint((clause, *(policy.clause(key, shipment) for key in self._exclusions))),
            self._rule,
        )
