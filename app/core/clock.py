from datetime import UTC, datetime
from typing import Protocol, final


class Clock(Protocol):
    """Source of the current moment."""

    def now(self) -> datetime: ...


@final
class Utc:
    """Clock that returns the current UTC time without a zone, as the database stores it."""

    __slots__ = ()

    def now(self) -> datetime:
        now = datetime.now(UTC)
        return datetime.combine(now.date(), now.time())
