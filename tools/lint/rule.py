from typing import Protocol

from tools.lint.script import Script


class Rule(Protocol):
    """Project convention that reports every place where a script breaks it."""

    def violations(self, script: Script) -> tuple[str, ...]: ...
