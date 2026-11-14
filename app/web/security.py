from urllib.parse import quote

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.auth.errors import DeniedError
from app.auth.identity import Identity
from app.jobs.models import Declaration, Policy
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


def expert(request: Request) -> Identity:
    who = identity(request)
    if not who.allows("expert"):
        raise HTTPException(status_code=403, detail="Действие доступно только эксперту")
    return who


async def visible(request: Request, who: Identity, job_id: int) -> None:
    async with services(request).database.session() as session:
        groups = [
            *await session.scalars(
                select(Declaration.access_group).where(Declaration.job_id == job_id)
            ),
            *await session.scalars(select(Policy.access_group).where(Policy.job_id == job_id)),
        ]
    if not any(who.sees(group) for group in groups):
        raise HTTPException(status_code=404, detail=f"Задача {job_id} не найдена")
