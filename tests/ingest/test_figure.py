import random

from hamcrest import assert_that, equal_to

from app.ingest.figure import Day, Figure, Serial


def test_whole_float_has_no_trailing_zero() -> None:
    whole = random.randint(1, 10**9)
    assert_that(
        Figure(float(whole)).text(),
        equal_to(str(whole)),
        "Whole float is not rendered without the fraction",
    )


def test_round_number_has_no_exponent() -> None:
    assert_that(
        Figure(100000000000.0).text(),
        equal_to("100000000000"),
        "Round number is not rendered without exponent",
    )


def test_fraction_is_kept_exactly() -> None:
    assert_that(
        Figure(11155860.81).text(),
        equal_to("11155860.81"),
        "Fraction of a number is not kept exactly",
    )


def test_empty_value_is_rendered_as_empty_text() -> None:
    assert_that(Figure("").text(), equal_to(""), "Empty value is not rendered as empty text")


def test_day_is_rendered_with_dots() -> None:
    assert_that(
        Day("2026-09-05 00:00:00").text(),
        equal_to("05.09.2026"),
        "Day is not rendered as DD.MM.YYYY",
    )


def test_serial_number_is_rendered_as_a_day() -> None:
    assert_that(
        Serial(46286.0, 0).text(),
        equal_to("21.09.2026"),
        "Serial number is not rendered as a day of the 1900 system",
    )


def test_serial_number_of_the_1904_system_is_shifted() -> None:
    assert_that(
        Serial(44824.0, 1).text(),
        equal_to("21.09.2026"),
        "Serial number is not rendered as a day of the 1904 system",
    )
