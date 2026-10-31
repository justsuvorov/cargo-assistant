from typing import Final, Protocol, final

from app.domain.clause import Clause


class Presence(Protocol):
    """Answer whether a policy clause is stated in the profile at all."""

    def exists(self) -> bool: ...


@final
class Stated:
    """Presence of a clause that holds some text, date, sum or item; Absent holds none."""

    __slots__ = ("_clause",)

    def __init__(self, clause: Clause) -> None:
        self._clause: Final = clause

    def exists(self) -> bool:
        return bool(
            self._clause.text()
            or self._clause.dates()
            or self._clause.amounts()
            or self._clause.entries()
        )
