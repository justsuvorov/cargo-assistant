import re
from typing import Final, Protocol, final


class Content(Protocol):
    """Text of a model answer at one stage of cleaning."""

    def text(self) -> str: ...


@final
class Raw:
    """Answer text exactly as the provider returned it."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def text(self) -> str:
        return self._text


@final
class Thoughtless:
    """Answer without reasoning: closed think blocks, text before a stray closing tag and an
    unclosed think block up to the end are removed."""

    __slots__ = ("_origin",)

    def __init__(self, origin: Content) -> None:
        self._origin: Final = origin

    def text(self) -> str:
        return re.sub(
            r"<think>.*",
            "",
            re.sub(r"<think>.*?</think>", "", self._origin.text(), flags=re.DOTALL).rpartition(
                "</think>"
            )[2],
            flags=re.DOTALL,
        ).strip()


@final
class Unfenced:
    """Answer freed from one code fence that wraps the whole of it, such as a json fence;
    a fence inside the text is left alone because markdown is never parsed."""

    __slots__ = ("_origin",)

    def __init__(self, origin: Content) -> None:
        self._origin: Final = origin

    def text(self) -> str:
        text = self._origin.text().strip()
        match = re.fullmatch(r"```[a-zA-Z]*[ \t]*\n(.*)\n[ \t]*```", text, flags=re.DOTALL)
        return match.group(1).strip() if match else text
