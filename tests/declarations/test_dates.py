from datetime import date

from hamcrest import assert_that, contains_exactly, empty

from app.declarations.dates import Dates


def test_reads_serial_day_number() -> None:
    assert_that(
        Dates("46286").dates(),
        contains_exactly(date(2026, 9, 21)),
        "Dates do not read a serial day number",
    )


def test_reads_serial_day_number_written_as_float() -> None:
    assert_that(
        Dates("46286.0").dates(),
        contains_exactly(date(2026, 9, 21)),
        "Dates do not read a serial day number with a zero fraction",
    )


def test_reads_dotted_date_with_a_trailing_semicolon() -> None:
    assert_that(
        Dates("17.09.2026;").dates(),
        contains_exactly(date(2026, 9, 17)),
        "Dates do not read a dotted date followed by a semicolon",
    )


def test_reads_dotted_date_with_two_digit_year() -> None:
    assert_that(
        Dates("14.05.26").dates(),
        contains_exactly(date(2026, 5, 14)),
        "Dates do not read a dotted date with a two-digit year",
    )


def test_reads_russian_month_name_with_year_mark() -> None:
    assert_that(
        Dates("15 сентября 2026 г.").dates(),
        contains_exactly(date(2026, 9, 15)),
        "Dates do not read a Russian month name",
    )


def test_reads_english_month_names_in_both_orders() -> None:
    assert_that(
        Dates("15 September 2026 and Oct 3rd, 2026").dates(),
        contains_exactly(date(2026, 9, 15), date(2026, 10, 3)),
        "Dates do not read English month names in both orders",
    )


def test_reads_iso_date() -> None:
    assert_that(
        Dates("2026-09-05").dates(),
        contains_exactly(date(2026, 9, 5)),
        "Dates do not read an ISO date",
    )


def test_list_without_years_takes_the_year_from_the_end() -> None:
    assert_that(
        Dates("10.09, 16.09, 16.09, 04.09, 16.09,.14.09.2026").dates(),
        contains_exactly(
            date(2026, 9, 10),
            date(2026, 9, 16),
            date(2026, 9, 16),
            date(2026, 9, 4),
            date(2026, 9, 16),
            date(2026, 9, 14),
        ),
        "Dates do not give the year at the end of a list to every date before it",
    )


def test_list_without_any_year_is_unreadable() -> None:
    assert_that(Dates("10.09, 16.09").dates(), empty(), "Dates guess a year that no one wrote")


def test_impossible_date_makes_the_whole_text_unreadable() -> None:
    assert_that(
        Dates("17.09.2026, 31.02.2026").dates(),
        empty(),
        "Dates do not refuse a text that holds an impossible date",
    )


def test_text_without_dates_has_no_dates() -> None:
    assert_that(Dates("нет").dates(), empty(), "Dates invent a date although the text has no dates")


def test_document_number_with_a_slash_is_not_a_date() -> None:
    assert_that(Dates("1409/1").dates(), empty(), "Dates do not tell a document number from a date")
