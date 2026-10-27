import threading
from collections.abc import Mapping
from typing import Final, Protocol, final

from pydantic import BaseModel, ValidationError

from app.llm.errors import MalformedError, MisconfiguredError
from app.llm.messages import Message


class Counted(Protocol):
    """Model that knows how many times it was asked."""

    def count(self) -> int: ...


@final
class FakeModel:
    """Model for tests that answers each purpose with a recorded JSON text, validates it like the
    real client and counts the calls; it never touches the network."""

    __slots__ = ("_answers", "_asked", "_lock")

    def __init__(self, answers: Mapping[str, str]) -> None:
        self._answers: Final = dict(answers)
        self._asked: Final[list[tuple[str, tuple[Message, ...]]]] = []
        self._lock: Final = threading.Lock()

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        with self._lock:
            self._asked.append((purpose, messages))
        if purpose not in self._answers:
            raise MisconfiguredError(f"Для запроса {purpose} в FakeModel нет записанного ответа")
        try:
            return schema.model_validate_json(self._answers[purpose])
        except ValidationError as error:
            raise MalformedError(
                f"Записанный ответ на запрос {purpose} не проходит схему {schema.__name__}"
            ) from error

    def count(self) -> int:
        with self._lock:
            return len(self._asked)
