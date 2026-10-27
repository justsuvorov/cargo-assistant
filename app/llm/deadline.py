import time
from typing import Final, Protocol, final


class Deadline(Protocol):
    """Limit on the total time that all attempts of one answer may take."""

    def left(self) -> float: ...


@final
class Countdown:
    """Deadline that starts when it is created and runs on the monotonic clock."""

    __slots__ = ("_end",)

    def __init__(self, seconds: float) -> None:
        self._end: Final = time.monotonic() + seconds

    def left(self) -> float:
        return max(0.0, self._end - time.monotonic())


class Cadence(Protocol):
    """How many times something is tried and how long to wait between the tries."""

    def attempts(self) -> int: ...

    def pause(self) -> float: ...


@final
class Rhythm:
    """Cadence with a fixed number of attempts and a fixed pause."""

    __slots__ = ("_attempts", "_pause")

    def __init__(self, attempts: int, pause: float) -> None:
        self._attempts: Final = attempts
        self._pause: Final = pause

    def attempts(self) -> int:
        return self._attempts

    def pause(self) -> float:
        return self._pause
