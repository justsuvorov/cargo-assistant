from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from sqlalchemy import select

from app.auth.identity import Identity
from app.jobs.errors import ChoiceError, MissingWorkspaceError
from app.jobs.models import Workspace
from app.jobs.queue import MissingJobError
from app.web.folders import TooLargeError, opened
from app.web.overviews import Overview, overview
from app.web.security import identity, services, visible, workspace_of

router = APIRouter(prefix="/api")


def described(view: Overview) -> dict[str, object]:
    return {
        "id": view.workspace.id,
        "name": view.workspace.name,
        "started": view.started(),
        "finished": view.finished(),
        "progress": view.progress(),
        "found": list(view.workspace.found),
        "profile": {
            "status": view.basis.status,
            "version": view.basis.version,
            "problems": list(view.basis.problems),
            "build": view.build.status if view.build is not None else "",
            "error": view.build.error if view.build is not None else "",
        },
        "declarations": [
            {
                "id": line.declaration.id,
                "path": line.path,
                "number": line.declaration.number,
                "job_id": line.job.id,
                "status": line.job.status,
                "stage": line.job.stage,
                "progress": line.job.progress,
                "error": line.job.error,
                "profile_status": line.declaration.profile_status,
                "result": bool(line.declaration.result_key),
            }
            for line in view.lines
        ],
    }


@router.post("/sessions")
async def open_folder(
    request: Request, files: list[UploadFile], who: Annotated[Identity, Depends(identity)]
) -> dict[str, object]:
    try:
        name, found = await opened(files, services(request).settings.folder_limit())
    except TooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    number = await services(request).workspaces.open(who.id(), who.name(), name, found)
    return described(await overview(request, who, await workspace_of(request, who, number)))


@router.get("/sessions")
async def listing(
    request: Request, who: Annotated[Identity, Depends(identity)]
) -> list[dict[str, object]]:
    async with services(request).database.session() as session:
        found = (
            await session.scalars(
                select(Workspace).where(Workspace.owner == who.id()).order_by(Workspace.id.desc())
            )
        ).all()
    return [
        {"id": each.id, "name": each.name, "started": each.started_at is not None} for each in found
    ]


@router.get("/sessions/{workspace_id}")
async def session(
    workspace_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> dict[str, object]:
    workspace = await workspace_of(request, who, workspace_id)
    return described(await overview(request, who, workspace))


@router.post("/sessions/{workspace_id}/start")
async def start(
    workspace_id: int,
    declaration: Annotated[list[str], Form()],
    request: Request,
    who: Annotated[Identity, Depends(identity)],
) -> dict[str, object]:
    await workspace_of(request, who, workspace_id)
    try:
        started = await services(request).workspaces.start(
            who.id(), workspace_id, tuple(declaration)
        )
    except MissingWorkspaceError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ChoiceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"declaration_ids": list(started)}


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
