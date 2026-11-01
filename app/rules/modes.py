import re
from collections.abc import Mapping
from typing import Final, Protocol, final

from app.domain.clause import Clause
from app.domain.field import Field
from app.domain.policy import Policy
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Review
from app.rules.outcome import Finding, Outcome

_MIXED = "mixed"


class Kinds(Protocol):
    """Vocabulary that recognises modes of transport in a text and a mixed carriage."""

    def kinds(self, text: str) -> frozenset[str]: ...

    def mixed(self, text: str) -> bool: ...


@final
class Modes:
    """Kinds named by the words of a card: a mode is named when a word of it starts a word
    of the text; the key mixed marks a carriage declared as mixed in so many words."""

    __slots__ = ("_table",)

    def __init__(self, table: Mapping[str, tuple[str, ...]]) -> None:
        self._table: Final = table

    def kinds(self, text: str) -> frozenset[str]:
        return self._named(text) - {_MIXED}

    def mixed(self, text: str) -> bool:
        return _MIXED in self._named(text) or len(self.kinds(text)) > 1

    def _named(self, text: str) -> frozenset[str]:
        folded = text.casefold().replace("ё", "е")
        return frozenset(
            code
            for code, words in self._table.items()
            if any(re.search(rf"(?<!\w){re.escape(word.casefold())}", folded) for word in words)
        )


@final
class Conveyance:
    """Measure of a transport field: every mode it names is among the modes the clause names,
    and a field that names no mode at all needs a person."""

    __slots__ = ("_kinds",)

    def __init__(self, kinds: Kinds) -> None:
        self._kinds: Final = kinds

    def outcome(
        self, field: Field, clause: Clause, _shipment: Shipment, _policy: Policy
    ) -> Outcome:
        values = {"reference": clause.reference(), "entry": field.text()}
        declared = self._kinds.kinds(field.text())
        banned = declared - self._kinds.kinds(" ".join((clause.text(), *clause.entries())))
        if not declared:
            return Finding(Review(), "unrecognized", values)
        if banned:
            return Finding(Mismatch(), "unlisted", {**values, "entry": self._entry(field, banned)})
        return Finding(Match(), "listed", values)

    def _entry(self, field: Field, banned: frozenset[str]) -> str:
        return next(
            (entry for entry in field.entries() if self._kinds.kinds(entry) & banned),
            field.text(),
        )
