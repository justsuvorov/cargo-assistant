from datetime import date
from typing import Protocol


class Paper(Protocol):
    """Readable document of a policy package with a reference that an expert can look up."""

    def reference(self) -> str: ...

    def text(self) -> str: ...


class Amendment(Paper, Protocol):
    """Signed amendment whose number, entry into force and declarations are read by code.

    An empty scope means that the amendment concerns every declaration of the policy.
    """

    def number(self) -> int: ...

    def effective(self) -> date: ...

    def scope(self) -> tuple[str, ...]: ...


class Package(Protocol):
    """Documents of one policy told apart by their content, and what could not be settled.

    Each file that was left out and may matter, such as a draft amendment or a scan without
    text, is named in problems, so that the expert sees it before approving the profile.
    """

    def policy(self) -> Paper: ...

    def amendments(self) -> tuple[Amendment, ...]: ...

    def conditions(self) -> tuple[str, ...]: ...

    def carriers(self) -> tuple[str, ...]: ...

    def problems(self) -> tuple[str, ...]: ...
