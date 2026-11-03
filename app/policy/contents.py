from pathlib import Path
from typing import Final, Protocol, final

from app.domain.errors import UnreadableError
from app.ingest.source import Source


class Plain(Protocol):
    """Text of a file in which every line of the file is a line of the text."""

    def text(self) -> str: ...


@final
class Contents:
    """Plain text of a txt, doc, docx, xls or xlsx file; a table row becomes one line of cells."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def text(self) -> str:
        return (
            "\n".join(self._plain().splitlines())
            if self._path.suffix.lower() == ".txt"
            else self._book()
        )

    def _plain(self) -> str:
        raw = self._path.read_bytes()
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return self._legacy(raw)

    def _legacy(self, raw: bytes) -> str:
        try:
            return raw.decode("cp1251")
        except UnicodeDecodeError as error:
            raise UnreadableError(
                f"Файл {self._path.name} не удалось прочитать в кодировке utf-8 или cp1251"
            ) from error

    def _book(self) -> str:
        return "\n".join(
            " ".join(cell.text() for cell in line.cells())
            for sheet in Source(self._path).sheets()
            for line in sheet.lines()
        )
