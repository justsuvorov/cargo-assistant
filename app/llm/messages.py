from typing import Final, Protocol, final


class Message(Protocol):
    """One turn of a conversation with the model."""

    def role(self) -> str: ...

    def text(self) -> str: ...


@final
class System:
    """Instruction from the application that frames the whole conversation."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def role(self) -> str:
        return "system"

    def text(self) -> str:
        return self._text


@final
class User:
    """Question or data that the application gives to the model."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def role(self) -> str:
        return "user"

    def text(self) -> str:
        return self._text


@final
class Assistant:
    """Earlier answer of the model, repeated back so that it can correct itself."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def role(self) -> str:
        return "assistant"

    def text(self) -> str:
        return self._text
