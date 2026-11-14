import re
from typing import Final, Protocol, final


class Numbers(Protocol):
    """Comparison of numbers of the general policy as the card of the policy field makes it."""

    def blank(self, text: str) -> bool: ...

    def same(self, declared: str, number: str) -> bool: ...


@final
class Numbered:
    """Numbers compared character by character without spaces and without the given characters;
    the number is a run of words of the declared text, so «№ 1 2» holds the number 12."""

    __slots__ = ("_ignore",)

    def __init__(self, ignore: tuple[str, ...]) -> None:
        self._ignore: Final = ignore

    def blank(self, text: str) -> bool:
        return not self._stripped(text).strip()

    def same(self, declared: str, number: str) -> bool:
        words = self._stripped(declared).split()
        wanted = re.sub(r"\s", "", self._stripped(number))
        return bool(wanted) and wanted in {
            "".join(words[start:end])
            for start in range(len(words))
            for end in range(start + 1, len(words) + 1)
        }

    def _stripped(self, text: str) -> str:
        return "".join(" " if char in self._ignore else char for char in text)
