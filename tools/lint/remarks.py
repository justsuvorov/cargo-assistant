import re
from typing import Final, final

from tools.lint.script import Script


@final
class Remarks:
    """Rule that the only comments in code are puzzles in the agreed format."""

    __slots__ = ("_puzzle",)

    def __init__(self, puzzle: str) -> None:
        self._puzzle: Final = puzzle

    def violations(self, script: Script) -> tuple[str, ...]:
        return tuple(
            script.mark(line, f"Комментарий не является пазлом в формате PDD: {text}")
            for line, text in script.comments()
            if not re.fullmatch(self._puzzle, text)
        )
