from pathlib import PurePosixPath

from fastapi import HTTPException, Request, UploadFile

from app.auth.errors import DeniedError
from app.auth.identity import Identity
from app.jobs.intake import Receipt
from app.storage.errors import EscapeError
from app.web.security import services


def safe(name: str | None) -> str:
    return PurePosixPath((name or "").replace("\\", "/")).name


async def upload(
    request: Request, files: list[UploadFile], who: Identity
) -> list[tuple[str, Receipt]]:
    received: list[tuple[str, Receipt]] = []
    try:
        for file in files:
            name = safe(file.filename)
            receipt = await services(request).reception.receive(
                name, await file.read(), who.group()
            )
            received.append((name, receipt))
    except (EscapeError, DeniedError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return received
