from pathlib import Path
from typing import Final, final

from app.policy.opening import Opening
from app.policy.outcome import Outcome, Result


@final
class Listing:
    """Step that reads files with special conditions or carriers into non-blank lines.

    Each line is one entry. A file that is not read or has no text is named in problems.
    """

    __slots__ = ("_files", "_root")

    def __init__(self, files: tuple[Path, ...], root: Path) -> None:
        self._files: Final = files
        self._root: Final = root

    def survey(self) -> Outcome[str]:
        opened = tuple(Opening(path, self._root).survey() for path in self._files)
        return Result(
            tuple(
                line.strip()
                for outcome in opened
                for paper in outcome.items()
                for line in paper.text().splitlines()
                if line.strip()
            ),
            tuple(problem for outcome in opened for problem in outcome.problems()),
        )
