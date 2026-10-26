import re
from decimal import Decimal
from typing import Final, Protocol, final

from app.domain.money import Amount, Money

_CURRENCIES = (
    ("BYN", ("белорус", "belarus")),
    ("KZT", ("тенге", "tenge")),
    ("UAH", ("гривн", "hryvn")),
    ("RUB", ("руб", "rouble", "ruble", "₽")),
    ("USD", ("доллар", "dollar", "$")),
    ("EUR", ("евро", "euro", "€")),
    ("CNY", ("юан", "yuan", "renminbi")),
    ("GBP", ("фунт", "pound", "£")),
    ("CHF", ("франк", "franc")),
    ("JPY", ("иен", "йен", "yen")),
    ("AED", ("дирхам", "dirham")),
    ("TRY", ("лир", "lira")),
    ("INR", ("рупи", "rupee")),
)


class Tender(Protocol):
    """Currency named in a text, as an ISO 4217 code that is empty if the text names none."""

    def code(self) -> str: ...


class Cash(Protocol):
    """Sums that a pair of texts, the number and its currency, state together."""

    def amounts(self) -> tuple[Money, ...]: ...


@final
class Currency:
    """Currency named by an ISO code or by a word such as рублей, евро or китайских юаней."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def code(self) -> str:
        lowered = self._text.casefold()
        return next(
            (
                code
                for code, stems in _CURRENCIES
                if re.search(rf"(?<![a-z]){code.lower()}(?![a-z])", lowered)
                or any(stem in lowered for stem in stems)
            ),
            "",
        )


@final
class Sum:
    """Amount written as a number with spaces, a comma or a point, next to a currency text."""

    __slots__ = ("_currency", "_value")

    def __init__(self, value: str, currency: str) -> None:
        self._value: Final = value
        self._currency: Final = currency

    def amounts(self) -> tuple[Money, ...]:
        code = Currency(self._currency).code()
        return tuple(Amount(number, code) for number in self._numbers() if code)

    def _numbers(self) -> tuple[Decimal, ...]:
        # @todo #2:30min Уточнить, как читать «1,234»: тысячи или дробь, сейчас дробь
        text = re.sub(r"\s", "", self._value)
        last = max(text.rfind(","), text.rfind("."))
        both = "," in text and "." in text
        single = len(re.findall(r"[.,]", text)) == 1
        cut = last if both or single else len(text)
        whole = re.sub(r"[.,]", "", text[:cut])
        fraction = text[cut + 1 :]
        if re.fullmatch(r"\d+", whole) and re.fullmatch(r"\d*", fraction):
            return (Decimal(f"{whole}.{fraction}" if fraction else whole),)
        return ()
