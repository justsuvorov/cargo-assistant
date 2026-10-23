from typing import Final, Protocol, final

from app.domain.place import Place
from app.domain.reason import Reason
from app.domain.remark import Remark
from app.domain.status import Status


class Verdict(Protocol):
    """Result of checking one field of one shipment against the policy."""

    def place(self) -> Place: ...

    def status(self) -> Status: ...

    def reason(self) -> Reason: ...

    def remark(self) -> Remark: ...


@final
class Ruling:
    """Verdict assembled from its place, status, reason and remark."""

    __slots__ = ("_place", "_reason", "_remark", "_status")

    def __init__(self, place: Place, status: Status, reason: Reason, remark: Remark) -> None:
        self._place: Final = place
        self._status: Final = status
        self._reason: Final = reason
        self._remark: Final = remark

    def place(self) -> Place:
        return self._place

    def status(self) -> Status:
        return self._status

    def reason(self) -> Reason:
        return self._reason

    def remark(self) -> Remark:
        return self._remark
