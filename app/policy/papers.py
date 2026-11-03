from datetime import date
from typing import Final, final

from app.policy.package import Paper


@final
class Opened:
    """Paper that is already read: the reference an expert can look up and the text of the file."""

    __slots__ = ("_reference", "_text")

    def __init__(self, reference: str, text: str) -> None:
        self._reference: Final = reference
        self._text: Final = text

    def reference(self) -> str:
        return self._reference

    def text(self) -> str:
        return self._text


@final
class Agreement:
    """Amendment made of a paper and the number, entry into force and scope that code read."""

    __slots__ = ("_effective", "_number", "_paper", "_scope")

    def __init__(self, paper: Paper, number: int, effective: date, scope: tuple[str, ...]) -> None:
        self._paper: Final = paper
        self._number: Final = number
        self._effective: Final = effective
        self._scope: Final = scope

    def reference(self) -> str:
        return self._paper.reference()

    def text(self) -> str:
        return self._paper.text()

    def number(self) -> int:
        return self._number

    def effective(self) -> date:
        return self._effective

    def scope(self) -> tuple[str, ...]:
        return self._scope
