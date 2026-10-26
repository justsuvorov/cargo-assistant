import random
import string
from datetime import date

from hamcrest import assert_that, contains_exactly, empty, equal_to

from app.declarations.fields import (
    Citing,
    Dating,
    Pricing,
    Read,
    Spanning,
    Split,
    Waybills,
    Whole,
)


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_read_field_keeps_its_key_and_is_filled() -> None:
    key = _word()
    field = Read(key, Whole((_word(),)))
    assert_that(
        (field.key(), field.filled()),
        equal_to((key, True)),
        "Read field does not keep its key or does not count as filled",
    )


def test_read_field_with_empty_text_is_not_filled() -> None:
    assert_that(
        Read(_word(), Whole(("  ",))).filled(),
        equal_to(False),
        "Read field with empty text does not count as blank",
    )


def test_whole_fact_has_its_text_as_the_only_entry() -> None:
    word = _word()
    assert_that(
        Whole((f" {word} ",)).entries(),
        contains_exactly(word),
        "Whole fact does not keep its text as the only entry",
    )


def test_split_fact_cuts_cargo_at_commas_and_semicolons() -> None:
    assert_that(
        Split(("мясо, сыр;\nмасло",), r"[,;\n]").entries(),
        contains_exactly("мясо", "сыр", "масло"),
        "Split fact does not cut a list of cargo at its separators",
    )


def test_split_fact_cuts_route_at_dashes_but_not_inside_words() -> None:
    assert_that(
        Split(
            ("Город, ул. Первая - Санкт-Петербург, лит. В- Псков",), r"\s*[-–—]\s+"
        ).entries(),
        contains_exactly("Город, ул. Первая", "Санкт-Петербург, лит. В", "Псков"),
        "Split fact does not cut a route at dashes only",
    )


def test_split_fact_drops_number_mark_of_an_item() -> None:
    assert_that(
        Split(("№550, 551, 552",), r"[,;\n]").entries(),
        contains_exactly("550", "551", "552"),
        "Split fact does not drop the number mark of an item",
    )


def test_dating_fact_reads_dates_of_a_list_with_one_year() -> None:
    assert_that(
        Dating(("14.09, 11.09.2026",)).dates(),
        contains_exactly(date(2026, 9, 14), date(2026, 9, 11)),
        "Dating fact does not read the dates of a list with one year",
    )


def test_dating_fact_has_no_entries() -> None:
    assert_that(
        Dating(("14.09.2026",)).entries(), empty(), "Dating fact does not leave its entries empty"
    )


def test_citing_fact_reads_the_date_after_the_number() -> None:
    assert_that(
        Citing(("№ 12/05 от 26.08.2025 г.",)).dates(),
        contains_exactly(date(2025, 8, 26)),
        "Citing fact does not skip the number of the document before the date",
    )


def test_spanning_fact_gives_start_and_end_of_a_period() -> None:
    assert_that(
        Spanning(("46286", "по", "20.10.2026")).dates(),
        contains_exactly(date(2026, 9, 21), date(2026, 10, 20)),
        "Spanning fact does not give the start and the end of a period",
    )


def test_spanning_fact_with_an_unreadable_end_has_no_dates() -> None:
    assert_that(
        Spanning(("21.09.2026", "по", "скоро")).dates(),
        empty(),
        "Spanning fact does not refuse a period with an unreadable end",
    )


def test_pricing_fact_gives_an_amount_with_the_currency_of_the_next_cell() -> None:
    assert_that(
        Pricing(("252 000", "китайских юаней")).amounts()[0].text(),
        equal_to("252 000,00 CNY"),
        "Pricing fact does not combine the number with the next cell currency",
    )


def test_pricing_fact_has_no_amounts_when_the_number_is_unreadable() -> None:
    assert_that(
        Pricing(("по счёту", "рублей")).amounts(),
        empty(),
        "Pricing fact guesses a number that is not written",
    )


def test_waybills_fact_splits_numbers_and_reads_the_date_cell() -> None:
    fact = Waybills(("№550, 551", "от", "17.09.2026"))
    assert_that(
        (fact.entries(), fact.dates(), fact.text()),
        equal_to((("550", "551"), (date(2026, 9, 17),), "№550, 551 от 17.09.2026")),
        "Waybills fact does not split numbers or does not read the date cell",
    )


def test_waybills_fact_reads_the_date_written_inside_the_number_cell() -> None:
    fact = Waybills(("771-12306011 от 19.09.2026",))
    assert_that(
        (fact.entries(), fact.dates()),
        equal_to((("771-12306011",), (date(2026, 9, 19),))),
        "Waybills fact does not read the date written after the number",
    )


def test_waybills_fact_does_not_take_a_number_for_a_date() -> None:
    assert_that(
        Waybills(("1409/1",)).dates(),
        empty(),
        "Waybills fact does not tell a number with a slash from a date",
    )
