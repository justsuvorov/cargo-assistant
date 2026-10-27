import hashlib
import json
import threading
import time
from typing import Final, Protocol, final

from pydantic import BaseModel, ValidationError

from app.llm.deadline import Countdown, Deadline
from app.llm.errors import MalformedError, UnavailableError
from app.llm.ledger import Ledger, Logged, Measured, Origin
from app.llm.messages import Assistant, Message, User
from app.llm.provider import Backend
from app.llm.schema.shape import Shape
from app.llm.text import Raw, Thoughtless, Unfenced


class Model(Protocol):
    """Language model that answers a conversation with an instance of the given pydantic schema;
    the purpose names the kind of request for accounting and for recorded answers in tests."""

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T: ...


@final
class Strict:
    """Model that accepts only JSON valid against the schema: it removes reasoning and a fence
    around the whole answer, asks once more after an invalid answer and then fails loudly;
    every request is recorded in the ledger and all of them share one deadline."""

    __slots__ = ("_ledger", "_origin", "_provider", "_total")

    def __init__(self, provider: Backend, origin: Origin, ledger: Ledger, total: float) -> None:
        self._provider: Final = provider
        self._origin: Final = origin
        self._ledger: Final = ledger
        self._total: Final = total

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        deadline = Countdown(self._total)
        first = self._text(purpose, messages, schema, deadline)
        try:
            return schema.model_validate_json(first)
        except ValidationError as error:
            second = self._text(
                purpose,
                (
                    *messages,
                    Assistant(first),
                    User(
                        f"Ответ не прошёл проверку по JSON-схеме: {error}. "
                        "Ответь заново одним JSON-объектом по схеме"
                    ),
                ),
                schema,
                deadline,
            )
        try:
            return schema.model_validate_json(second)
        except ValidationError as error:
            raise MalformedError(
                f"Ответ модели на запрос {purpose} дважды не прошёл проверку по схеме "
                f"{schema.__name__}: {error}"
            ) from error

    def _text(
        self,
        purpose: str,
        messages: tuple[Message, ...],
        schema: type[BaseModel],
        deadline: Deadline,
    ) -> str:
        digest = hashlib.sha256(
            json.dumps(
                [Shape(schema).instruction(), *([m.role(), m.text()] for m in messages)],
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        started = time.perf_counter()
        try:
            reply = self._provider.reply(messages, Shape(schema), deadline)
        except UnavailableError:
            self._ledger.record(
                Logged(
                    purpose,
                    self._origin,
                    digest,
                    Measured((0, 0), time.perf_counter() - started, valid=False),
                )
            )
            raise
        text = Unfenced(Thoughtless(Raw(reply.text()))).text()
        self._ledger.record(
            Logged(
                purpose,
                self._origin,
                digest,
                Measured(
                    reply.spent(), time.perf_counter() - started, valid=self._valid(text, schema)
                ),
            )
        )
        return text

    def _valid(self, text: str, schema: type[BaseModel]) -> bool:
        try:
            schema.model_validate_json(text)
        except ValidationError:
            return False
        return True


@final
class Throttled:
    """Model that lets no more requests run at once than the shared semaphore of the process
    allows; worker stages call it from threads, so the semaphore is a thread one."""

    __slots__ = ("_gate", "_model")

    def __init__(self, model: Model, gate: threading.Semaphore) -> None:
        self._model: Final = model
        self._gate: Final = gate

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        with self._gate:
            return self._model.answer(purpose, messages, schema)
