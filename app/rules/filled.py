import re
from collections.abc import Mapping
from typing import Final, final

from app.domain.field import Field
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Status
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
    """Probe that a field names a party by a legal form and a name.

    A legal form of the card with a name matches, a form without a name is incomplete. The
    card gives the statuses of the other cases: a foreign form, a form fused with the next
    word without a space, a name without a form written only in Latin letters and any other
    name without a form.
    """

    __slots__ = ("_foreign", "_forms", "_statuses")

    def __init__(
        self, forms: tuple[str, ...], foreign: tuple[str, ...], statuses: Mapping[str, Status]
    ) -> None:
        self._forms: Final = forms
        self._foreign: Final = foreign
        self._statuses: Final = statuses

    def outcome(self, field: Field, _shipment: Shipment, _policy: Policy) -> Outcome:
        text = field.text()
        values = {"entry": text}
        if self._named(text, self._forms):
            return Finding(Match(), "filled", values)
        if self._named(text, self._foreign):
            return Finding(self._statuses["foreign"], "foreign", values)
        if self._fused(text, (*self._forms, *self._foreign)):
            return Finding(self._statuses["fused"], "fused", values)
        if self._formed(text, (*self._forms, *self._foreign)):
            return Finding(Mismatch(), "incomplete", values)
        if re.search(r"[A-Za-z]", text) and not re.search(r"[^\W\dA-Za-z_]", text):
            return Finding(self._statuses["latin"], "latin", values)
        return Finding(self._statuses["unformed"], "unformed", values)

    def _named(self, text: str, forms: tuple[str, ...]) -> bool:
        folded = text.casefold().replace("ё", "е")
        pattern = self._pattern(forms)
        return (
            bool(forms)
            and bool(re.search(pattern, folded))
            and bool(re.search(r"\w", re.sub(pattern, " ", folded)))
        )

    def _formed(self, text: str, forms: tuple[str, ...]) -> bool:
        return bool(forms) and bool(
            re.search(self._pattern(forms), text.casefold().replace("ё", "е"))
        )

    def _fused(self, text: str, forms: tuple[str, ...]) -> bool:
        return bool(forms) and bool(
            re.search(
                "|".join(
                    rf"(?<!\w)(?i:{re.escape(form.replace('ё', 'е'))})(?=[A-ZА-ЯЁ][a-zа-яё])"
                    for form in sorted(forms, key=len, reverse=True)
                ),
                text.replace("ё", "е"),
            )
        )

    def _pattern(self, forms: tuple[str, ...]) -> str:
        return "|".join(
            rf"(?<!\w){re.escape(form.casefold().replace('ё', 'е'))}(?!\w)"
            for form in sorted(forms, key=len, reverse=True)
        )
