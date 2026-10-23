from typing import Protocol, final


class Status(Protocol):
    """Outcome of one field check, as an expert reads it in the result."""

    def key(self) -> str: ...

    def text(self) -> str: ...


@final
class Match:
    """Status of a declared field that agrees with the policy."""

    __slots__ = ()

    def key(self) -> str:
        return "match"

    def text(self) -> str:
        return "совпадает"


@final
class Mismatch:
    """Status of a declared field that contradicts the policy or is missing."""

    __slots__ = ()

    def key(self) -> str:
        return "mismatch"

    def text(self) -> str:
        return "не совпадает"


@final
class Review:
    """Status of a declared field that the system cannot decide without a person."""

    __slots__ = ()

    def key(self) -> str:
        return "review"

    def text(self) -> str:
        return "требует проверки"
