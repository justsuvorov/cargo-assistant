import re
from datetime import date
from typing import Final, Protocol, final

_MONTHS = {
    **dict.fromkeys(("января", "january", "jan"), 1),
    **dict.fromkeys(("февраля", "february", "feb"), 2),
    **dict.fromkeys(("марта", "march", "mar"), 3),
    **dict.fromkeys(("апреля", "april", "apr"), 4),
    **dict.fromkeys(("мая", "may"), 5),
    **dict.fromkeys(("июня", "june", "jun"), 6),
    **dict.fromkeys(("июля", "july", "jul"), 7),
    **dict.fromkeys(("августа", "august", "aug"), 8),
    **dict.fromkeys(("сентября", "september", "sep", "sept"), 9),
    **dict.fromkeys(("октября", "october", "oct"), 10),
    **dict.fromkeys(("ноября", "november", "nov"), 11),
    **dict.fromkeys(("декабря", "december", "dec"), 12),
}
_WORDS = "|".join(sorted(_MONTHS, key=len, reverse=True))
_PATTERN = re.compile(
    r"(?<!\d)(?P<dd>\d{2})\.(?P<dm>\d{2})\.(?P<dy>\d{4})(?!\d)"
    rf"|(?<!\d)(?P<wd>\d{{1,2}})\s*[»\"]?\s*(?P<wm>{_WORDS})\.?\s+(?P<wy>\d{{4}})(?!\d)",
    re.IGNORECASE,
)


class Dated(Protocol):
    """Dates written in a text of a document, in the order of writing."""

    def dates(self) -> tuple[date, ...]: ...


@final
class Stated:
    """Dates of a legal text written as DD.MM.YYYY or as a day in quotes with a month name.

    A date that cannot exist, a year with a typo and a blank placeholder are skipped.
    """

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def dates(self) -> tuple[date, ...]:
        return tuple(
            found for match in _PATTERN.finditer(self._text) for found in self._date(match)
        )

    def _date(self, match: re.Match[str]) -> tuple[date, ...]:
        try:
            return (
                (date(int(match["dy"]), int(match["dm"]), int(match["dd"])),)
                if match["dd"]
                else (date(int(match["wy"]), _MONTHS[match["wm"].casefold()], int(match["wd"])),)
            )
        except ValueError:
            return ()
