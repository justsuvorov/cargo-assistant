from decimal import Decimal
from typing import Final, Protocol, final

from app.domain.errors import IncomparableError


class Money(Protocol):
    """Sum of money in one currency, declared by a client or limited by a policy."""

    def exceeds(self, other: "Money") -> bool: ...

    def under(self, value: Decimal, currency: str) -> bool: ...

    def text(self) -> str: ...


@final
class Amount:
    """Exact decimal sum in an ISO 4217 currency code."""

    __slots__ = ("_currency", "_value")

    def __init__(self, value: Decimal, currency: str) -> None:
        self._value: Final = value
        self._currency: Final = currency

    def exceeds(self, other: Money) -> bool:
        return other.under(self._value, self._currency)

    def under(self, value: Decimal, currency: str) -> bool:
        if currency != self._currency:
            raise IncomparableError(
                f"Сумму в {currency} нельзя сравнить с {self._currency} без курса"
            )
        return self._value < value

    def text(self) -> str:
        return f"{self._value:,.2f} {self._currency}".replace(",", " ").replace(".", ",")
