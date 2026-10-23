from typing import Final, Protocol, final

from app.domain.clause import Clause
from app.domain.place import Place
from app.domain.verdict import Verdict


class Question(Protocol):
    """Request to judge one declared value against one policy clause by meaning."""

    def place(self) -> Place: ...

    def value(self) -> str: ...

    def clause(self) -> Clause: ...

    def rule(self) -> str: ...


@final
class Inquiry:
    """Question built by a semantic card for one shipment row."""

    __slots__ = ("_clause", "_place", "_rule", "_value")

    def __init__(self, place: Place, value: str, clause: Clause, rule: str) -> None:
        self._place: Final = place
        self._value: Final = value
        self._clause: Final = clause
        self._rule: Final = rule

    def place(self) -> Place:
        return self._place

    def value(self) -> str:
        return self._value

    def clause(self) -> Clause:
        return self._clause

    def rule(self) -> str:
        return self._rule


class Semantics(Protocol):
    """Judgement by meaning for fields whose card says check semantic, one batch per call."""

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]: ...
