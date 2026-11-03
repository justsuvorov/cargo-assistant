from pathlib import Path
from typing import Final, final

from app.domain.errors import UnreadableError
from app.policy.contents import Contents
from app.policy.outcome import Outcome, Result
from app.policy.package import Paper
from app.policy.papers import Opened


@final
class Opening:
    """Step that reads one file into a paper, or names the file in problems.

    A file that cannot be read and a document without text are not guessed at: the expert sees
    them in problems with the path that is relative to the policy folder.
    """

    __slots__ = ("_path", "_root")

    def __init__(self, path: Path, root: Path) -> None:
        self._path: Final = path
        self._root: Final = root

    def survey(self) -> Outcome[Paper]:
        reference = self._path.relative_to(self._root).as_posix()
        try:
            text = Contents(self._path).text()
        except UnreadableError as error:
            return Result((), (f"{error} ({reference})",))
        return (
            Result((Opened(reference, text),), ())
            if text.strip()
            else Result((), (f"Документ {self._path.name} пустой, текста нет",))
        )
