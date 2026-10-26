from decimal import Decimal

from hamcrest import assert_that, empty, equal_to

from app.declarations.sums import Currency, Sum
from app.domain.money import Amount


def test_currency_words_are_turned_into_iso_codes() -> None:
    assert_that(
        tuple(
            Currency(word).code()
            for word in (
                "рублей",
                "долларов США",
                "евро",
                "китайских юаней",
                "фунтов стерлингов",
                "швейцарский франк",
                "белорусских рублей",
            )
        ),
        equal_to(("RUB", "USD", "EUR", "CNY", "GBP", "CHF", "BYN")),
        "Currency words are not turned into ISO 4217 codes",
    )


def test_english_currency_words_and_iso_codes_are_known() -> None:
    assert_that(
        tuple(Currency(word).code() for word in ("Chinese yuan", "usd", "Euro", "Pounds")),
        equal_to(("CNY", "USD", "EUR", "GBP")),
        "English currency words and ISO codes are not known",
    )


def test_unknown_currency_has_an_empty_code() -> None:
    assert_that(
        Currency("бананов").code(), equal_to(""), "Unknown currency does not stay without a code"
    )


def test_sum_with_spaces_and_currency_becomes_an_amount() -> None:
    assert_that(
        Sum("252 000", "китайских юаней").amounts()[0].text(),
        equal_to(Amount(Decimal(252000), "CNY").text()),
        "Sum with spaces is not read as an amount in the currency",
    )


def test_sum_with_a_comma_fraction_is_read_exactly() -> None:
    assert_that(
        Sum("1 234 567,89", "рублей").amounts()[0].text(),
        equal_to(Amount(Decimal("1234567.89"), "RUB").text()),
        "Sum with a comma fraction is not read exactly",
    )


def test_sum_with_points_for_thousands_and_comma_for_fraction() -> None:
    assert_that(
        Sum("1.234.567,5", "евро").amounts()[0].text(),
        equal_to(Amount(Decimal("1234567.5"), "EUR").text()),
        "Sum with points for thousands is not read as a number",
    )


def test_sum_with_a_point_fraction_is_read_exactly() -> None:
    assert_that(
        Sum("11155860.81", "рублей").amounts()[0].text(),
        equal_to(Amount(Decimal("11155860.81"), "RUB").text()),
        "Sum with a point fraction is not read exactly",
    )


def test_sum_without_a_known_currency_is_unreadable() -> None:
    assert_that(
        Sum("100", "").amounts(),
        empty(),
        "Sum without a currency is read although the currency is not written",
    )


def test_sum_with_words_instead_of_a_number_is_unreadable() -> None:
    assert_that(
        Sum("согласно полису", "рублей").amounts(),
        empty(),
        "Sum written in words is not refused",
    )
