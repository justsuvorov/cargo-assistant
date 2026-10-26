from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final, Protocol, final


class Rendering(Protocol):
    """Value of a spreadsheet cell that is turned into the text a person would read."""

    def text(self) -> str: ...


@final
class Figure:
    """Number rendered without exponent and without the trailing zero of a whole float."""

    __slots__ = ("_value",)

    def __init__(self, value: object) -> None:
        self._value: Final = value

    def text(self) -> str:
        if not self._value:
            return ""
        return format(Decimal(repr(self._value)).normalize(), "f")


@final
class Day:
    """Calendar day given in ISO form and rendered as DD.MM.YYYY, the form of declarations."""

    __slots__ = ("_iso",)

    def __init__(self, iso: str) -> None:
        self._iso: Final = iso

    def text(self) -> str:
        return datetime.fromisoformat(self._iso).strftime("%d.%m.%Y")


@final
class Serial:
    """Spreadsheet serial day number rendered as DD.MM.YYYY for the 1900 or 1904 date system."""

    __slots__ = ("_mode", "_number")

    def __init__(self, number: float, mode: int) -> None:
        self._number: Final = number
        self._mode: Final = mode

    def text(self) -> str:
        start = {1: datetime(1904, 1, 1)}.get(self._mode, datetime(1899, 12, 30))
        return (start + timedelta(days=self._number)).strftime("%d.%m.%Y")
