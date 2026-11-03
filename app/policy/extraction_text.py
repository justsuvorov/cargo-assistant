import re
from datetime import date
from decimal import Decimal
from typing import Final, Protocol, final

_GAP = r"[\s«»\"“”„'’|]*"
_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_CURRENCIES = (
    ("BYN", r"\bBYN\b|белорусск\w*\s+рубл"),
    ("KZT", r"\bKZT\b|\bтенге\b"),
    ("UAH", r"\bUAH\b|\bгривн"),
    ("RUB", r"\bRUB\b|\bRUR\b|\bруб(?:л|\.|\b)|₽"),
    ("USD", r"\bUSD\b|\bдолл|\$"),
    ("EUR", r"\bEUR\b|\bевро\b|€"),
    ("CNY", r"\bCNY\b|\bюан"),
    ("GBP", r"\bGBP\b|\bфунт\w*\s+стерл|£"),
    ("CHF", r"\bCHF\b|\bшвейцарск\w*\s+франк"),
    ("JPY", r"\bJPY\b|\b[ий]ен[аыу]?\b"),
    ("AED", r"\bAED\b|\bдирхам"),
    ("TRY", r"\bTRY\b|\bтурецк\w*\s+лир"),
    ("INR", r"\bINR\b|\bрупи"),
)


class Evidence(Protocol):
    """Source text of a document that tells whether a value from an answer stands in it."""

    def dated(self, day: date) -> bool: ...

    def priced(self, value: Decimal, currency: str) -> bool: ...

    def names(self, point: str) -> bool: ...

    def numbered(self, point: str) -> bool: ...

    def quotes(self, phrase: str) -> bool: ...


@final
class Original:
    """Text of a document searched for the written forms of a value.

    A value that may only be a piece of a longer number or date does not count as found: a
    wrongly refused value goes to the expert, a wrongly accepted one would stay unnoticed.
    """

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def dated(self, day: date) -> bool:
        return any(
            re.search(form, self._text, re.IGNORECASE)
            for form in (
                rf"(?<![\d.])0?{day.day}[./-]0?{day.month}[./-]"
                rf"(?:{day.year}|{day.year % 100:02d})(?!\d|\.\d)",
                rf"(?<![\d.]){day.year}-{day.month:02d}-{day.day:02d}(?!\d)",
                rf"(?<![\d.])0?{day.day}[\s«»\"“”„'’]*{_MONTHS[day.month - 1]}\s*{day.year}(?!\d)",
            )
        )

    def priced(self, value: Decimal, currency: str) -> bool:
        return bool(currency) and any(
            self._nearest(self._text[found.end() : found.end() + 100]) == currency
            or self._before(found.start(), currency)
            for found in re.finditer(self._figure(value), self._text)
        )

    def names(self, point: str) -> bool:
        return bool(point) and bool(
            re.search(
                r"(?:пункт\w*|(?<![а-яё])пп?\.)\s*(?:[\d.]+(?:\s*,\s*|\s+и\s+))*"
                rf"{re.escape(point)}(?!\d|\.\d)",
                self._text,
                re.IGNORECASE,
            )
        )

    def numbered(self, point: str) -> bool:
        return self.names(point) or (
            bool(point)
            and bool(
                re.search(
                    rf"(?:^|\|)[^\S\n]*{re.escape(point)}(?!\d|\.\d)",
                    self._text,
                    re.MULTILINE,
                )
            )
        )

    def quotes(self, phrase: str) -> bool:
        letters = re.sub(_GAP, "", phrase)
        return bool(letters) and bool(
            re.search(
                rf"(?<![\w/-]){_GAP.join(map(re.escape, letters))}(?![\w/-])",
                self._text,
                re.IGNORECASE,
            )
        )

    def _figure(self, value: Decimal) -> str:
        whole, _, fraction = f"{value.normalize():f}".partition(".")
        cents = rf"[.,]{fraction}0*" if fraction else r"(?:[.,]0+)?"
        groups = r"[\s.,'’]?".join(f"{int(whole):,}".split(","))
        return (
            rf"(?<!\d)(?<!\d[\s.,'’]){groups}{cents}"
            r"(?![.,]?\d)(?!\s\d{3}(?!\d))"
        )

    def _before(self, start: int, currency: str) -> bool:
        return self._nearest(self._text[max(0, start - 15) : start]) == currency

    def _nearest(self, fragment: str) -> str:
        return min(
            (
                (found.start(), code)
                for code, pattern in _CURRENCIES
                for found in re.finditer(pattern, fragment, re.IGNORECASE)
            ),
            default=(0, ""),
        )[1]
