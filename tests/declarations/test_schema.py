from datetime import date

from hamcrest import assert_that, contains_exactly, equal_to

from app.declarations.schema import Fields


def test_empty_texts_give_a_blank_field() -> None:
    assert_that(
        Fields().field("cargo", (" ",)).filled(),
        equal_to(False),
        "Schema does not give a blank field for empty texts",
    )


def test_unknown_key_gives_a_blank_field() -> None:
    assert_that(
        Fields().field("weather", ("sunny",)).filled(),
        equal_to(False),
        "Schema does not give a blank field for a key that contracts do not know",
    )


def test_transport_is_cut_at_plus_comma_and_slash() -> None:
    assert_that(
        Fields().field("transport", ("Авто+авиа+авто / ООО",)).entries(),
        contains_exactly("Авто", "авиа", "авто", "ООО"),
        "Schema does not cut transport at plus, comma and slash",
    )


def test_period_gives_both_dates() -> None:
    assert_that(
        Fields().field("period", ("21.09.2026", "по", "24.09.2026")).dates(),
        contains_exactly(date(2026, 9, 21), date(2026, 9, 24)),
        "Schema does not read both dates of a period",
    )


def test_sum_gives_amount_with_currency_from_the_second_text() -> None:
    assert_that(
        Fields().field("sum", ("7492870", "рублей")).amounts()[0].text(),
        equal_to("7 492 870,00 RUB"),
        "Schema does not read the sum with the currency of the second text",
    )
