from collections.abc import Mapping
from datetime import date
from typing import Final, final

from app.domain.clause import Clause
from app.domain.errors import UnreadableError
from app.domain.field import Field
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Review, Status
from app.rules.outcome import Finding, Outcome
from app.rules.presence import Stated
from app.rules.probe import Probe


@final
class Ordered:
    """Probe that finds the end of the dates of a field, named by the bounds of the card,
    before their start without any policy clause and gives the status of the card for it; dates
    in order and dates that cannot be read go to the inner probe.

    A field without its own start, such as the end of a table row, takes the start of the
    shipment.
    """

    __slots__ = ("_bounds", "_probe", "_status")

    def __init__(self, bounds: tuple[str, ...], status: Status, probe: Probe) -> None:
        self._bounds: Final = bounds
        self._status: Final = status
        self._probe: Final = probe

    def outcome(self, field: Field, shipment: Shipment, policy: Policy) -> Outcome:
        stated = dict(zip(self._bounds, field.dates(), strict=False))
        try:
            days = {"start": stated["start"] if "start" in stated else shipment.start(), **stated}
        except UnreadableError:
            return self._probe.outcome(field, shipment, policy)
        if days.get("end", days["start"]) < days["start"]:
            return Finding(self._status, "end_before_start", {"entry": field.text()})
        return self._probe.outcome(field, shipment, policy)


@final
class Window:
    """Measure that the dates of a field, named by the bounds start and end of the card, lie
    within the term of the clause; the end may pass the term when the profile states the
    extension clause. The order of the dates is the business of Ordered before the clause.

    A field without its own start, such as the end of a table row, takes the start of the
    shipment.
    """

    __slots__ = ("_bounds", "_extension")

    def __init__(self, bounds: tuple[str, ...], extension: str) -> None:
        self._bounds: Final = bounds
        self._extension: Final = extension

    def outcome(self, field: Field, clause: Clause, shipment: Shipment, policy: Policy) -> Outcome:
        term = clause.dates()
        values = {"reference": clause.reference(), "entry": field.text()}
        if len(term) < len(("start", "end")):
            return Finding(Review(), "clause_unreadable", values)
        dated = {
            **values,
            "policy_start": f"{term[0]:%d.%m.%Y}",
            "policy_end": f"{term[1]:%d.%m.%Y}",
        }
        stated = dict(zip(self._bounds, field.dates(), strict=False))
        if len(stated) < len(self._bounds):
            return Finding(Review(), "unreadable", dated)
        try:
            days = {"start": stated["start"] if "start" in stated else shipment.start(), **stated}
        except UnreadableError:
            return Finding(Review(), "unreadable", dated)
        return next(
            iter(self._start(days, term, dated) or self._end(days, term, dated, shipment, policy)),
            Finding(Match(), "within", dated),
        )

    def _start(
        self, days: Mapping[str, date], term: tuple[date, ...], values: Mapping[str, str]
    ) -> tuple[Outcome, ...]:
        if "start" not in self._bounds:
            return ()
        return self._outside(days["start"], term, values)

    def _end(
        self,
        days: Mapping[str, date],
        term: tuple[date, ...],
        values: Mapping[str, str],
        shipment: Shipment,
        policy: Policy,
    ) -> tuple[Outcome, ...]:
        if "end" not in days:
            return ()
        if days["end"] > term[1] and self._extended(shipment, policy):
            return (Finding(Match(), "extended", values),)
        return self._outside(days["end"], term, values)

    def _outside(
        self, day: date, term: tuple[date, ...], values: Mapping[str, str]
    ) -> tuple[Outcome, ...]:
        if day < term[0]:
            return (Finding(Mismatch(), "before_policy_start", values),)
        if day > term[1]:
            return (Finding(Mismatch(), "after_policy_end", values),)
        return ()

    def _extended(self, shipment: Shipment, policy: Policy) -> bool:
        return bool(self._extension) and Stated(policy.clause(self._extension, shipment)).exists()
