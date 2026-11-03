from pathlib import Path
from typing import Final, final

from app.domain.errors import UnreadableError
from app.policy.opening import Opening
from app.policy.outcome import Outcome, Result
from app.policy.package import Paper
from app.policy.title import Title

_DOCUMENTS = frozenset({".doc", ".docx"})
_SCANS = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"})


@final
class Policies:
    """Step that finds the text of the general policy among the files of a policy folder.

    The first line of a document tells the policy from its attachments, and the file name does
    not. With several candidates the longest text is taken and all of them are named in problems.
    A folder without a policy text is an error: scans are named in it, as they are not read.
    """

    __slots__ = ("_files", "_root")

    def __init__(self, files: tuple[Path, ...], root: Path) -> None:
        self._files: Final = files
        self._root: Final = root

    def survey(self) -> Outcome[Paper]:
        opened = tuple(
            Opening(path, self._root).survey()
            for path in self._files
            if path.suffix.lower() in _DOCUMENTS
        )
        problems = tuple(problem for outcome in opened for problem in outcome.problems())
        found = tuple(
            paper for outcome in opened for paper in outcome.items() if Title(paper.text()).policy()
        )
        if not found:
            raise UnreadableError(self._lack(problems))
        best = max(found, key=lambda paper: len(paper.text()))
        return Result((best,), problems + self._several(found, best))

    def _several(self, found: tuple[Paper, ...], best: Paper) -> tuple[str, ...]:
        names = ", ".join(paper.reference() for paper in found)
        return (
            (
                f"Найдено несколько кандидатов на ГП ({names}),"
                f" взят самый длинный: {best.reference()}",
            )
            if len(found) > 1
            else ()
        )

    def _lack(self, problems: tuple[str, ...]) -> str:
        scans = tuple(path.name for path in self._files if path.suffix.lower() in _SCANS)
        return "; ".join(
            (
                "В папке полиса не найден текст Генерального полиса",
                *problems,
                *((f"сканы не читаются: {', '.join(scans)}",) if scans else ()),
            )
        )
