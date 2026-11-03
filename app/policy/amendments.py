from pathlib import Path, PurePosixPath
from typing import Final, final

from app.policy.opening import Opening
from app.policy.outcome import Outcome, Result
from app.policy.package import Amendment, Paper
from app.policy.signing import Signing
from app.policy.title import Title

_DOCUMENTS = frozenset({".doc", ".docx"})


@final
class Amendments:
    """Step that finds the signed amendments among the files of the folder of amendments.

    The title of a document tells an amendment from an attachment, and the file name does not.
    Two files with one number and different text are both left out and named in problems; a
    copy with the same text is taken once. A folder in which no amendment text was found is named
    in problems too.
    """

    __slots__ = ("_files", "_root")

    def __init__(self, files: tuple[Path, ...], root: Path) -> None:
        self._files: Final = files
        self._root: Final = root

    def survey(self) -> Outcome[Amendment]:
        opened = tuple(
            Opening(path, self._root).survey()
            for path in self._files
            if path.suffix.lower() in _DOCUMENTS
        )
        titled = tuple(
            paper
            for outcome in opened
            for paper in outcome.items()
            if Title(paper.text()).amendment()
        )
        signed = tuple(Signing(paper).survey() for paper in titled)
        groups = self._groups(tuple(item for outcome in signed for item in outcome.items()))
        return Result(
            tuple(group[0] for group in groups if self._copies(group)),
            tuple(problem for outcome in opened + signed for problem in outcome.problems())
            + tuple(self._conflict(group) for group in groups if not self._copies(group))
            + self._hollow(titled),
        )

    def _groups(self, found: tuple[Amendment, ...]) -> tuple[tuple[Amendment, ...], ...]:
        return tuple(
            tuple(item for item in found if item.number() == number)
            for number in sorted({item.number() for item in found})
        )

    def _copies(self, group: tuple[Amendment, ...]) -> bool:
        return len({item.text() for item in group}) == 1

    def _conflict(self, group: tuple[Amendment, ...]) -> str:
        names = ", ".join(item.reference() for item in group)
        return (
            f"ДС {group[0].number()} найдено в нескольких файлах с разным текстом ({names}),"
            " ни один не взят"
        )

    def _hollow(self, titled: tuple[Paper, ...]) -> tuple[str, ...]:
        folders = {PurePosixPath(paper.reference()).parent.as_posix() for paper in titled}
        return tuple(
            f"В папке {folder} не найден текст ДС"
            for folder in sorted(
                {path.parent.relative_to(self._root).as_posix() for path in self._files}
            )
            if not any(known == folder or known.startswith(f"{folder}/") for known in folders)
        )
