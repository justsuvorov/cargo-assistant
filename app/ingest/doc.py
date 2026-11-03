import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Final, Protocol, final

from app.domain.errors import UnreadableError
from app.ingest.book import Sheet
from app.ingest.docx import Docx

_HOME = Path(tempfile.gettempdir()) / "cargo-assistant-soffice"
_SLOTS = 4
_STALE = 300.0
_PAUSE = 0.05
_WAIT = 300.0
_FORMATS = (bytes.fromhex("D0CF11E0A1B11AE1"), b"{\\rtf", b"PK", b"<?xml")


class Leased(Protocol):
    """Pool of LibreOffice user profiles of which each is used by one conversion at a time."""

    def lease(self) -> AbstractContextManager[Path]: ...


class Warmable(Protocol):
    """Document that can be converted ahead of reading."""

    def warm(self) -> None: ...


@final
class Profiles:
    """Profiles of LibreOffice kept in a folder; a conversion takes a free one for its time.

    Two instances of LibreOffice must not share a profile: the second one hands its task to the
    first and fails. A profile is taken by creating the folder lock-N, which only one process or
    thread can do. A profile stays warm between conversions, because the first start of a new
    profile is the slow one. A lock older than five minutes is left by a dead process and is
    taken over.
    """

    __slots__ = ("_home", "_size")

    def __init__(self, home: Path = _HOME, size: int = _SLOTS) -> None:
        self._home: Final = home
        self._size: Final = size

    @contextmanager
    def lease(self) -> Iterator[Path]:
        self._home.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + _WAIT
        while time.monotonic() < deadline:
            for slot in range(self._size):
                lock = self._home / f"lock-{slot}"
                if self._taken(lock):
                    try:
                        yield self._home / f"profile-{slot}"
                    finally:
                        lock.rmdir()
                    return
            time.sleep(_PAUSE)
        raise UnreadableError("Нет свободного профиля LibreOffice для преобразования файла")

    def _taken(self, lock: Path) -> bool:
        try:
            lock.mkdir()
        except FileExistsError:
            if time.time() - lock.stat().st_mtime > _STALE:
                shutil.rmtree(lock, ignore_errors=True)
            return False
        return True


@final
class Doc:
    """Book read from a legacy doc file after LibreOffice in headless mode converts it to docx.

    The converted file is kept by the digest of the source, so the same document is converted
    once, and warm lets several documents be converted in parallel before they are read. Each
    conversion runs on its own LibreOffice profile.
    """

    __slots__ = ("_command", "_home", "_path")

    def __init__(self, path: Path, command: str = "soffice", home: Path = _HOME) -> None:
        self._path: Final = path
        self._command: Final = command
        self._home: Final = home

    def sheets(self) -> tuple[Sheet, ...]:
        return Docx(self._converted()).sheets()

    def warm(self) -> None:
        self._converted()

    def _converted(self) -> Path:
        data = self._path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        cached = self._home / "cache" / f"{digest}.docx"
        if cached.is_file():
            return cached
        program = shutil.which(self._command)
        if not program:
            raise UnreadableError(
                f"Файл {self._path.name} нельзя прочитать, потому что LibreOffice не установлен"
            )
        if not data.startswith(_FORMATS):
            raise UnreadableError(f"Файл {self._path.name} не является документом Word")
        cached.parent.mkdir(parents=True, exist_ok=True)
        with (
            tempfile.TemporaryDirectory() as folder,
            Profiles(self._home / "profiles").lease() as profile,
        ):
            self._convert(program, folder, profile)
            ready = Path(folder) / f"{self._path.stem}.docx"
            if not ready.is_file():
                raise UnreadableError(
                    f"Файл {self._path.name} не удалось преобразовать через LibreOffice"
                )
            partial = cached.with_name(f"{cached.name}.{os.getpid()}.part")
            shutil.copyfile(ready, partial)
            partial.replace(cached)
        return cached

    def _convert(self, program: str, folder: str, profile: Path) -> None:
        try:
            subprocess.run(
                [
                    program,
                    f"-env:UserInstallation={profile.as_uri()}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "docx",
                    "--outdir",
                    folder,
                    str(self._path),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except (subprocess.SubprocessError, OSError) as error:
            raise UnreadableError(
                f"Файл {self._path.name} не удалось преобразовать через LibreOffice"
            ) from error
