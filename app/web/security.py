from fastapi import HTTPException, Request
from sqlalchemy import select

from app.auth.errors import DeniedError
from app.auth.identity import Identity
from app.jobs.models import Declaration, Policy
from app.web.services import Services


def services(request: Request) -> Services:
    found: Services = request.app.state.services
    return found


def token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get("access_token", "")


def identity(request: Request) -> Identity:
    try:
        who = services(request).passport.identity(token(request))
    except DeniedError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
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
