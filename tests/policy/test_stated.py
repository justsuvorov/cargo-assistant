from datetime import date

from hamcrest import assert_that, contains_exactly, empty

from app.policy.stated import Stated


def test_reads_date_with_day_in_quotes_and_month_name() -> None:
    assert_that(
        Stated("г. Город      «26» ноября 2020 г.").dates(),
        contains_exactly(date(2020, 11, 26)),
        "Stated does not read a day in quotes followed by a month name",
    )


def test_reads_date_with_extra_spaces_after_quotes() -> None:
    assert_that(
        Stated("«23»  июня 2019 г.").dates(),
        contains_exactly(date(2019, 6, 23)),
        "Stated does not read a date with two spaces after the quotes",
    )


def test_reads_dotted_date() -> None:
    assert_that(
        Stated("с 19.11.2024 г. по 18.11.2026 г.").dates(),
        contains_exactly(date(2024, 11, 19), date(2026, 11, 18)),
        "Stated does not read dotted dates in the order of writing",
    )


def test_reads_english_month_name() -> None:
    assert_that(
        Stated("Moscow, 5 March 2026").dates(),
        contains_exactly(date(2026, 3, 5)),
        "Stated does not read an English month name",
    )


def test_skips_year_with_a_typo_of_five_digits() -> None:
    assert_that(
        Stated("от 20.10.20217 г.").dates(),
        empty(),
        "Stated does not skip a dotted date whose year has five digits",
    )


def test_skips_blank_placeholder_of_a_date() -> None:
    assert_that(
        Stated("«     »            2026 г.").dates(),
        empty(),
        "Stated does not skip a date left blank in a draft",
    )


def test_skips_impossible_day() -> None:
    assert_that(
        Stated("31.02.2026").dates(),
        empty(),
        "Stated does not skip a day that the month does not have",
    )
