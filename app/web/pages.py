from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.auth.identity import Identity
from app.jobs.models import Declaration, Job
from app.jobs.queue import MissingJobError, Snapshot
from app.web.security import identity, services, visible
from app.web.uploads import upload

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


async def rows(request: Request, who: Identity, month: str, limit: int) -> list[dict[str, object]]:
    query = (
        select(Declaration, Job)
        .join(Job, Declaration.job_id == Job.id)
        .order_by(Declaration.id.desc())
        .limit(limit)
    )
    if month:
        query = query.where(Declaration.month == month)
    async with services(request).database.session() as session:
        found = (await session.execute(query)).all()
    return [
        {"declaration": declaration, "job": Snapshot.of(job)}
        for declaration, job in found
        if who.sees(declaration.access_group)
    ]


@router.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse("/reconcile")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/reconcile", response_class=HTMLResponse)
async def reconcile(request: Request, who: Annotated[Identity, Depends(identity)]) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "reconcile.html",
        {"page": "reconcile", "rows": await rows(request, who, "", 20)},
    )


@router.post("/reconcile/upload", response_class=HTMLResponse)
async def accept(
    request: Request, files: list[UploadFile], who: Annotated[Identity, Depends(identity)]
) -> HTMLResponse:
    received = await upload(request, files, who)
    return templates.TemplateResponse(
        request,
        "uploaded.html",
        {
            "rows": [
                {
                    "name": name,
                    "job": await services(request).jobs.snapshot(receipt.job_id),
                }
                for name, receipt in received
            ]
        },
    )


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
async def status(
    job_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> HTMLResponse:
    try:
        snapshot = await services(request).jobs.snapshot(job_id)
    except MissingJobError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    await visible(request, who, job_id)
    async with services(request).database.session() as session:
        note = await session.scalar(select(Declaration.binding).where(Declaration.job_id == job_id))
    return templates.TemplateResponse(request, "job.html", {"job": snapshot, "note": note or ""})


@router.get("/archive", response_class=HTMLResponse)
async def archive(
    request: Request, who: Annotated[Identity, Depends(identity)], month: str = ""
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "archive.html",
        {"page": "archive", "month": month, "rows": await rows(request, who, month, 200)},
    )
