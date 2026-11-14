import io
from typing import Final, Protocol, final
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from app.storage.errors import BrokenError
from app.storage.relative import Relative

_ENTRIES = 2000
_BYTES = 512 * 1024 * 1024
_UTF8_FLAG = 0x800


class Stored(Protocol):
    """File of an uploaded package with its path inside the package."""

    def name(self) -> str: ...

    def data(self) -> bytes: ...


@final
class Blob:
    """File that is already in memory."""

    __slots__ = ("_data", "_name")

    def __init__(self, name: str, data: bytes) -> None:
        self._name: Final = name
        self._data: Final = data

    def name(self) -> str:
        return self._name

    def data(self) -> bytes:
        return self._data


class Unpacked(Protocol):
    """Files that an archive holds."""

    def files(self) -> tuple[Stored, ...]: ...


@final
class Unzipped:
    """Files of a zip archive with names restored and every path checked against leaving the folder.

    A name without the UTF-8 flag is read from UTF-8 when the bytes are valid UTF-8 and from
    cp866 otherwise. A name that is already Unicode, as the zipfile module makes it from the
    Unicode path field of an entry, cannot be encoded back to cp437 and is never recoded.
    Service files and folders are left out; the size is bounded.
    """

    __slots__ = ("_data",)

    def __init__(self, data: bytes) -> None:
        self._data: Final = data

    def files(self) -> tuple[Stored, ...]:
        try:
            with ZipFile(io.BytesIO(self._data)) as archive:
                infos = [item for item in archive.infolist() if not item.is_dir()]
                if len(infos) > _ENTRIES or sum(item.file_size for item in infos) > _BYTES:
                    raise BrokenError("Архив слишком велик для распаковки")
                named = [(Relative(self._name(item)), item) for item in infos]
                return tuple(
                    Blob(path.path(), archive.read(item))
                    for path, item in named
                    if not path.service()
                )
        except BadZipFile as error:
            raise BrokenError("Архив повреждён или не является zip") from error

    def _name(self, item: ZipInfo) -> str:
        if item.flag_bits & _UTF8_FLAG:
            return item.filename
        try:
            raw = item.filename.encode("cp437")
        except UnicodeEncodeError:
            return item.filename
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp866", errors="replace")


@final
class Zipped:
    """Zip archive made of files that are already in memory, under the names they have."""

    __slots__ = ("_files",)

    def __init__(self, files: tuple[Stored, ...]) -> None:
        self._files: Final = files

    def data(self) -> bytes:
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for file in self._files:
                archive.writestr(file.name(), file.data())
        return buffer.getvalue()
