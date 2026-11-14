from pathlib import Path
from typing import Final, Protocol, final

from app.policy.layout import Layout
from app.policy.listing import Listing
from app.policy.outcome import Outcome


class Written(Protocol):
    """Special conditions file of the client as it is kept with the session."""

    def file(self) -> str: ...

    def chosen(self) -> bool: ...

    def lines(self) -> tuple[str, ...]: ...

    def problems(self) -> tuple[str, ...]: ...


@final
class Kept:
    """Special conditions file of the client read once, so that it outlives the folder it was
    read from."""

    __slots__ = ("_chosen", "_file", "_lines", "_problems")

    def __init__(self, found: Written) -> None:
        self._file: Final = found.file()
        self._chosen: Final = found.chosen()
        self._lines: Final = found.lines()
        self._problems: Final = found.problems()

    def file(self) -> str:
        return self._file

    def chosen(self) -> bool:
        return self._chosen

    def lines(self) -> tuple[str, ...]:
        return self._lines

    def problems(self) -> tuple[str, ...]:
        return self._problems


@final
class Clients:
    """Special conditions of the client: the file chosen apart from the folder when there is
    one, otherwise the files of the folder of special conditions. It tells the file that was
    taken, whether it was chosen, its non-blank lines and what could not be read."""

    __slots__ = ("_chosen", "_folder")

    def __init__(self, folder: Path, chosen: Path) -> None:
        self._folder: Final = folder
        self._chosen: Final = chosen

    def file(self) -> str:
        files, root = self._files()
        return ", ".join(path.relative_to(root).as_posix() for path in files)

    def chosen(self) -> bool:
        return bool(self._own())

    def lines(self) -> tuple[str, ...]:
        return self._read().items()

    def problems(self) -> tuple[str, ...]:
        return self._read().problems()

    def _own(self) -> tuple[Path, ...]:
        return tuple(sorted(path for path in self._chosen.rglob("*") if path.is_file()))

    def _files(self) -> tuple[tuple[Path, ...], Path]:
        own = self._own()
        return (own, self._chosen) if own else (Layout(self._folder).conditions(), self._folder)

    def _read(self) -> Outcome[str]:
        files, root = self._files()
        return Listing(files, root).survey()
