from typing import Final, Protocol, final

from app.policy.package import Amendment, Paper


class Extras(Protocol):
    """Special conditions and carriers of a policy, one entry per line of their files."""

    def conditions(self) -> tuple[str, ...]: ...

    def carriers(self) -> tuple[str, ...]: ...


@final
class Listed:
    """Special conditions and carriers that are already read."""

    __slots__ = ("_carriers", "_conditions")

    def __init__(self, conditions: tuple[str, ...], carriers: tuple[str, ...]) -> None:
        self._conditions: Final = conditions
        self._carriers: Final = carriers

    def conditions(self) -> tuple[str, ...]:
        return self._conditions

    def carriers(self) -> tuple[str, ...]:
        return self._carriers


@final
class Assembled:
    """Package of a policy whose parts are already read, with the problems found on the way."""

    __slots__ = ("_amendments", "_extras", "_policy", "_problems")

    def __init__(
        self,
        policy: Paper,
        amendments: tuple[Amendment, ...],
        extras: Extras,
        problems: tuple[str, ...],
    ) -> None:
        self._policy: Final = policy
        self._amendments: Final = amendments
        self._extras: Final = extras
        self._problems: Final = problems

    def policy(self) -> Paper:
        return self._policy

    def amendments(self) -> tuple[Amendment, ...]:
        return self._amendments

    def conditions(self) -> tuple[str, ...]:
        return self._extras.conditions()

    def carriers(self) -> tuple[str, ...]:
        return self._extras.carriers()

    def problems(self) -> tuple[str, ...]:
        return self._problems
