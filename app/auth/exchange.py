from typing import Final, Protocol, final

import httpx

from app.auth.errors import DeniedError
from app.core.settings import Settings


class Tokens(Protocol):
    """Place where an authorization code is exchanged for the access token of a person."""

    async def access(self, code: str, verifier: str, address: str) -> str: ...


@final
class Remote:
    """Token endpoint of Keycloak reached over HTTP with the PKCE code verifier."""

    __slots__ = ("_settings",)

    def __init__(self, settings: Settings) -> None:
        self._settings: Final = settings

    async def access(self, code: str, verifier: str, address: str) -> str:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": address,
            "client_id": self._settings.audience(),
        }
        if self._settings.client_secret():
            form["client_secret"] = self._settings.client_secret()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self._settings.tokens(), data=form)
            response.raise_for_status()
            return str(response.json()["access_token"])
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise DeniedError(f"Keycloak не выдал токен: {error}") from error
