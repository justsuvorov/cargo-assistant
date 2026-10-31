import re
from typing import Final, final

from app.domain.field import Field
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Review
from app.rules.outcome import Finding, Outcome
from app.rules.probe import Probe


@final
class Parts:
    """Probe that a filled field states each required part, a number or a date, and then
    runs the inner probe."""

    __slots__ = ("_parts", "_probe")

    def __init__(self, parts: tuple[str, ...], probe: Probe) -> None:
        self._parts: Final = parts
        self._probe: Final = probe

    def outcome(self, field: Field, shipment: Shipment, policy: Policy) -> Outcome:
        stated = {"number": bool(field.entries()), "date": bool(field.dates())}
        if not all(stated[part] for part in self._parts):
            return Finding(Mismatch(), "incomplete", {"entry": field.text()})
        return self._probe.outcome(field, shipment, policy)


@final
class Party:
    """Probe that a field names a party by a legal form and a name: a legal form of the card
    matches, a foreign form needs a person, and a name without a form or a form without a
    name is incomplete."""

    __slots__ = ("_foreign", "_forms")

    def __init__(self, forms: tuple[str, ...], foreign: tuple[str, ...]) -> None:
        self._forms: Final = forms
        self._foreign: Final = foreign

    def outcome(self, field: Field, _shipment: Shipment, _policy: Policy) -> Outcome:
        values = {"entry": field.text()}
        if self._named(field.text(), self._forms):
            return Finding(Match(), "filled", values)
        if self._named(field.text(), self._foreign):
            return Finding(Review(), "foreign", values)
        return Finding(Mismatch(), "incomplete", values)

    def _named(self, text: str, forms: tuple[str, ...]) -> bool:
        folded = text.casefold().replace("ё", "е")
        pattern = "|".join(
            rf"(?<!\w){re.escape(form.casefold().replace('ё', 'е'))}(?!\w)"
            for form in sorted(forms, key=len, reverse=True)
        )
        return (
            bool(forms)
            and bool(re.search(pattern, folded))
            and bool(re.search(r"\w", re.sub(pattern, " ", folded)))
        )
