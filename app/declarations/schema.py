from collections.abc import Callable
from typing import Protocol, final

from app.declarations.fields import (
    Citing,
    Dating,
    Pricing,
    Read,
    Spanning,
    Split,
    Waybills,
    Whole,
)
from app.domain.fact import Fact
from app.domain.field import Blank, Field

_LIST = r"[,;\n]"
_ROUTE = r"\s*[-–—]\s+"
_TRANSPORT = r"\s*[+,;/]\s*"
_FACTS: dict[str, Callable[[tuple[str, ...]], Fact]] = {
    "insurer": Whole,
    "policy": Citing,
    "cargo": lambda texts: Split(texts, _LIST),
    "packaging": Whole,
    "beneficiary": Whole,
    "sum": Pricing,
    "transport": lambda texts: Split(texts, _TRANSPORT),
    "departure": lambda texts: Split(texts, _ROUTE),
    "transshipment": lambda texts: Split(texts, _ROUTE),
    "destination": lambda texts: Split(texts, _ROUTE),
    "period": Spanning,
    "period_start": Dating,
    "period_end": Dating,
    "document": Waybills,
    "document_number": lambda texts: Split(texts, _LIST),
    "document_date": Dating,
    "carrier": Whole,
    "sealing": Whole,
    "other": Whole,
}


class Schema(Protocol):
    """Rule that turns the cell texts of a field key into a normalised field."""

    def field(self, key: str, texts: tuple[str, ...]) -> Field: ...


@final
class Fields:
    """Schema of the fifteen keys of the contracts; an unknown or empty field is a Blank."""

    __slots__ = ()

    def field(self, key: str, texts: tuple[str, ...]) -> Field:
        if key in _FACTS and any(text.strip() for text in texts):
            return Read(key, _FACTS[key](texts))
        return Blank(key)
