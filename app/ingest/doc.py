import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Final, final

from app.domain.errors import UnreadableError
from app.ingest.book import Sheet
from app.ingest.docx import Docx


@final
class Doc:
    """Book read from a legacy doc file after LibreOffice in headless mode converts it to docx."""

    __slots__ = ("_command", "_path")

    def __init__(self, path: Path, command: str = "soffice") -> None:
        self._path: Final = path
        self._command: Final = command

    def sheets(self) -> tuple[Sheet, ...]:
        program = shutil.which(self._command)
        if not program:
            raise UnreadableError(
                f"Файл {self._path.name} нельзя прочитать, потому что LibreOffice не установлен"
            )
        with tempfile.TemporaryDirectory() as folder:
            self._convert(program, folder)
            return Docx(Path(folder) / f"{self._path.stem}.docx").sheets()

    def _convert(self, program: str, folder: str) -> None:
        try:
            subprocess.run(
                [
                    program,
                    "--headless",
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
