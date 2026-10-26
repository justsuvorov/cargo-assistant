from typing import Final, Protocol, final

from tools.eval.sheet import Mark


class Entry(Protocol):
    """What became of one marked MVP row: a gold line, a question or an exclusion."""

    def kind(self) -> str: ...

    def declaration(self) -> str: ...

    def field(self) -> str: ...

    def marked(self) -> bool: ...

    def cells(self) -> tuple[str, ...]: ...


@final
class Settled:
    """Gold line with an expected status, its basis and a short note written by eval."""

    __slots__ = ("_key", "_mark", "_verdict")

    def __init__(self, mark: Mark, key: str, verdict: tuple[str, str, str]) -> None:
        self._mark: Final = mark
        self._key: Final = key
        self._verdict: Final = verdict

    def kind(self) -> str:
        return "gold"

    def declaration(self) -> str:
        return self._mark.declaration()

    def field(self) -> str:
        return self._key

    def marked(self) -> bool:
        return bool(self._mark.remark())

    def cells(self) -> tuple[str, ...]:
        return (self._mark.declaration(), self._mark.shipment(), self._key, *self._verdict)


@final
class Open:
    """Question to the user or FSC: the row has no expected status that follows unambiguously."""

    __slots__ = ("_field", "_mark", "_offer", "_reason")

    def __init__(self, mark: Mark, field: str, reason: str, offer: str) -> None:
        self._mark: Final = mark
        self._field: Final = field
        self._reason: Final = reason
        self._offer: Final = offer

    def kind(self) -> str:
        return "question"

    def declaration(self) -> str:
        return self._mark.declaration()

    def field(self) -> str:
        return self._field

    def marked(self) -> bool:
        return bool(self._mark.remark())

    def cells(self) -> tuple[str, ...]:
        return (
            self._mark.declaration(),
            self._mark.shipment(),
            self._field,
            self._mark.answer(),
            self._mark.remark(),
            self._reason,
            self._offer,
        )


@final
class Dropped:
    """Row left out of the gold on purpose, such as a field that the form does not have."""

    __slots__ = ("_field", "_mark", "_reason")

    def __init__(self, mark: Mark, field: str, reason: str) -> None:
        self._mark: Final = mark
        self._field: Final = field
        self._reason: Final = reason

    def kind(self) -> str:
        return "excluded"

    def declaration(self) -> str:
        return self._mark.declaration()

    def field(self) -> str:
        return self._field

    def marked(self) -> bool:
        return bool(self._mark.remark())

    def cells(self) -> tuple[str, ...]:
        return (self._mark.declaration(), self._mark.shipment(), self._field, self._reason)
