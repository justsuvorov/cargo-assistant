from typing import Final, Protocol, final


class Outcome[T](Protocol):
    """What a step of reading a policy folder found, and what it could not settle."""

    def items(self) -> tuple[T, ...]: ...

    def problems(self) -> tuple[str, ...]: ...


class Surveyed[T](Protocol):
    """Step of reading a policy folder whose result is an outcome."""

    def survey(self) -> Outcome[T]: ...


@final
class Result[T]:
    """Outcome that is already known: found items and problems for the expert."""

    __slots__ = ("_items", "_problems")

    def __init__(self, items: tuple[T, ...], problems: tuple[str, ...]) -> None:
        self._items: Final = items
        self._problems: Final = problems

    def items(self) -> tuple[T, ...]:
        return self._items

    def problems(self) -> tuple[str, ...]:
        return self._problems
