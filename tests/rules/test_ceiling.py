import random
from decimal import Decimal

from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.money import Amount
from app.domain.place import Spot
from app.domain.policy import Vacant
from app.domain.status import Review
from app.domain.verdict import Verdict
from app.rules.answers import Replies
from app.rules.ceiling import Ceiling
from app.rules.wording import Comments
from tests.rules.fakes import Paper, Text


def _verdict(value: str, currency: str, limits: tuple[Amount, ...]) -> Verdict:
    return (
        Ceiling(Review())
        .outcome(
            Fields().field("sum", (value, currency)),
            Text("ГП п. 12", "лимит", amounts=limits),
            Paper("12", "vertical", ({"sum": (value, currency)},)).shipments()[0],
            Vacant("1"),
        )
        .verdict(
            Spot("12", "sum"),
            Comments(
                {
                    "match": "",
                    "mismatch": "Превышает лимит {limit}",
                    "review": "Сумма {amount}, лимит {limit}",
                }
            ),
            Replies((), ()),
        )
    )


def test_sum_under_the_limit_is_within() -> None:
    assert_that(
        _verdict(str(random.randint(1, 900000000)), "рублей", (Amount(Decimal(900000000), "RUB"),))
        .reason()
        .code(),
        equal_to("sum.within_limit"),
        "Ceiling does not accept a sum under the limit",
    )


def test_sum_equal_to_the_limit_is_within() -> None:
    assert_that(
        _verdict("900 000 000", "RUB", (Amount(Decimal(900000000), "RUB"),)).status().key(),
        equal_to("match"),
        "Ceiling does not accept a sum equal to the limit",
    )


def test_sum_over_the_limit_is_a_mismatch() -> None:
    assert_that(
        _verdict("920 000 000", "рублей", (Amount(Decimal(900000000), "RUB"),)).remark().comment(),
        equal_to("Превышает лимит 900 000 000,00 RUB"),
        "Ceiling does not reject a sum over the limit",
    )


def test_sum_in_another_currency_is_not_compared() -> None:
    verdict = _verdict("7 492 870", "китайских юаней", (Amount(Decimal(1000000), "EUR"),))
    assert_that(
        (verdict.status().key(), verdict.reason().code(), verdict.remark().comment()),
        equal_to(("review", "sum.currency", "Сумма 7 492 870,00 CNY, лимит 1 000 000,00 EUR")),
        "Ceiling does not leave a sum in another currency to a person",
    )


def test_limit_in_the_currency_of_the_sum_is_chosen() -> None:
    assert_that(
        _verdict(
            "5 000",
            "евро",
            (Amount(Decimal(900000000), "RUB"), Amount(Decimal(1000), "EUR")),
        )
        .reason()
        .code(),
        equal_to("sum.over_limit"),
        "Ceiling does not compare with the limit in the same currency",
    )


def test_unreadable_sum_needs_a_person() -> None:
    assert_that(
        _verdict("около миллиона", "рублей", (Amount(Decimal(1), "RUB"),)).reason().code(),
        equal_to("sum.unreadable"),
        "Ceiling does not ask for review of an unreadable sum",
    )
