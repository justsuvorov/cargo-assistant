import re
from typing import Final, Protocol, final

from app.domain.place import Place
from app.domain.reason import Reason
from app.domain.remark import Remark
from app.domain.status import Status
from app.domain.verdict import Verdict


class Ordinal(Protocol):
    """Number of a declaration or a shipment row in the form in which eval compares numbers."""

    def text(self) -> str: ...


@final
class Digits:
    """Number reduced to its digits without leading zeros, part by part around slashes (D-30)."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def text(self) -> str:
        return "/".join(self._part(part) for part in self._text.split("/"))

    def _part(self, part: str) -> str:
        digits = re.sub(r"\D", "", part)
        if not digits:
            return " ".join(part.casefold().split())
        return digits.lstrip("0") or "0"


@final
class Canonical:
    """Place that keeps its written shipment number but compares numbers by their digits."""

    __slots__ = ("_place",)

    def __init__(self, place: Place) -> None:
        self._place: Final = place

    def shipment(self) -> str:
        return self._place.shipment()

    def field(self) -> str:
        return self._place.field()

    def same(self, other: Place) -> bool:
        return other.field() == self._place.field() and (
            Digits(other.shipment()).text() == Digits(self._place.shipment()).text()
        )


@final
class Aligned:
    """Verdict of a pipeline whose place compares shipment numbers by their digits."""

    __slots__ = ("_verdict",)

    def __init__(self, verdict: Verdict) -> None:
        self._verdict: Final = verdict

    def place(self) -> Place:
        return Canonical(self._verdict.place())

    def status(self) -> Status:
        return self._verdict.status()

    def reason(self) -> Reason:
        return self._verdict.reason()

    def remark(self) -> Remark:
        return self._verdict.remark()
