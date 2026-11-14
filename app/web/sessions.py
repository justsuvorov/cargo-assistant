from collections import defaultdict
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.auth.identity import Identity
from app.jobs.errors import ChoiceError, MissingWorkspaceError
from app.jobs.models import Declaration, Job, Workspace
from app.storage.archive import Blob, Zipped
from app.web.folders import chosen, opened
from app.web.overviews import overview
from app.web.security import identity, services, workspace_of

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
_ZIP = "application/zip"


def standing(statuses: list[str]) -> str:
    if not statuses:
        return "Не запущена"
    if any(status not in {"done", "failed"} for status in statuses):
        return "Выполняется"
    return "Завершена с ошибками" if "failed" in statuses else "Завершена"


async def page(
    request: Request, who: Identity, workspace_id: int, template: str, notice: str
) -> HTMLResponse:
    workspace = await workspace_of(request, who, workspace_id)
    return templates.TemplateResponse(
        request,
        template,
        {
            "page": "sessions",
            "notice": notice,
            "view": await overview(request, who, workspace),
        },
    )


@router.get("/sessions", response_class=HTMLResponse)
async def listing(request: Request, who: Annotated[Identity, Depends(identity)]) -> HTMLResponse:
    async with services(request).database.session() as session:
        found = (
            await session.scalars(
                select(Workspace).where(Workspace.owner == who.id()).order_by(Workspace.id.desc())
            )
        ).all()
        states: defaultdict[int, list[str]] = defaultdict(list)
        for number, status in (
            await session.execute(
                select(Declaration.workspace_id, Job.status)
                .join(Job, Declaration.job_id == Job.id)
                .where(Declaration.owner == who.id())
            )
        ).all():
            states[number or 0].append(status)
    return templates.TemplateResponse(
        request,
        "sessions.html",
        {
            "page": "sessions",
            "rows": [
                {
                    "workspace": workspace,
                    "count": len(states[workspace.id]),
                    "standing": standing(states[workspace.id]),
                }
                for workspace in found
            ],
        },
    )


@router.get("/sessions/new", response_class=HTMLResponse)
async def blank(request: Request, _who: Annotated[Identity, Depends(identity)]) -> HTMLResponse:
    return templates.TemplateResponse(request, "session_new.html", {"page": "new"})


@router.post("/sessions")
async def open_folder(
    request: Request,
    files: list[UploadFile],
    who: Annotated[Identity, Depends(identity)],
    conditions: Annotated[list[UploadFile] | None, File()] = None,
) -> RedirectResponse:
    name, found = await opened(files)
    number = await services(request).workspaces.open(
        who.id(), who.name(), name, found, await chosen(conditions)
    )
    return RedirectResponse(f"/sessions/{number}", status_code=303)


@router.get("/sessions/{workspace_id}", response_class=HTMLResponse)
async def show(
    workspace_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> HTMLResponse:
    return await page(request, who, workspace_id, "session.html", "")


@router.get("/sessions/{workspace_id}/body", response_class=HTMLResponse)
async def body(
    workspace_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> HTMLResponse:
    return await page(request, who, workspace_id, "session_body.html", "")


@router.post("/sessions/{workspace_id}/start", response_model=None)
async def start(
    workspace_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> RedirectResponse | HTMLResponse:
    await workspace_of(request, who, workspace_id)
    chosen = tuple(str(item) for item in (await request.form()).getlist("declaration"))
    try:
        await services(request).workspaces.start(who.id(), workspace_id, chosen)
    except MissingWorkspaceError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ChoiceError as error:
        refused = await page(request, who, workspace_id, "session.html", str(error))
        refused.status_code = 409
        return refused
    return RedirectResponse(f"/sessions/{workspace_id}", status_code=303)


@router.get("/sessions/{workspace_id}/archive")
async def archive(
    workspace_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> Response:
    workspace = await workspace_of(request, who, workspace_id)
    async with services(request).database.session() as session:
        found = (
            await session.scalars(
                select(Declaration)
                .where(
                    Declaration.workspace_id == workspace.id,
                    Declaration.owner == who.id(),
                    Declaration.result_key != "",
                )
                .order_by(Declaration.id)
            )
        ).all()
    if not found:
        raise HTTPException(status_code=404, detail="Файлов результата в сессии пока нет")
    storage = services(request).storage
    names = [declaration.result_key.rsplit("/", 1)[-1] for declaration in found]
    data = Zipped(
        tuple(
            Blob(
                f"{declaration.id} – {name}" if names.count(name) > 1 else name,
                storage.read(declaration.result_key),
            )
            for declaration, name in zip(found, names, strict=True)
        )
    ).data()
    title = quote(f"{workspace.name} – результаты проверки.zip")
    return Response(
        data,
        media_type=_ZIP,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{title}"},
    )
