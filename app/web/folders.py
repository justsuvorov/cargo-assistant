from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile

from app.storage.archive import Blob, Stored, Unzipped
from app.storage.errors import BrokenError, EscapeError
from app.storage.tree import Tree


async def opened(files: list[UploadFile]) -> tuple[str, tuple[Stored, ...]]:
    """Name and files of the folder that a user chose in the browser or packed into one zip."""
    if not files:
        raise HTTPException(status_code=400, detail="Файлы папки не выбраны")
    uploaded: tuple[Stored, ...] = tuple(
        [Blob(file.filename or "", await file.read()) for file in files]
    )
    zipped = len(uploaded) == 1 and uploaded[0].name().lower().endswith(".zip")
    try:
        tree = Tree(Unzipped(uploaded[0].data()).files() if zipped else uploaded)
        found = tree.files()
        name = tree.name() or (PurePosixPath(uploaded[0].name()).stem if zipped else "")
    except (EscapeError, BrokenError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return name or "Папка без названия", found


async def chosen(files: list[UploadFile] | None) -> tuple[Stored, ...]:
    """Special conditions file of the client that a user chose apart from the folder, if any:
    a field left empty by the browser gives nothing, a path is cut to the name of the file."""
    return tuple(
        Blob(PurePosixPath(file.filename.replace("\\", "/")).name, data)
        for file in (files or [])
        if file.filename
        for data in (await file.read(),)
        if data
    )
