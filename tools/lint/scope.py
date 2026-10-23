from typing import Final, final

from tools.lint.rule import Rule
from tools.lint.script import Script


@final
class Scoped:
    """Rule applied only to scripts that match an included glob and no excluded glob."""

    __slots__ = ("_exclude", "_include", "_rule")

    def __init__(self, rule: Rule, include: tuple[str, ...], exclude: tuple[str, ...]) -> None:
        self._rule: Final = rule
        self._include: Final = include
        self._exclude: Final = exclude

    def violations(self, script: Script) -> tuple[str, ...]:
        if any(map(script.matches, self._include)) and not any(map(script.matches, self._exclude)):
            return self._rule.violations(script)
        return ()
