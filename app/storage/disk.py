from pathlib import Path, PurePosixPath
from typing import Final, Protocol, final

from app.storage.errors import EscapeError


class Storage(Protocol):
    """Place that keeps files under slash-separated keys."""

    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def remove(self, key: str) -> None: ...


@final
class DiskStorage:
    """Storage on a local or shared volume that refuses keys leading out of its root."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root: Final = root.resolve()

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def remove(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if (
            ".." in PurePosixPath(key.replace("\\", "/")).parts
            or not path.is_relative_to(self._root)
            or path == self._root
        ):
            raise EscapeError(f"Ключ {key} выходит за корень хранилища")
        return path
