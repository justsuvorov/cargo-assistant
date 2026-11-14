from typing import Final, Protocol, final

from app.storage.archive import Blob, Stored
from app.storage.relative import Relative


class Folder(Protocol):
    """Files of a policy package under the paths they have inside the policy folder, and the
    name of the folder that wrapped them, blank when none did."""

    def files(self) -> tuple[Stored, ...]: ...

    def name(self) -> str: ...


@final
class Tree:
    """Uploaded files with checked paths, service files dropped and the one wrapping folder cut.

    A folder chosen in a browser or packed into an archive brings its own name in front of every
    path; when all files share it, it is not part of the package layout and is removed.
    """

    __slots__ = ("_files",)

    def __init__(self, files: tuple[Stored, ...]) -> None:
        self._files: Final = files

    def files(self) -> tuple[Stored, ...]:
        kept, wrapped = self._kept()
        return tuple(
            Blob(path.path().split("/", 1)[1] if wrapped else path.path(), file.data())
            for path, file in kept
        )

    def name(self) -> str:
        kept, wrapped = self._kept()
        return kept[0][0].path().split("/")[0] if kept and wrapped else ""

    def _kept(self) -> tuple[tuple[tuple[Relative, Stored], ...], bool]:
        kept = tuple(
            (path, file)
            for file in self._files
            for path in (Relative(file.name()),)
            if not path.service()
        )
        tops = {path.path().split("/")[0] for path, _ in kept}
        return kept, len(tops) == 1 and all("/" in path.path() for path, _ in kept)
