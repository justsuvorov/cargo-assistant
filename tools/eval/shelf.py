from collections.abc import Mapping
from pathlib import Path
from typing import Final, Protocol, final

from app.declarations.declared import Declared
from app.domain.errors import UnreadableError
from app.ingest.source import Source
from tools.eval.number import Digits

_SUFFIXES = frozenset({".xls", ".xlsx", ".xlsm", ".doc", ".docx"})
_SKIPPED = ("результат проверки", "разметка")


@final
class AbsentError(LookupError):
    """Declaration that the folder of real declarations has no single readable file for."""

    __slots__ = ()


class Library(Protocol):
    """Files of real declarations found by the number that each declaration states in its header."""

    def path(self, declaration: str) -> Path: ...


class Archive(Protocol):
    """Folder of real declarations that eval reads once and then looks files up in."""

    def catalog(self) -> Library: ...


@final
class Catalog:
    """Library made of declaration files indexed by the digits of their numbers (D-30)."""

    __slots__ = ("_paths", "_root", "_unread")

    def __init__(
        self, root: Path, paths: Mapping[str, tuple[Path, ...]], unread: tuple[str, ...]
    ) -> None:
        self._root: Final = root
        self._paths: Final = paths
        self._unread: Final = unread

    def path(self, declaration: str) -> Path:
        found = self._paths.get(Digits(declaration).text(), ())
        if len(found) > 1:
            raise AbsentError(
                f"Декларации {declaration} в каталоге {self._root} соответствует несколько "
                f"файлов: {', '.join(path.name for path in found)}"
            )
        if not found:
            raise AbsentError(
                f"Файл декларации {declaration} не найден в каталоге {self._root}"
                + (f"; не прочитаны файлы: {', '.join(self._unread)}" if self._unread else "")
            )
        return found[0]


@final
class Shelf:
    """Archive of declaration files in a folder and its subfolders, without result sheets."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root: Final = root

    def catalog(self) -> Library:
        if not self._root.is_dir():
            raise FileNotFoundError(
                f"Каталог реальных деклараций {self._root} не найден: укажите --real "
                f"или переменную окружения EVAL_REAL_DIR"
            )
        paths: dict[str, tuple[Path, ...]] = {}
        unread: list[str] = []
        for path in self._files():
            try:
                number = Digits(Declared(Source(path)).number()).text()
            except UnreadableError as error:
                unread.append(f"{path.name} ({error})")
                continue
            paths[number] = (*paths.get(number, ()), path)
        return Catalog(self._root, paths, tuple(unread))

    def _files(self) -> tuple[Path, ...]:
        return tuple(
            path
            for path in sorted(self._root.rglob("*"))
            if path.is_file()
            and path.suffix.lower() in _SUFFIXES
            and not path.name.startswith("~$")
            and not any(word in path.name.casefold() for word in _SKIPPED)
        )
