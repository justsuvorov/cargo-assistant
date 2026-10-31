from collections.abc import Mapping
from typing import Final, final

from app.domain.declaration import Declaration
from app.domain.policy import Policy
from app.domain.verdict import Verdict
from app.rules.errors import CardError
from app.rules.rows import Check


@final
class Ruled:
    """Card read from a rule file: its field, its titles per form, the policy subject it is
    checked against and the check that turns a declaration into verdicts."""

    __slots__ = ("_check", "_field", "_subject", "_titles")

    def __init__(self, field: str, titles: Mapping[str, str], subject: str, check: Check) -> None:
        self._field: Final = field
        self._titles: Final = titles
        self._subject: Final = subject
        self._check: Final = check

    def field(self) -> str:
        return self._field

    def covers(self, form: str) -> bool:
        return form in self._titles

    def title(self, form: str) -> str:
        if form not in self._titles:
            raise CardError(f"Карточка {self._field} не относится к форме {form}")
        return self._titles[form]

    def subject(self) -> str:
        return self._subject

    def verdicts(self, declaration: Declaration, policy: Policy) -> tuple[Verdict, ...]:
        return self._check.verdicts(declaration, policy)
