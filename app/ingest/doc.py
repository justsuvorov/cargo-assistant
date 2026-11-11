import hashlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final, Protocol, final

from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.domain.errors import UnreadableError
from app.ingest.book import Sheet
from app.ingest.docx import Docx

_HOME = EnvSettings(Environment()).soffice()
_SLOTS = 4
_STALE = 300.0
_PAUSE = 0.05
_WAIT = 300.0
_LIMIT = 120.0
_FORMATS = (bytes.fromhex("D0CF11E0A1B11AE1"), b"{\\rtf", b"PK", b"<?xml")


class Leased(Protocol):
    """Pool of LibreOffice user profiles of which each is used by one conversion at a time."""

    def lease(self) -> AbstractContextManager[Path]: ...

    def clear(self) -> int: ...


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

    def __init__(self, home: Path, size: int = _SLOTS) -> None:
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

    def clear(self) -> int:
        count = 0
        for slot in range(self._size):
            profile = self._home / f"profile-{slot}"
            lock = self._home / f"lock-{slot}"
            if profile.exists() and self._taken(lock):
                try:
                    shutil.rmtree(profile, ignore_errors=True)
                    count += 1
                finally:
                    lock.rmdir()
        return count

    def _taken(self, lock: Path) -> bool:
        try:
            lock.mkdir()
        except (FileExistsError, PermissionError):
            with suppress(FileNotFoundError, PermissionError):
                if time.time() - lock.stat().st_mtime > _STALE:
                    shutil.rmtree(lock, ignore_errors=True)
            return False
        return True


class Swept(Protocol):
    """Folder of conversions that gets rid of what is old or idle."""

    def sweep(self, before: float) -> int: ...


@final
class Conversions:
    """Home folder of the conversions: converted files, work folders and LibreOffice profiles.

    A converted file or a work folder whose last change is earlier than the given moment is
    removed, which also removes the parts left by a dead process. Profiles that no conversion
    holds are removed on every sweep, because LibreOffice keeps the names of opened documents in
    them. The number of removed items is returned.
    """

    __slots__ = ("_home",)

    def __init__(self, home: Path) -> None:
        self._home: Final = home

    def sweep(self, before: float) -> int:
        count = Profiles(self._home / "profiles").clear()
        for folder in ("cache", "work"):
            for path in sorted((self._home / folder).glob("*")):
                if path.stat().st_mtime < before:
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
                    count += 1
        return count


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
        work = self._home / "work"
        work.mkdir(parents=True, exist_ok=True)
        with (
            TemporaryDirectory(dir=work) as folder,
            Profiles(self._home / "profiles").lease() as profile,
        ):
            self._convert(program, folder, profile)
            ready = Path(folder) / f"{self._path.stem}.docx"
            if not ready.is_file():
                raise UnreadableError(
                    f"Файл {self._path.name} не удалось преобразовать через LibreOffice"
                )
            partial = cached.with_name(f"{cached.name}.{os.getpid()}.{threading.get_ident()}.part")
            try:
                shutil.copyfile(ready, partial)
                partial.replace(cached)
            finally:
                partial.unlink(missing_ok=True)
        return cached

    def _convert(self, program: str, folder: str, profile: Path) -> None:
        failure = UnreadableError(
            f"Файл {self._path.name} не удалось преобразовать через LibreOffice"
        )
        try:
            process = subprocess.Popen(
                [
                    program,
                    f"-env:UserInstallation={profile.resolve().as_uri()}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "docx",
                    "--outdir",
                    folder,
                    str(self._path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            raise failure from error
        try:
            code = process.wait(timeout=_LIMIT)
        except subprocess.TimeoutExpired as error:
            self._stop(process)
            raise failure from error
        if code != 0:
            raise failure

    def _stop(self, process: subprocess.Popen[bytes]) -> None:
        if sys.platform == "win32":
            subprocess.run(
                [shutil.which("taskkill") or "taskkill", "/F", "/T", "/PID", str(process.pid)],
                check=False,
                capture_output=True,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
