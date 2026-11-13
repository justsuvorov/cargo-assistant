from typing import Final, Protocol, final

import jwt
from jwt import PyJWK, PyJWKClient

from app.auth.errors import DeniedError
from app.auth.identity import Identity, Local, Person
from app.core.settings import Settings


class Passport(Protocol):
    """Check that turns the token of a request into the identity of its sender."""

    def identity(self, token: str) -> Identity: ...


class KeySource(Protocol):
    """Place that knows which public key signed a token."""

    def key(self, token: str) -> PyJWK: ...


@final
class RemoteKeys:
    """Public keys published by Keycloak, fetched and cached on first use."""

    __slots__ = ("_client",)

    def __init__(self, address: str) -> None:
        self._client: Final = PyJWKClient(address)

    def key(self, token: str) -> PyJWK:
        return self._client.get_signing_key_from_jwt(token)


@final
class StaticKeys:
    """Public keys known in advance and found by the key identifier of a token."""

    __slots__ = ("_keys",)

    def __init__(self, keys: dict[str, PyJWK]) -> None:
        self._keys: Final = keys

    def key(self, token: str) -> PyJWK:
        return self._keys[jwt.get_unverified_header(token)["kid"]]


@final
class Open:
    """Passport of a deployment without login that gives everybody the one local user."""

    __slots__ = ("_user",)

    def __init__(self, user: str) -> None:
        self._user: Final = user

    def identity(self, token: str) -> Identity:
        del token
        return Local(self._user)


@final
class Keycloak:
    """Passport that accepts only tokens signed by Keycloak for this application."""

    __slots__ = ("_keys", "_settings")

    def __init__(self, settings: Settings, keys: KeySource) -> None:
        self._settings: Final = settings
        self._keys: Final = keys

    def identity(self, token: str) -> Identity:
        try:
            claims = jwt.decode(
                token,
                self._keys.key(token),
                algorithms=["RS256"],
                audience=self._settings.audience(),
                issuer=self._settings.issuer(),
            )
        except (jwt.PyJWTError, KeyError) as error:
            raise DeniedError(f"Токен не принят: {error}") from error
        return Person(
            str(claims.get("preferred_username", claims.get("sub", ""))),
            self._roles(frozenset(map(str, claims.get("realm_access", {}).get("roles", [])))),
            frozenset(str(group).strip("/") for group in claims.get("groups", [])),
        )

    def _roles(self, granted: frozenset[str]) -> frozenset[str]:
        known = tuple(
            name for name in ("user", "expert", "admin") if self._settings.role(name) in granted
        )
        return frozenset(known + (("user",) if known else ()))
