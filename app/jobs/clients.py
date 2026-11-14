from pathlib import Path
from typing import Any, Final, Protocol, final

from app.policy.layout import Layout
from app.policy.listing import Listing


class Written(Protocol):
    """Special conditions file of the client as a record kept with the session."""

    def record(self) -> dict[str, Any]: ...


@final
class Clients:
    """Special conditions of the client: the file chosen apart from the folder when there is
    one, otherwise the files of the folder of special conditions. The record tells the file that
    was taken, whether it was chosen, its non-blank lines and what could not be read."""

    __slots__ = ("_chosen", "_folder")

    def __init__(self, folder: Path, chosen: Path) -> None:
        self._folder: Final = folder
        self._chosen: Final = chosen

    def record(self) -> dict[str, Any]:
        own = tuple(sorted(path for path in self._chosen.rglob("*") if path.is_file()))
        files, root = (own, self._chosen) if own else (Layout(self._folder).conditions(), self._folder)
        read = Listing(files, root).survey()
        return {
            "file": ", ".join(path.relative_to(root).as_posix() for path in files),
            "chosen": bool(own),
            "lines": list(read.items()),
            "problems": list(read.problems()),
        }
