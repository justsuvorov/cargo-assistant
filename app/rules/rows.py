from typing import Final, Protocol, final

from app.domain.declaration import Declaration
from app.domain.place import Spot
from app.domain.policy import Policy
from app.domain.semantics import Semantics
from app.domain.verdict import Verdict
from app.rules.answers import Distinct, Replies
from app.rules.probe import Probe
from app.rules.wording import Wording


class Check(Protocol):
    """Way a card judges its field in every shipment of a declaration at once."""

    def verdicts(self, declaration: Declaration, policy: Policy) -> tuple[Verdict, ...]: ...


@final
class Rowwise:
    """Check that probes the field of every shipment, asks the semantic judge all distinct
    questions of the declaration in one batch, if there are any, and words each verdict.

    Shipments with the same value and clause share one question and so one answer.
    """

    __slots__ = ("_key", "_probe", "_semantics", "_wording")

    def __init__(self, key: str, probe: Probe, wording: Wording, semantics: Semantics) -> None:
        self._key: Final = key
        self._probe: Final = probe
        self._wording: Final = wording
        self._semantics: Final = semantics

    def verdicts(self, declaration: Declaration, policy: Policy) -> tuple[Verdict, ...]:
        placed = tuple(
            (
                Spot(shipment.number(), self._key),
                self._probe.outcome(shipment.field(self._key), shipment, policy),
            )
            for shipment in declaration.shipments()
        )
        asked = Distinct(
            tuple(question for place, outcome in placed for question in outcome.questions(place))
        ).questions()
        answers = Replies(asked, self._semantics.verdicts(asked) if asked else ())
        return tuple(outcome.verdict(place, self._wording, answers) for place, outcome in placed)
