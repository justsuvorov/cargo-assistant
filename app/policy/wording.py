import re
from datetime import date
from itertools import groupby
from typing import Final, Protocol, final

from app.domain.clause import Absent, Clause
from app.domain.errors import UnreadableError
from app.domain.money import Amount, Money
from app.domain.revision import Revision
from app.domain.shipment import Shipment
from app.policy.schema.profile import Sum, Wording


class Choice(Protocol):
    """Revisions of one clause that answer about a shipment with the clause in force for it."""

    def clause(self, shipment: Shipment) -> Clause: ...


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
class Gathered:
    """Policy clause made of several wordings in the order given; it names every source and
    gives each date, sum and entry once."""

    __slots__ = ("_wordings",)

    def __init__(self, wordings: tuple[Wording, ...]) -> None:
        self._wordings: Final = wordings

    def reference(self) -> str:
        return _sources(self._wordings)

    def text(self) -> str:
        return "\n".join(each.text for each in self._wordings if each.text)

    def dates(self) -> tuple[date, ...]:
        return _days(self._wordings)

    def amounts(self) -> tuple[Money, ...]:
        return tuple(Amount(each.value, each.currency) for each in _sums(self._wordings))

    def entries(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(entry for each in self._wordings for entry in each.entries))


@final
class Edition:
    """Revision read from one wording of a clause; the only home of the choice rule D-33.

    It concerns a shipment when its scope names the declaration of the shipment by digits
    (D-30) or every declaration; an empty scope means the same as in a package amendment. The
    wording of the policy itself, amendment 0, governs on any date, so that a shipment outside
    the term reaches the card; an amendment governs from the day it takes effect, and an
    unreadable start of the shipment raises UnreadableError. Dates in the text do not end a
    revision: only a superseding one does, and the term of the policy is the business of a card.

    An edition replaces only its own point and those nested in it, and an empty point stands
    for the whole clause, so that neighbouring points and the point around it stay. Among those
    an edition to named declarations supersedes a general one; within one group the later date
    wins, then the greater amendment number. The contract shows another revision only through
    its clause, so the other one is found among the peers, the wordings of the same clause, by
    its reference; a revision outside the peers or a source that several wordings share is not
    superseded unless the edition outranks and covers them all, so that the choice stays with a
    person.
    """

    __slots__ = ("_peers", "_wording")

    def __init__(self, wording: Wording, peers: tuple[Wording, ...]) -> None:
        self._wording: Final = wording
        self._peers: Final = peers

    def governs(self, shipment: Shipment) -> bool:
        return self._concerns(shipment.declaration()) and (
            self._wording.amendment == 0 or self._wording.effective <= shipment.start()
        )

    def supersedes(self, other: Revision) -> bool:
        reference = other.clause().reference()
        namesakes = tuple(peer for peer in self._peers if peer.source == reference)
        return bool(namesakes) and all(
            _rank(peer) < _rank(self._wording) and _covers(self._wording, peer)
            for peer in namesakes
        )

    def clause(self) -> Clause:
        return Quoted(self._wording)

    def _concerns(self, declaration: str) -> bool:
        scope = self._wording.scope
        if scope == "all" or not scope:
            return True
        return bool(_figures(declaration)) and _figures(declaration) in map(_figures, scope)


@final
class Editions:
    """Wordings of one clause that give the clause in force for a shipment.

    The clause gathers, in the order of points, every wording that governs the shipment and that
    no other governing one supersedes; it is absent when none governs. UnreadableError says that
    a person has to choose: when two wordings of one point stay equal, when a point is no number,
    when a limit holds several sums of one currency or a term more than a start and an end, since
    a card would otherwise compare a value with an arbitrary one of them.
    """

    __slots__ = ("_key", "_wordings")

    def __init__(self, key: str, wordings: tuple[Wording, ...]) -> None:
        self._key: Final = key
        self._wordings: Final = wordings

    def clause(self, shipment: Shipment) -> Clause:
        standing = tuple(sorted(self._standing(shipment), key=_order))
        if not standing:
            return Absent(self._key)
        doubts = (*self._rivals(standing), *self._excess(standing))
        if doubts:
            raise UnreadableError(doubts[0])
        return Gathered(standing)

    def _standing(self, shipment: Shipment) -> tuple[Wording, ...]:
        editions = tuple((each, Edition(each, self._wordings)) for each in self._wordings)
        governing = tuple(pair for pair in editions if pair[1].governs(shipment))
        return tuple(
            wording
            for wording, edition in governing
            if not any(other.supersedes(edition) for _, other in governing if other is not edition)
        )

    def _rivals(self, standing: tuple[Wording, ...]) -> tuple[str, ...]:
        return tuple(
            f"У пункта «{self._key}» равноправные редакции: {_sources(group)}"
            for group in (tuple(same) for _, same in groupby(standing, key=_order))
            if len(group) > 1
        )

    def _excess(self, standing: tuple[Wording, ...]) -> tuple[str, ...]:
        sums = _sums(standing)
        excess, problem = {
            "limit": (
                len(sums) > len({each.currency for each in sums}),
                "несколько сумм в одной валюте",
            ),
            "term": (len(_days(standing)) > len(("start", "end")), "больше двух дат"),
        }.get(self._key, (False, ""))
        return (f"У пункта «{self._key}» {problem}: {_sources(standing)}",) if excess else ()


def _rank(wording: Wording) -> tuple[bool, date, int]:
    named = wording.scope != "all" and bool(wording.scope)
    return (named, wording.effective, wording.amendment)


def _covers(outer: Wording, inner: Wording) -> bool:
    parts = _order(outer)
    return _order(inner)[: len(parts)] == parts


def _order(wording: Wording) -> tuple[int, ...]:
    bare = wording.point.strip().rstrip(".")
    if bare and not re.fullmatch(r"\d+(\.\d+)*", bare):
        raise UnreadableError(f"Номер подпункта «{wording.point}» нельзя разобрать")
    return tuple(int(part) for part in bare.split(".") if part)


def _sources(wordings: tuple[Wording, ...]) -> str:
    return ", ".join(dict.fromkeys(each.source for each in wordings))


def _days(wordings: tuple[Wording, ...]) -> tuple[date, ...]:
    return tuple(dict.fromkeys(day for each in wordings for day in each.dates))


def _sums(wordings: tuple[Wording, ...]) -> tuple[Sum, ...]:
    return tuple(dict.fromkeys(amount for each in wordings for amount in each.amounts))


def _figures(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return digits.lstrip("0") or digits[:1]
