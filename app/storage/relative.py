from pathlib import PurePosixPath
from typing import Final, Protocol, final

from app.storage.errors import EscapeError


class Located(Protocol):
    """Path inside a folder that is known to stay inside it."""

    def path(self) -> str: ...

    def service(self) -> bool: ...


@final
class Relative:
    """Slash-separated path inside a policy folder; backslashes count as separators.

    An absolute path, a drive letter, a parent segment or a null byte lead out of the folder
    and are refused loudly.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: str) -> None:
        self._raw: Final = raw

    def path(self) -> str:
        text = self._raw.replace("\\", "/")
        parts = PurePosixPath(text).parts
        if not parts or text.startswith("/") or "\0" in text or ".." in parts or ":" in parts[0]:
            raise EscapeError(f"Путь {self._raw!r} выходит за каталог пакета")
        return "/".join(parts)

    def service(self) -> bool:
        return any(
            part.startswith(("~$", "."))
            or part.casefold() in {"thumbs.db", "desktop.ini"}
            or part == "__MACOSX"
            for part in self.path().split("/")
        )
