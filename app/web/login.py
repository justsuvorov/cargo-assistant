import secrets
from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth.errors import DeniedError
from app.web.security import COOKIE, services

router = APIRouter(prefix="/auth")
RITUAL = "cargo_login"
RITUAL_SECONDS = 600


def address(request: Request) -> str:
    base = services(request).settings.base() or str(request.base_url).rstrip("/")
    return f"{base}/auth/callback"


def local(target: str) -> str:
    return target if target.startswith("/") and not target.startswith("//") else "/"


def keep(response: RedirectResponse, request: Request, name: str, value: str, seconds: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=seconds,
        httponly=True,
        secure=services(request).settings.secure(),
        samesite="lax",
        path="/",
    )


@router.get("/login")
async def enter(request: Request, next: str = "/") -> RedirectResponse:
    known = services(request)
    if known.settings.development():
        return RedirectResponse("/", status_code=302)
    if not known.settings.audience() or not known.settings.issuer().startswith("http"):
        raise HTTPException(status_code=503, detail="Keycloak не настроен, вход невозможен")
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    query = urlencode(
        {
            "client_id": known.settings.audience(),
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": address(request),
            "state": state,
            "code_challenge": urlsafe_b64encode(sha256(verifier.encode()).digest())
            .decode()
            .rstrip("="),
            "code_challenge_method": "S256",
        }
    )
    response = RedirectResponse(f"{known.settings.authorize()}?{query}", status_code=302)
    keep(
        response,
        request,
        RITUAL,
        known.seal.seal(
            {"state": state, "verifier": verifier, "next": local(next)}, RITUAL_SECONDS
        ),
        RITUAL_SECONDS,
    )
    return response


@router.get("/callback")
async def arrive(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    known = services(request)
    if error:
        raise HTTPException(status_code=401, detail=f"Keycloak отказал во входе: {error}")
    try:
        ritual: dict[str, Any] = known.seal.open(request.cookies.get(RITUAL, ""))
        if not code or not secrets.compare_digest(state, str(ritual.get("state", "-"))):
            raise DeniedError("Параметр state входа не совпадает с сохранённым")
        who = known.passport.identity(
            await known.tokens.access(code, str(ritual["verifier"]), address(request))
        )
    except DeniedError as failure:
        raise HTTPException(status_code=401, detail=f"Вход не выполнен: {failure}") from failure
    if not who.allows("user"):
        raise HTTPException(status_code=403, detail="Недостаточно прав для работы с сервисом")
    hours = known.settings.hours() * 3600
    response = RedirectResponse(local(str(ritual.get("next", "/"))), status_code=302)
    keep(response, request, COOKIE, known.seal.seal(who.card(), hours), hours)
    response.delete_cookie(RITUAL, path="/")
    return response


@router.get("/logout")
async def leave(request: Request) -> RedirectResponse:
    known = services(request)
    if known.settings.development():
        return RedirectResponse("/", status_code=302)
    home = known.settings.base() or str(request.base_url).rstrip("/")
    response = RedirectResponse(
        f"{known.settings.logout()}?client_id={quote(known.settings.audience())}"
        f"&post_logout_redirect_uri={quote(home + '/', safe='')}",
        status_code=302,
    )
    response.delete_cookie(COOKIE, path="/")
    return response
