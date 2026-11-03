from collections.abc import Iterable
from pathlib import Path
from typing import Final, Protocol, final

_POLICY = frozenset({"гп", "gp"})
_AMENDMENTS = frozenset({"дс", "ds"})
_CONDITIONS = frozenset({"особые условия", "special conditions"})
_CARRIERS = frozenset({"перевозчики", "carriers"})
_SERVICE = frozenset({"thumbs.db", "desktop.ini", ".ds_store"})


class Laid(Protocol):
    """Files of a policy folder sorted by what they are meant for, by place and not by content."""

    def policies(self) -> tuple[Path, ...]: ...

    def amendments(self) -> tuple[Path, ...]: ...

    def conditions(self) -> tuple[Path, ...]: ...

    def carriers(self) -> tuple[Path, ...]: ...


@final
class Layout:
    """Layout of a policy folder: policy files lie in the folder itself or in a subfolder GP.

    Amendments lie in the folder DS at any depth, special conditions and carriers in folders of
    their own. Names of folders are compared in any letter case. Thumbnails, lock files of the
    editor and hidden files are left out.
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root: Final = root

    def policies(self) -> tuple[Path, ...]:
        return self._kept(self._root.iterdir()) + tuple(
            path for folder in self._folders(_POLICY) for path in self._kept(folder.rglob("*"))
        )

    def amendments(self) -> tuple[Path, ...]:
        return self._within(_AMENDMENTS)

    def conditions(self) -> tuple[Path, ...]:
        return self._within(_CONDITIONS)

    def carriers(self) -> tuple[Path, ...]:
        return self._within(_CARRIERS)

    def _within(self, names: frozenset[str]) -> tuple[Path, ...]:
        return tuple(
            path for folder in self._folders(names) for path in self._kept(folder.rglob("*"))
        )

    def _folders(self, names: frozenset[str]) -> tuple[Path, ...]:
        return tuple(
            sorted(
                path
                for path in self._root.iterdir()
                if path.is_dir() and path.name.strip().casefold() in names
            )
        )

    def _kept(self, paths: Iterable[Path]) -> tuple[Path, ...]:
        return tuple(sorted(path for path in paths if path.is_file() and not self._service(path)))

    def _service(self, path: Path) -> bool:
        return path.name.startswith(("~$", ".")) or path.name.casefold() in _SERVICE
