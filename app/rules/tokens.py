import re
from collections import Counter
from collections.abc import Mapping
from typing import Final, Protocol, final


class Bag(Protocol):
    """Words of a name that compare regardless of case, quotes, spaces and order."""

    def words(self) -> tuple[str, ...]: ...

    def same(self, other: "Bag") -> bool: ...

    def within(self, other: "Bag") -> bool: ...


@final
class Tokens:
    """Bag of the words of a text in lower case, with ё read as е and every abbreviation
    from the synonyms spelled out in full."""

    __slots__ = ("_synonyms", "_text")

    def __init__(self, text: str, synonyms: Mapping[str, str]) -> None:
        self._text: Final = text
        self._synonyms: Final = synonyms

    def words(self) -> tuple[str, ...]:
        folded = self._text.casefold().replace("ё", "е")
        for short, full in self._synonyms.items():
            folded = re.sub(
                rf"(?<!\w){re.escape(short.casefold().replace('ё', 'е'))}(?!\w)",
                full.casefold().replace("ё", "е"),
                folded,
            )
        return tuple(sorted(re.findall(r"\w+", folded)))

    def same(self, other: Bag) -> bool:
        return bool(self.words()) and self.words() == other.words()

    def within(self, other: Bag) -> bool:
        return bool(self.words()) and Counter(self.words()) <= Counter(other.words())
