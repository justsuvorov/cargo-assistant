import time
from typing import Final, Protocol, final

from app.core.journal import Journal
from app.llm.deadline import Cadence, Deadline
from app.llm.errors import UnavailableError
from app.llm.messages import Message
from app.llm.schema.shape import Shape
from app.llm.text import Raw, Thoughtless


class Reply(Protocol):
    """Text that a provider returned together with the tokens it spent."""

    def text(self) -> str: ...

    def spent(self) -> tuple[int, int]: ...


@final
class Answered:
    """Reply as read from the answer body of a provider."""

    __slots__ = ("_spent", "_text")

    def __init__(self, text: str, spent: tuple[int, int]) -> None:
        self._text: Final = text
        self._spent: Final = spent

    def text(self) -> str:
        return self._text

    def spent(self) -> tuple[int, int]:
        return self._spent


class Backend(Protocol):
    """Service that turns a conversation into one reply asking for JSON of the given shape."""

    def reply(self, messages: tuple[Message, ...], shape: Shape, deadline: Deadline) -> Reply: ...


@final
class Insistent:
    """Backend that asks again when the answer is empty after reasoning is removed, as happens
    when the model spends its whole budget on thinking."""

    __slots__ = ("_cadence", "_journal", "_provider")

    def __init__(self, provider: Backend, cadence: Cadence, journal: Journal) -> None:
        self._provider: Final = provider
        self._cadence: Final = cadence
        self._journal: Final = journal

    def reply(self, messages: tuple[Message, ...], shape: Shape, deadline: Deadline) -> Reply:
        for attempt in range(self._cadence.attempts()):
            wait = self._cadence.pause() if attempt else 0.0
            if deadline.left() <= wait:
                break
            time.sleep(wait)
            reply = self._provider.reply(messages, shape, deadline)
            if Thoughtless(Raw(reply.text())).text():
                return reply
            self._journal.info(
                f"Модель вернула пустой ответ с попытки {attempt + 1} "
                f"из {self._cadence.attempts()}",
                0,
                0,
            )
        raise UnavailableError("Модель не дала непустого ответа за отведённые попытки и время")
