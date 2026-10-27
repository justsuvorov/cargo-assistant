import time
from typing import Final, Protocol, final

import httpx

from app.core.journal import Journal
from app.llm.deadline import Cadence, Deadline
from app.llm.errors import TransientError, UnavailableError


class Wire(Protocol):
    """Channel that sends one JSON request to a provider and returns the raw HTTP answer."""

    def send(self, body: dict[str, object], timeout: float) -> httpx.Response: ...


@final
class Bearer:
    """Wire of an OpenAI-compatible endpoint authorised by a bearer key, like the VSK gateway."""

    __slots__ = ("_client", "_key", "_url")

    def __init__(self, client: httpx.Client, url: str, key: str) -> None:
        self._client: Final = client
        self._url: Final = url
        self._key: Final = key

    def send(self, body: dict[str, object], timeout: float) -> httpx.Response:
        return self._client.post(
            self._url,
            json=body,
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=timeout,
        )


@final
class Keyed:
    """Wire of the Anthropic Messages API authorised by an API key header."""

    __slots__ = ("_client", "_key", "_url")

    def __init__(self, client: httpx.Client, url: str, key: str) -> None:
        self._client: Final = client
        self._url: Final = url
        self._key: Final = key

    def send(self, body: dict[str, object], timeout: float) -> httpx.Response:
        return self._client.post(
            self._url,
            json=body,
            headers={"x-api-key": self._key, "anthropic-version": "2026-10-21"},
            timeout=timeout,
        )


class Endpoint(Protocol):
    """Place that takes a request body and gives back the text of a successful answer."""

    def post(self, body: dict[str, object], deadline: Deadline) -> str: ...


@final
class Patient:
    """Endpoint that repeats a request after network failures, timeouts, 429 and 5xx answers,
    with a pause between attempts and within the total deadline; other answers fail at once."""

    __slots__ = ("_cadence", "_journal", "_timeout", "_wire")

    def __init__(self, wire: Wire, cadence: Cadence, timeout: float, journal: Journal) -> None:
        self._wire: Final = wire
        self._cadence: Final = cadence
        self._timeout: Final = timeout
        self._journal: Final = journal

    def post(self, body: dict[str, object], deadline: Deadline) -> str:
        reason = "общее время ожидания модели истекло до первого запроса"
        for attempt in range(self._cadence.attempts()):
            wait = self._cadence.pause() if attempt else 0.0
            if deadline.left() <= wait:
                break
            time.sleep(wait)
            try:
                return self._once(body, deadline)
            except TransientError as error:
                reason = str(error)
                self._journal.info(
                    f"Запрос к модели не удался с попытки {attempt + 1} "
                    f"из {self._cadence.attempts()}: {reason}",
                    0,
                    0,
                )
        raise UnavailableError(f"Модель недоступна после всех попыток: {reason}")

    def _once(self, body: dict[str, object], deadline: Deadline) -> str:
        try:
            response = self._wire.send(body, min(self._timeout, deadline.left()))
        except httpx.TransportError as error:
            raise TransientError(f"сетевая ошибка {error!r}") from error
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS or response.is_server_error:
            raise TransientError(f"шлюз ответил кодом {response.status_code}")
        if not response.is_success:
            raise UnavailableError(
                f"Модель отклонила запрос с кодом {response.status_code}: {response.text[:500]}"
            )
        return response.text
