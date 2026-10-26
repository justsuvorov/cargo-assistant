import re
from datetime import date
from typing import Final, final

from app.declarations.dates import Dates
from app.declarations.sums import Sum
from app.domain.fact import Fact
from app.domain.money import Money

_FROM = r"\s+(?:от|from|dated)\s+"


@final
class Joined:
    """Texts of the cells of a field written one after another."""

    __slots__ = ("_texts",)

    def __init__(self, texts: tuple[str, ...]) -> None:
        self._texts: Final = texts

    def text(self) -> str:
        return " ".join(text.strip() for text in self._texts if text.strip())


@final
class Read:
    """Declaration field: a key and the fact that its cells state."""

    __slots__ = ("_fact", "_key")

    def __init__(self, key: str, fact: Fact) -> None:
        self._key: Final = key
        self._fact: Final = fact

    def key(self) -> str:
        return self._key

    def filled(self) -> bool:
        return bool(self._fact.text())

    def text(self) -> str:
        return self._fact.text()

    def dates(self) -> tuple[date, ...]:
        return self._fact.dates()

    def amounts(self) -> tuple[Money, ...]:
        return self._fact.amounts()

    def entries(self) -> tuple[str, ...]:
        return self._fact.entries()


@final
class Whole:
    """Fact with one value that the checks compare as a whole."""

    __slots__ = ("_texts",)

    def __init__(self, texts: tuple[str, ...]) -> None:
        self._texts: Final = texts

    def text(self) -> str:
        return Joined(self._texts).text()

    def dates(self) -> tuple[date, ...]:
        return ()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return (self.text(),)


@final
class Split:
    """Fact that is a list of items cut at a separator pattern, such as a list of cargo."""

    __slots__ = ("_separator", "_texts")

    def __init__(self, texts: tuple[str, ...], separator: str) -> None:
        self._texts: Final = texts
        self._separator: Final = separator

    def text(self) -> str:
        return Joined(self._texts).text()

    def dates(self) -> tuple[date, ...]:
        return ()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return tuple(
            item
            for part in re.split(self._separator, self.text())
            if (item := re.sub(r"^№\s*", "", part.strip()))
        )


@final
class Dating:
    """Fact that holds dates, such as the date of a transport document."""

    __slots__ = ("_texts",)

    def __init__(self, texts: tuple[str, ...]) -> None:
        self._texts: Final = texts

    def text(self) -> str:
        return Joined(self._texts).text()

    def dates(self) -> tuple[date, ...]:
        return tuple(day for text in self._texts for day in Dates(text).dates())

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return ()


@final
class Citing:
    """Fact that cites a document by number and date, such as the policy."""

    __slots__ = ("_texts",)

    def __init__(self, texts: tuple[str, ...]) -> None:
        self._texts: Final = texts

    def text(self) -> str:
        return Joined(self._texts).text()

    def dates(self) -> tuple[date, ...]:
        return Dates(re.split(_FROM, self.text(), maxsplit=1)[-1]).dates()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return (self.text(),)


@final
class Spanning:
    """Fact of a period: the start and the end together, or no dates if either is unreadable."""

    __slots__ = ("_texts",)

    def __init__(self, texts: tuple[str, ...]) -> None:
        self._texts: Final = texts

    def text(self) -> str:
        return Joined(self._texts).text()

    def dates(self) -> tuple[date, ...]:
        found = Dating(self._texts).dates()
        return found if len(found) == len(("start", "end")) else ()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        return ()


@final
class Pricing:
    """Fact of an insured sum: the number comes first, its currency second."""

    __slots__ = ("_texts",)

    def __init__(self, texts: tuple[str, ...]) -> None:
        self._texts: Final = texts

    def text(self) -> str:
        return Joined(self._texts).text()

    def dates(self) -> tuple[date, ...]:
        return ()

    def amounts(self) -> tuple[Money, ...]:
        value, currency = (*self._texts, "", "")[:2]
        return Sum(value, currency).amounts()

    def entries(self) -> tuple[str, ...]:
        return (self.text(),)


@final
class Waybills:
    """Fact of a transport document: numbers before the word «от», dates after it."""

    __slots__ = ("_texts",)

    def __init__(self, texts: tuple[str, ...]) -> None:
        self._texts: Final = texts

    def text(self) -> str:
        return Joined(self._texts).text()

    def dates(self) -> tuple[date, ...]:
        first, *rest = (*self._texts, "")
        return Dating((*re.split(_FROM, first, maxsplit=1)[1:], *rest)).dates()

    def amounts(self) -> tuple[Money, ...]:
        return ()

    def entries(self) -> tuple[str, ...]:
        head = re.split(_FROM, (*self._texts, "")[0], maxsplit=1)[0]
        return Split((head,), r"[,;\n]").entries()
