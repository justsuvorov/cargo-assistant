import re
from collections.abc import Mapping
from typing import Final, final

from app.domain.clause import Clause
from app.domain.field import Field
from app.domain.numbers import Numbered
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Review
from app.rules.outcome import Finding, Outcome, Worst


@final
class Exact:
    """Measure that a field repeats the clause character by character, ignoring spaces and
    the characters of the card; with parts, the number is a run of words of the field and
    the date of the clause is among the dates of the field."""

    __slots__ = ("_ignore", "_parts")

    def __init__(self, parts: tuple[str, ...], ignore: tuple[str, ...]) -> None:
        self._parts: Final = parts
        self._ignore: Final = ignore

    def outcome(
        self, field: Field, clause: Clause, _shipment: Shipment, _policy: Policy
    ) -> Outcome:
        values = {"reference": clause.reference(), "entry": field.text()}
        checks = {"number": self._number, "date": self._date, "whole": self._whole}
        return Worst(
            tuple(checks[part](field, clause, values) for part in self._parts or ("whole",))
        )

    def _number(self, field: Field, clause: Clause, values: Mapping[str, str]) -> Outcome:
        numbers = Numbered(self._ignore)
        if numbers.blank(clause.text()):
            return Finding(Review(), "unreadable", values)
        return self._verdict(values, same=numbers.same(field.text(), clause.text()))

    def _date(self, field: Field, clause: Clause, values: Mapping[str, str]) -> Outcome:
        if not field.dates() or not clause.dates():
            return Finding(Review(), "unreadable", values)
        return self._verdict(values, same=clause.dates()[0] in field.dates())

    def _whole(self, field: Field, clause: Clause, values: Mapping[str, str]) -> Outcome:
        return self._verdict(
            values,
            same=re.sub(r"\s", "", self._stripped(field.text()))
            == re.sub(r"\s", "", self._stripped(clause.text())),
        )

    def _stripped(self, text: str) -> str:
        return "".join(" " if char in self._ignore else char for char in text)

    def _verdict(self, values: Mapping[str, str], *, same: bool) -> Outcome:
        if same:
            return Finding(Match(), "same", values)
        return Finding(Mismatch(), "different", values)
