from fastapi import HTTPException, Request

from app.auth.errors import DeniedError
from app.auth.identity import Identity
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
