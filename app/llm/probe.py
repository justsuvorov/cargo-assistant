import time
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Final, Protocol, TextIO, final

import httpx
from pydantic import ValidationError

from app.llm.deadline import Countdown
from app.llm.errors import UnavailableError
from app.llm.ledger import Origin
from app.llm.messages import System, User
from app.llm.provider import Backend, Reply
from app.llm.schema.catalog import Catalog
from app.llm.schema.shape import Shape
from app.llm.schema.trial import Trial
from app.llm.text import Raw, Thoughtless, Unfenced


class Inventory(Protocol):
    """Names of the models that an endpoint serves."""

    def names(self) -> tuple[str, ...]: ...


@final
class Listing:
    """Models listed by an OpenAI-compatible endpoint at its models address."""

    __slots__ = ("_client", "_key", "_url")

    def __init__(self, client: httpx.Client, url: str, key: str) -> None:
        self._client: Final = client
        self._url: Final = url
        self._key: Final = key

    def names(self) -> tuple[str, ...]:
        try:
            response = self._client.get(
                self._url, headers={"Authorization": f"Bearer {self._key}"}, timeout=30.0
            )
        except httpx.TransportError as error:
            raise UnavailableError(f"список моделей недоступен: {error!r}") from error
        if not response.is_success:
            raise UnavailableError(f"список моделей недоступен, код {response.status_code}")
        try:
            return Catalog.model_validate_json(response.text).names()
        except ValidationError as error:
            raise UnavailableError("список моделей пришёл в незнакомом формате") from error


@final
class Unlisted:
    """Models of a provider that publishes no OpenAI-compatible list and has no embeddings."""

    __slots__ = ()

    def names(self) -> tuple[str, ...]:
        raise UnavailableError("провайдер не публикует список моделей в формате OpenAI")


class Survey(Protocol):
    """Reconnaissance of a model endpoint that writes a human-readable report."""

    def run(self, output: TextIO) -> None: ...


@final
class Probe:
    """Survey of latency, determinism, constrained output, parallel load and served models,
    made with a made-up question and providers that never retry; the first provider is the one
    the settings choose and every provider is one way to constrain the answer."""

    __slots__ = ("_catalog", "_origin", "_parallel", "_providers")

    def __init__(
        self, providers: Mapping[str, Backend], catalog: Inventory, origin: Origin, parallel: int
    ) -> None:
        self._providers: Final = providers
        self._catalog: Final = catalog
        self._origin: Final = origin
        self._parallel: Final = parallel

    def run(self, output: TextIO) -> None:
        provider = next(iter(self._providers.values()))
        output.write(
            f"Разведка модели: провайдер {self._origin.provider()}, модель {self._origin.model()}\n"
        )
        output.write(self._latency(provider))
        output.write(self._determinism(provider))
        output.write(self._formats())
        output.write(self._concurrency(provider))
        output.write(self._models())

    def _latency(self, provider: Backend) -> str:
        try:
            seconds, reply = self._ask(provider)
        except UnavailableError as error:
            return f"1. Задержка: запрос не удался: {error}\n"
        return (
            f"1. Задержка типичного запроса: {seconds:.2f} с, токенов на входе {reply.spent()[0]},"
            f" на выходе {reply.spent()[1]}, ответ проходит схему: {self._verdict(reply)}\n"
        )

    def _determinism(self, provider: Backend) -> str:
        texts: list[str] = []
        for _ in range(5):
            try:
                texts.append(Thoughtless(Raw(self._ask(provider)[1].text())).text())
            except UnavailableError as error:
                return f"2. Детерминизм: запрос не удался: {error}\n"
        return (
            f"2. Детерминизм: {len(texts)} одинаковых запросов, "
            f"различных ответов {len(set(texts))}\n"
        )

    def _formats(self) -> str:
        return "3. Ограничение ответа схемой:\n" + "".join(
            f"   {name}: {self._format(provider)}\n" for name, provider in self._providers.items()
        )

    def _format(self, provider: Backend) -> str:
        try:
            seconds, reply = self._ask(provider)
        except UnavailableError as error:
            return f"не работает: {error}"
        return f"принято, ответ проходит схему: {self._verdict(reply)}, {seconds:.2f} с"

    def _concurrency(self, provider: Backend) -> str:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self._parallel) as pool:
            failures = tuple(
                failure
                for failure in pool.map(lambda _: self._failure(provider), range(self._parallel))
                if failure
            )
        return (
            f"4. Параллельность: {self._parallel} запросов одновременно, успешно "
            f"{self._parallel - len(failures)}, ошибок {len(failures)}, общее время "
            f"{time.perf_counter() - started:.2f} с\n"
            + "".join(f"   {text}: {count}\n" for text, count in Counter(failures).items())
        )

    def _failure(self, provider: Backend) -> str:
        try:
            self._ask(provider)
        except UnavailableError as error:
            return str(error)
        return ""

    def _models(self) -> str:
        try:
            names = self._catalog.names()
        except UnavailableError as error:
            return f"5. Модели: {error}\n"
        return f"5. Модели (ищите среди них модель эмбеддингов): {', '.join(names) or 'нет'}\n"

    def _ask(self, provider: Backend) -> tuple[float, Reply]:
        started = time.perf_counter()
        reply = provider.reply(
            (
                System("Ты помогаешь сверять декларации на перевозку грузов с полисом страхования"),
                User(
                    "Груз в декларации: «Холодильники бытовые, 20 шт.». Пункт полиса: "
                    "«Застрахованы бытовая техника и электроника». Относится ли груз к пункту? "
                    "В поле covered ответь true или false, в поле reason — одно предложение"
                ),
            ),
            Shape(Trial),
            Countdown(3600.0),
        )
        return time.perf_counter() - started, reply

    def _verdict(self, reply: Reply) -> str:
        try:
            Trial.model_validate_json(Unfenced(Thoughtless(Raw(reply.text()))).text())
        except ValidationError:
            return f"нет, ответ: {reply.text()[:200]!r}"
        return "да"
