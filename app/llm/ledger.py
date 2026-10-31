import threading
from typing import Final, Protocol, final


class Origin(Protocol):
    """Provider and model that served a call."""

    def provider(self) -> str: ...

    def model(self) -> str: ...


@final
class Route:
    """Origin named by the settings of the client."""

    __slots__ = ("_model", "_provider")

    def __init__(self, provider: str, model: str) -> None:
        self._provider: Final = provider
        self._model: Final = model

    def provider(self) -> str:
        return self._provider

    def model(self) -> str:
        return self._model


class Outcome(Protocol):
    """What one call cost and whether its answer passed the schema."""

    def spent(self) -> tuple[int, int]: ...

    def latency(self) -> float: ...

    def valid(self) -> bool: ...


@final
class Measured:
    """Outcome measured by the client around one request to the provider."""

    __slots__ = ("_latency", "_spent", "_valid")

    def __init__(self, spent: tuple[int, int], latency: float, *, valid: bool) -> None:
        self._spent: Final = spent
        self._latency: Final = latency
        self._valid: Final = valid

    def spent(self) -> tuple[int, int]:
        return self._spent

    def latency(self) -> float:
        return self._latency

    def valid(self) -> bool:
        return self._valid


class Call(Protocol):
    """Record of one request to the model: why it was made, where, what and how it ended."""

    def purpose(self) -> str: ...

    def origin(self) -> Origin: ...

    def digest(self) -> str: ...

    def outcome(self) -> Outcome: ...


@final
class Logged:
    """Call as the client records it."""

    __slots__ = ("_digest", "_origin", "_outcome", "_purpose")

    def __init__(self, purpose: str, origin: Origin, digest: str, outcome: Outcome) -> None:
        self._purpose: Final = purpose
        self._origin: Final = origin
        self._digest: Final = digest
        self._outcome: Final = outcome

    def purpose(self) -> str:
        return self._purpose

    def origin(self) -> Origin:
        return self._origin

    def digest(self) -> str:
        return self._digest

    def outcome(self) -> Outcome:
        return self._outcome


class Ledger(Protocol):
    """Account of every call to the model."""

    def record(self, call: Call) -> None: ...


class History(Protocol):
    """Calls that a ledger has seen, in the order they were recorded."""

    def calls(self) -> tuple[Call, ...]: ...


@final
class Memory:
    """Ledger kept in the memory of the process and safe to share between threads."""

    __slots__ = ("_calls", "_lock")

    def __init__(self) -> None:
        self._calls: Final[list[Call]] = []
        self._lock: Final = threading.Lock()

    def record(self, call: Call) -> None:
        with self._lock:
            self._calls.append(call)

    def calls(self) -> tuple[Call, ...]:
        with self._lock:
            return tuple(self._calls)
