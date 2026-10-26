from collections.abc import Mapping, Sequence
from typing import Final, Protocol, final

from tools.eval.entry import Entry, Open
from tools.eval.fields import Target
from tools.eval.gold import Scale
from tools.eval.sheet import Mark


class Ruling(Protocol):
    """Decision of eval on one marked row, applied to the field the row was matched with."""

    def entry(self, mark: Mark, target: Target) -> Entry: ...


class Book(Protocol):
    """Rulings written down for remarks that are not a plain «верно»."""

    def ruling(self, shipment: str, field: str) -> Ruling: ...

    def unused(self, places: frozenset[tuple[str, str]]) -> tuple[str, ...]: ...


@final
class Silent:
    """No ruling: the target decides by the remark itself."""

    __slots__ = ()

    def entry(self, mark: Mark, target: Target) -> Entry:
        return target.default(mark)


@final
class Decided:
    """Ruling that gives the expected status, its basis and a note."""

    __slots__ = ("_basis", "_note", "_status")

    def __init__(self, status: str, basis: str, note: str) -> None:
        self._status: Final = status
        self._basis: Final = basis
        self._note: Final = note

    def entry(self, mark: Mark, target: Target) -> Entry:
        return target.settle(mark, (Scale().status(self._status).key(), self._basis, self._note))


@final
class Asked:
    """Ruling that sends the row to the questions with a reason and an offered answer."""

    __slots__ = ("_offer", "_reason")

    def __init__(self, reason: str, offer: str) -> None:
        self._reason: Final = reason
        self._offer: Final = offer

    def entry(self, mark: Mark, target: Target) -> Entry:
        return Open(mark, target.field(), self._reason, self._offer)


@final
class Rulings:
    """Rulings and broken shipment rows loaded from the gold settings of eval."""

    __slots__ = ("_broken", "_cases")

    def __init__(self, cases: Sequence[Mapping[str, str]], broken: Mapping[str, str]) -> None:
        self._cases: Final = cases
        self._broken: Final = broken

    def ruling(self, shipment: str, field: str) -> Ruling:
        if shipment in self._broken:
            return Asked(self._broken[shipment], "")
        found = tuple(
            case for case in self._cases if (case["shipment"], case["field"]) == (shipment, field)
        )
        if len(found) > 1:
            raise ValueError(f"Для строки {shipment} и поля {field} записано несколько решений")
        return self._ruling(found[0]) if found else Silent()

    def unused(self, places: frozenset[tuple[str, str]]) -> tuple[str, ...]:
        return tuple(
            f"{case['shipment']} × {case['field']}"
            for case in self._cases
            if (case["shipment"], case["field"]) not in places
        )

    def _ruling(self, case: Mapping[str, str]) -> Ruling:
        if "ask" in case:
            return Asked(case["ask"], case.get("offer", ""))
        return Decided(case["status"], case["basis"], case.get("note", ""))
