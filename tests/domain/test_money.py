import random
from decimal import Decimal

from hamcrest import assert_that, equal_to, raises

from app.domain.errors import IncomparableError
from app.domain.money import Amount


def test_bigger_amount_exceeds_smaller_limit() -> None:
    limit = random.randint(1, 10**9)
    assert_that(
        Amount(Decimal(limit + 1), "RUB").exceeds(Amount(Decimal(limit), "RUB")),
        equal_to(True),
        "Bigger amount does not exceed smaller limit",
    )


def test_equal_amount_does_not_exceed_limit() -> None:
    limit = Decimal(random.randint(1, 10**9)) / 100
    assert_that(
        Amount(limit, "EUR").exceeds(Amount(limit, "EUR")),
        equal_to(False),
        "Amount equal to limit is not allowed",
    )


def test_amounts_in_different_currencies_cannot_be_compared() -> None:
    assert_that(
        lambda: Amount(Decimal(random.randint(1, 99)), "CNY").exceeds(
            Amount(Decimal(random.randint(100, 999)), "RUB")
        ),
        raises(IncomparableError),
        "Amounts in different currencies are not refused without a rate",
    )


def test_amount_prints_with_grouped_thousands() -> None:
    assert_that(
        Amount(Decimal("7492870"), "RUB").text(),
        equal_to("7 492 870,00 RUB"),
        "Amount is not printed in Russian number format",
    )
