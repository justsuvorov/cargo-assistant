import re
from datetime import date
from typing import Final, final

from app.domain.clause import Clause
from app.domain.money import Amount, Money
from app.domain.revision import Revision
from app.domain.shipment import Shipment
from app.policy.schema.profile import Wording


@final
class Quoted:
    """Policy clause that repeats one approved wording and refers to its source."""

    __slots__ = ("_wording",)

    def __init__(self, wording: Wording) -> None:
        self._wording: Final = wording

    def reference(self) -> str:
        return self._wording.source

    def text(self) -> str:
        return self._wording.text

    def dates(self) -> tuple[date, ...]:
        return self._wording.dates

    def amounts(self) -> tuple[Money, ...]:
        return tuple(Amount(each.value, each.currency) for each in self._wording.amounts)

    def entries(self) -> tuple[str, ...]:
        return self._wording.entries


@final
class Unsettled:
    """Policy clause whose revision the code may not choose: it states no facts, so a card
    asks a person, and its reference says why."""

    __slots__ = ("_reason",)

    def __init__(self, reason: str) -> None:
        self._reason: Final = reason

    def reference(self) -> str:
        return self._reason

    def text(self) -> str:
        return ""

    def dates(self) -> tuple[date, ...]:
        return ()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return ()


@final
class Edition:
    """Revision read from one wording of a clause; the only home of the choice rule D-33.

    It governs a shipment from the day it takes effect, when its scope names the declaration
    of the shipment by digits (D-30) or concerns every declaration; an empty scope means the
    same as in a package amendment. Dates in its text do not end it: only a superseding
    revision does, and the term of the policy is the business of a card.

    An edition to named declarations supersedes a general one; within one group the later
    date wins, then the greater amendment number. The contract shows another revision only
    through its clause, so the other one is found among the peers, the wordings of the same
    clause, by its reference; a revision outside the peers or a source that several wordings
    share is not superseded, so that the choice stays with a person.
    """

    __slots__ = ("_peers", "_wording")

    def __init__(self, wording: Wording, peers: tuple[Wording, ...]) -> None:
        self._wording: Final = wording
        self._peers: Final = peers

    def governs(self, shipment: Shipment) -> bool:
        return self._concerns(shipment.declaration()) and self._wording.effective <= (
            shipment.start()
        )

    def supersedes(self, other: Revision) -> bool:
        reference = other.clause().reference()
        ranks = tuple(_rank(peer) for peer in self._peers if peer.source == reference)
        return bool(ranks) and max(ranks) < _rank(self._wording)

    def clause(self) -> Clause:
        return Quoted(self._wording)

    def _concerns(self, declaration: str) -> bool:
        scope = self._wording.scope
        if scope == "all" or not scope:
            return True
        return bool(_figures(declaration)) and _figures(declaration) in map(_figures, scope)


def _rank(wording: Wording) -> tuple[bool, date, int]:
    named = wording.scope != "all" and bool(wording.scope)
    return (named, wording.effective, wording.amendment)


def _figures(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return digits.lstrip("0") or digits[:1]
