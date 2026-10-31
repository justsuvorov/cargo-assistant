from collections.abc import Mapping
from typing import Final, final

from app.domain.clause import Clause
from app.domain.field import Field
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Review
from app.rules.outcome import Finding, Outcome
from app.rules.tokens import Tokens


@final
class Fuzzy:
    """Measure that a field names the same as the clause or one of its items, whatever the
    case, quotes, spaces, word order and abbreviations from the synonyms of the card; a name
    that only contains or is contained in another needs a person."""

    __slots__ = ("_synonyms",)

    def __init__(self, synonyms: Mapping[str, str]) -> None:
        self._synonyms: Final = synonyms

    def outcome(
        self, field: Field, clause: Clause, _shipment: Shipment, _policy: Policy
    ) -> Outcome:
        values = {"reference": clause.reference(), "entry": field.text()}
        value = Tokens(field.text(), self._synonyms)
        names = tuple(Tokens(name, self._synonyms) for name in clause.entries() or (clause.text(),))
        if any(name.same(value) for name in names):
            return Finding(Match(), "same", values)
        if any(name.within(value) or value.within(name) for name in names):
            return Finding(Review(), "partial", values)
        return Finding(Mismatch(), "different", values)
