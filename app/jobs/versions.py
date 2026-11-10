import hashlib
from pathlib import Path
from typing import Final, Protocol, final


class Versions(Protocol):
    """Versions of the code, the cards, the prompts and the model that a run was made with."""

    def code(self) -> str: ...

    def cards(self) -> str: ...

    def prompts(self) -> str: ...

    def model(self) -> str: ...


@final
class Stamp:
    """Versions fixed when the process starts and never changed afterwards."""

    __slots__ = ("_cards", "_code", "_model", "_prompts")

    def __init__(self, code: str, cards: str, prompts: str, model: str) -> None:
        self._code: Final = code
        self._cards: Final = cards
        self._prompts: Final = prompts
        self._model: Final = model

    def code(self) -> str:
        return self._code

    def cards(self) -> str:
        return self._cards

    def prompts(self) -> str:
        return self._prompts

    def model(self) -> str:
        return self._model


@final
class Fingerprint:
    """Short digest of the names and contents of the files in a folder, empty for a missing one."""

    __slots__ = ("_folder",)

    def __init__(self, folder: Path) -> None:
        self._folder: Final = folder

    def hex(self) -> str:
        if not self._folder.is_dir():
            return ""
        digest = hashlib.sha256()
        for path in sorted(self._folder.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(self._folder).as_posix().encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()[:12]
