from typing import Protocol

from app.domain.declaration import Declaration
from app.domain.policy import Policy
from app.domain.verdict import Verdict


class Card(Protocol):
    """Approved rule for one declaration field that turns a declaration into verdicts."""

    def field(self) -> str: ...

    def covers(self, form: str) -> bool: ...

    def title(self, form: str) -> str: ...

    def subject(self) -> str: ...

    def verdicts(self, declaration: Declaration, policy: Policy) -> tuple[Verdict, ...]: ...
