from typing import Final, Protocol, final

from app.domain.place import Place
from app.domain.status import Status
from app.domain.verdict import Verdict


class GoldCase(Protocol):
    """Expected status of one result cell, confirmed by FSC experts."""

    def place(self) -> Place: ...

    def agrees(self, verdict: Verdict) -> bool: ...


@final
class Expectation:
    """Gold case that accepts a verdict with the expected status in the same place."""

    __slots__ = ("_place", "_status")

    def __init__(self, place: Place, status: Status) -> None:
        self._place: Final = place
        self._status: Final = status

    def place(self) -> Place:
        return self._place

    def agrees(self, verdict: Verdict) -> bool:
        return verdict.place().same(self._place) and (verdict.status().key() == self._status.key())
