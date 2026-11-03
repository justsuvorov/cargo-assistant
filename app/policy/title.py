import re
from typing import Final, Protocol, final

_POLICY = re.compile(
    r"^\W*(?:Генеральный\s+полис\b|(?:General|Master|Open)\s+(?:\w+\s+){0,2}polic(?:y|ies)\b)",
    re.IGNORECASE,
)
_AMENDMENT = re.compile(
    r"^\W*(?:Дополнительное\s+соглашение|(?:Additional|Supplementary)\s+agreement)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(
    r"(?:№|\bNo\.?)\s*(?:\S+?\s*-\s*[DД]0*(\d+)|0*(\d+)\b)",
    re.IGNORECASE,
)


class Titled(Protocol):
    """Kind of a document told by its first line, and the number that this line carries."""

    def policy(self) -> bool: ...

    def amendment(self) -> bool: ...

    def number(self) -> tuple[int, ...]: ...


@final
class Title:
    """First non-blank line of a document that tells a general policy from an amendment.

    The file name is not consulted. An attachment that only mentions the policy does not start
    with its name, so it is not taken for the policy. An amendment number follows the suffix D of
    the policy number, with or without a space before the dash, or stands alone.
    """

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def policy(self) -> bool:
        return bool(_POLICY.search(self._line()))

    def amendment(self) -> bool:
        return bool(_AMENDMENT.search(self._line()))

    def number(self) -> tuple[int, ...]:
        return tuple(
            int(found[1] or found[2])
            for found in _NUMBER.finditer(self._line())
            if self.amendment()
        )[:1]

    def _line(self) -> str:
        return next((line for line in self._text.splitlines() if line.strip()), "")
