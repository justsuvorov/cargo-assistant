from collections.abc import Callable
from pathlib import Path
from typing import Final, final
from zipfile import BadZipFile

from docx.opc.exceptions import PackageNotFoundError
from openpyxl.utils.exceptions import InvalidFileException
from xlrd.biffh import XLRDError

from app.domain.errors import UnreadableError
from app.ingest.book import Book, Sheet
from app.ingest.doc import Doc
from app.ingest.docx import Docx
from app.ingest.xls import Xls
from app.ingest.xlsx import Xlsx


@final
class Unsupported:
    """Book of a file whose format the system does not read."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def sheets(self) -> tuple[Sheet, ...]:
        raise UnreadableError(f"Формат файла {self._path.name} не поддерживается")


@final
class Source:
    """Book of a declaration file chosen by its extension: xlsx, xls, docx or doc."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def sheets(self) -> tuple[Sheet, ...]:
        try:
            return self._book().sheets()
        except (
            OSError,
            ValueError,
            KeyError,
            BadZipFile,
            XLRDError,
            PackageNotFoundError,
            InvalidFileException,
        ) as error:
            raise UnreadableError(f"Файл {self._path.name} не удалось прочитать") from error

    def _book(self) -> Book:
        formats: dict[str, Callable[[Path], Book]] = {
            ".xlsx": Xlsx,
            ".xlsm": Xlsx,
            ".xls": Xls,
            ".docx": Docx,
            ".doc": Doc,
        }
        return formats.get(self._path.suffix.lower(), Unsupported)(self._path)
