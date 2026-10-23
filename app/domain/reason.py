from typing import Final, Literal, Protocol, final

type Source = Literal["rule", "llm"]


class Reason(Protocol):
    """Machine-readable cause of a status and the side that produced it."""

    def code(self) -> str: ...

    def source(self) -> Source: ...


@final
class Cause:
    """Reason code produced either by a rule in code or by the language model."""

    __slots__ = ("_code", "_source")

    def __init__(self, code: str, source: Source) -> None:
        self._code: Final = code
        self._source: Final = source

    def code(self) -> str:
        return self._code

    def source(self) -> Source:
        return self._source
