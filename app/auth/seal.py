import base64
import hashlib
import hmac
import json
from datetime import UTC
from typing import Final, Protocol, final

from app.auth.errors import DeniedError
from app.auth.identity import Identity, Person
from app.core.clock import Clock


class Seal(Protocol):
    """Signer that turns a small record into text nobody can forge and back."""

    def seal(self, record: dict[str, str], seconds: int) -> str: ...

    def open(self, text: str) -> dict[str, str]: ...


@final
class Signed:
    """Seal that signs records with HMAC-SHA256 and a secret, with an expiry time inside."""

    __slots__ = ("_clock", "_secret")

    def __init__(self, secret: str, clock: Clock) -> None:
        if not secret:
            raise ValueError("Не задан SESSION_SECRET, подпись cookie невозможна")
        self._secret: Final = secret.encode()
        self._clock: Final = clock

    def seal(self, record: dict[str, str], seconds: int) -> str:
        body = base64.urlsafe_b64encode(
            json.dumps({**record, "exp": str(self._now() + seconds)}).encode()
        ).decode()
        return f"{body}.{self._mark(body)}"

    def open(self, text: str) -> dict[str, str]:
        body, _, mark = text.partition(".")
        if not hmac.compare_digest(mark, self._mark(body)):
            raise DeniedError("Подпись cookie не совпадает")
        try:
            record: dict[str, str] = json.loads(base64.urlsafe_b64decode(body.encode()))
        except ValueError as error:
            raise DeniedError(f"Cookie не читается: {error}") from error
        if int(record.get("exp", "0")) <= self._now():
            raise DeniedError("Срок cookie истёк")
        return record

    def _now(self) -> int:
        return int(self._clock.now().replace(tzinfo=UTC).timestamp())

    def _mark(self, body: str) -> str:
        return base64.urlsafe_b64encode(
            hmac.new(self._secret, body.encode(), hashlib.sha256).digest()
        ).decode()


@final
class Sealed:
    """Passport that trusts the signed session cookie issued after a successful login."""

    __slots__ = ("_seal",)

    def __init__(self, seal: Seal) -> None:
        self._seal: Final = seal

    def identity(self, token: str) -> Identity:
        record = self._seal.open(token)
        sub = record.get("sub", "")
        if not sub:
            raise DeniedError("В сессии нет пользователя sub")
        return Person(
            sub,
            record.get("name", sub),
            frozenset(item for item in record.get("roles", "").split(",") if item),
            frozenset(item for item in record.get("groups", "").split(",") if item),
        )
