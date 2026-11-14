from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile

from app.storage.archive import Blob, Stored, Unzipped
from app.storage.errors import BrokenError, EscapeError
from app.storage.tree import Tree


class TooLargeError(Exception):
    """Upload that is larger than the limit of the settings."""


_MEGABYTE = 1048576


def megabytes(limit: int) -> str:
    """Limit in bytes as the text a user reads: whole megabytes, or kilobytes when smaller."""
    return f"{limit // _MEGABYTE} МБ" if limit >= _MEGABYTE else f"{max(limit // 1024, 1)} КБ"


async def received(files: list[UploadFile], limit: int, what: str) -> list[Blob]:
    """Files of a form read one by one; reading stops as soon as their total passes the limit."""
    found: list[Blob] = []
    total = 0
    for file in files:
        data = await file.read()
        total += len(data)
        if total > limit:
            raise TooLargeError(f"{what} больше допустимых {megabytes(limit)}, загрузка отменена")
        found.append(Blob(file.filename or "", data))
    return found


async def opened(files: list[UploadFile], limit: int) -> tuple[str, tuple[Stored, ...]]:
    """Name and files of the folder that a user chose in the browser or packed into one zip;
    the folder, also unpacked from a zip, may not be larger than the limit in bytes."""
    if not files:
        raise HTTPException(status_code=400, detail="Файлы папки не выбраны")
    uploaded: tuple[Stored, ...] = tuple(await received(files, limit, "Папка"))
    zipped = len(uploaded) == 1 and uploaded[0].name().lower().endswith(".zip")
    try:
        tree = Tree(Unzipped(uploaded[0].data()).files() if zipped else uploaded)
        found = tree.files()
        if sum(len(each.data()) for each in found) > limit:
            raise TooLargeError(f"Папка больше допустимых {megabytes(limit)}, загрузка отменена")
        name = tree.name() or (PurePosixPath(uploaded[0].name()).stem if zipped else "")
    except (EscapeError, BrokenError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return name or "Папка без названия", found


async def chosen(files: list[UploadFile] | None, limit: int) -> tuple[Stored, ...]:
    """Special conditions file of the client that a user chose apart from the folder, if any:
    a field left empty by the browser gives nothing, a path is cut to the name of the file;
    the file may not be larger than the limit in bytes."""
    found: list[Stored] = []
    for file, blob in zip(
        files or [], await received(files or [], limit, "Файл особых условий"), strict=True
    ):
        if file.filename and blob.data():
            found.append(Blob(PurePosixPath(file.filename.replace("\\", "/")).name, blob.data()))
    return tuple(found)
