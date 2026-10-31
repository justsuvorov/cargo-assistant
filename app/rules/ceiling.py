from collections.abc import Mapping
from typing import Final, final

from app.domain.clause import Clause
from app.domain.errors import IncomparableError
from app.domain.field import Field
from app.domain.money import Money
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Review, Status
from app.rules.outcome import Finding, Outcome, Worst


@final
class Ceiling:
    """Measure that every declared sum is not above a limit of the clause in the same
    currency; a sum in another currency is neither converted nor compared and gets the
    status of the card for a foreign currency."""

    __slots__ = ("_foreign",)

    def __init__(self, foreign: Status) -> None:
        self._foreign: Final = foreign

    def outcome(
        self, field: Field, clause: Clause, _shipment: Shipment, _policy: Policy
    ) -> Outcome:
        values = {"reference": clause.reference(), "entry": field.text(), "amount": field.text()}
        if not field.amounts():
            return Finding(Review(), "unreadable", values)
        if not clause.amounts():
            return Finding(Review(), "clause_unreadable", values)
        return Worst(
            tuple(self._against(amount, clause.amounts(), values) for amount in field.amounts())
        )

    def _against(
        self, amount: Money, limits: tuple[Money, ...], values: Mapping[str, str]
    ) -> Outcome:
        for limit in limits:
            try:
                over = amount.exceeds(limit)
            except IncomparableError:
                continue
            return Finding(
                Mismatch() if over else Match(),
                "over_limit" if over else "within_limit",
                {**values, "amount": amount.text(), "limit": limit.text()},
            )
        return Finding(
            self._foreign,
            "currency",
            {
                **values,
                "amount": amount.text(),
                "limit": ", ".join(limit.text() for limit in limits),
            },
        )
