from urllib.parse import quote

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.auth.errors import DeniedError
from app.auth.identity import Identity
from app.jobs.models import Declaration, Policy, Workspace
from app.web.services import Services

COOKIE = "cargo_session"


def services(request: Request) -> Services:
    found: Services = request.app.state.services
    return found


def bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def unsigned(request: Request) -> HTTPException:
    if request.url.path.startswith("/api/") or request.method != "GET":
        return HTTPException(status_code=401, detail="Требуется вход")
    if request.headers.get("hx-request"):
        return HTTPException(
            status_code=401, detail="Требуется вход", headers={"HX-Redirect": "/auth/login"}
        )
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return HTTPException(
        status_code=302,
        detail="Требуется вход",
        headers={"Location": f"/auth/login?next={quote(target, safe='')}"},
    )


def identity(request: Request) -> Identity:
    known = services(request)
    try:
        if bearer(request) or (known.settings.development() and not request.cookies.get(COOKIE)):
            who = known.passport.identity(bearer(request))
        elif request.cookies.get(COOKIE):
            who = known.session.identity(request.cookies[COOKIE])
        else:
            raise unsigned(request)
    except DeniedError as error:
        if bearer(request):
            raise HTTPException(status_code=401, detail=str(error)) from error
        raise unsigned(request) from error
    if not who.allows("user"):
        raise HTTPException(status_code=403, detail="Недостаточно прав для работы с сервисом")
    return who


async def visible(request: Request, who: Identity, job_id: int) -> None:
    async with services(request).database.session() as session:
        owners = [
            *await session.scalars(select(Declaration.owner).where(Declaration.job_id == job_id)),
            *await session.scalars(select(Policy.owner).where(Policy.job_id == job_id)),
        ]
    if who.id() not in owners:
        raise HTTPException(status_code=404, detail=f"Задача {job_id} не найдена")


async def workspace_of(request: Request, who: Identity, workspace_id: int) -> Workspace:
    async with services(request).database.session() as session:
        found = await session.scalar(
            select(Workspace).where(Workspace.id == workspace_id, Workspace.owner == who.id())
        )
    if found is None:
        raise HTTPException(status_code=404, detail=f"Сессия {workspace_id} не найдена")
    return found


async def declaration_of(request: Request, who: Identity, declaration_id: int) -> Declaration:
    async with services(request).database.session() as session:
        found = await session.scalar(
            select(Declaration).where(
                Declaration.id == declaration_id, Declaration.owner == who.id()
            )
        )
    if found is None:
        raise HTTPException(status_code=404, detail=f"Декларация {declaration_id} не найдена")
    return found


async def policy_of(request: Request, who: Identity, policy_id: int) -> Policy:
    async with services(request).database.session() as session:
        found = await session.scalar(
            select(Policy).where(Policy.id == policy_id, Policy.owner == who.id())
        )
    if found is None:
        raise HTTPException(status_code=404, detail=f"Полис {policy_id} не найден")
    return found
