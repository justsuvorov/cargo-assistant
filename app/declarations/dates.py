import re
from datetime import date, timedelta
from typing import Final, Protocol, final

_MONTHS = [
    *("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"),
    *("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
]
_WORD = "(?:" + "|".join(_MONTHS) + r")[^\W\d_]{0,6}"
_PATTERN = re.compile(
    r"(?<!\d)(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})(?!\d)"
    r"|(?<!\d)(?P<nd>\d{1,2})[./](?P<nm>\d{1,2})(?:[./](?P<ny>\d{4}|\d{2}))?(?!\d)"
    rf"|(?<!\d)(?P<td>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<tm>{_WORD})\.?,?\s+(?P<ty>\d{{4}})(?!\d)"
    rf"|(?<![^\W\d_])(?P<em>{_WORD})\.?\s+(?P<ed>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<ey>\d{{4}})(?!\d)",
    re.IGNORECASE,
)
_GROUPS = (("id", "im", "iy"), ("nd", "nm", "ny"), ("td", "tm", "ty"), ("ed", "em", "ey"))
_SERIAL = range(30000, 80001)


class Calendar(Protocol):
    """Dates that a text names, in the order of writing, or none if any of them is unreadable."""

    def dates(self) -> tuple[date, ...]: ...


@final
class Dates:
    """Calendar of a text with serial day numbers, DD.MM.YYYY, lists with one year and months.

    A day and a month without a year take the year of the nearest date to the right, as in
    "10.09, 16.09, 14.09.2026".
    """

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def dates(self) -> tuple[date, ...]:
        return self._serial() or self._written()

    def _serial(self) -> tuple[date, ...]:
        found = re.fullmatch(r"(\d{5})(?:\.0+)?", self._text.strip())
        if found and int(found[1]) in _SERIAL:
            return (date(1899, 12, 30) + timedelta(days=int(found[1])),)
        return ()

    def _written(self) -> tuple[date, ...]:
        parts = tuple(self._parts(found) for found in _PATTERN.finditer(self._text))
        try:
            return tuple(date(year, month, day) for day, month, year in self._completed(parts))
        except ValueError:
            return ()

    def _parts(self, found: re.Match[str]) -> tuple[int, int, int]:
        day, month, year = next(names for names in _GROUPS if found[names[0]])
        return (int(found[day]), self._month(found[month]), self._year(found[year] or ""))

    def _month(self, text: str) -> int:
        return int(text) if text.isdigit() else _MONTHS.index(text[:3].casefold()) % 12 + 1

    def _year(self, text: str) -> int:
        return {2: 2000}.get(len(text), 0) + int(text or 0)

    def _completed(
        self, parts: tuple[tuple[int, int, int], ...]
    ) -> tuple[tuple[int, int, int], ...]:
        year = 0
        done = []
        for day, month, given in reversed(parts):
            year = given or year
            done.append((day, month, year))
        return tuple(reversed(done))
