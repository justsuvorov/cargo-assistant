from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from app.auth.identity import Identity
from app.jobs.queue import MissingJobError
from app.web.security import identity, services, visible
from app.web.uploads import upload

router = APIRouter(prefix="/api")


@router.post("/declarations")
async def declarations(
    request: Request, files: list[UploadFile], who: Annotated[Identity, Depends(identity)]
) -> list[dict[str, object]]:
    return [
        {"file": name, "declaration_id": receipt.declaration_id, "job_id": receipt.job_id}
        for name, receipt in await upload(request, files, who)
    ]


@router.get("/jobs/{job_id}")
async def job(
    job_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> dict[str, object]:
    try:
        snapshot = await services(request).jobs.snapshot(job_id)
    except MissingJobError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    await visible(request, who, job_id)
    return {
        "id": snapshot.id,
        "kind": snapshot.kind,
        "status": snapshot.status,
        "stage": snapshot.stage,
        "progress": snapshot.progress,
        "error": snapshot.error,
        "timings": snapshot.timings,
    }
