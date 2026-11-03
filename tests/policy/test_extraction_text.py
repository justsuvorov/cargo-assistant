import random
import uuid
from datetime import date
from decimal import Decimal

from hamcrest import assert_that, equal_to

from app.policy.extraction_text import Original


def test_finds_a_date_written_with_points() -> None:
    day = date(random.randint(2000, 2030), random.randint(1, 12), random.randint(1, 28))
    assert_that(
        Original(f"Срок с {day:%d.%m.%Y} г.").dated(day),
        equal_to(True),
        "Date written with points is not found",
    )


def test_finds_a_date_without_leading_zeros() -> None:
    assert_that(
        Original("Подписан 1.9.2026").dated(date(2026, 9, 1)),
        equal_to(True),
        "Date without leading zeros is not found",
    )


def test_finds_a_date_with_a_short_year() -> None:
    assert_that(
        Original("Подписан 01.09.26").dated(date(2026, 9, 1)),
        equal_to(True),
        "Date with a short year is not found",
    )


def test_finds_a_date_written_in_iso_form() -> None:
    assert_that(
        Original("Срок: 2026-09-01").dated(date(2026, 9, 1)),
        equal_to(True),
        "Date written in ISO form is not found",
    )


def test_finds_a_date_with_the_day_in_quotes_and_a_month_word() -> None:
    assert_that(
        Original("от «01» сентября 2026 г.").dated(date(2026, 9, 1)),
        equal_to(True),
        "Date with the day in quotes and a month word is not found",
    )


def test_finds_a_date_with_a_month_word_and_no_break_spaces() -> None:
    assert_that(
        Original("с\xa01\xa0марта\xa02027\xa0года").dated(date(2027, 3, 1)),
        equal_to(True),
        "Date with a month word and no-break spaces is not found",
    )


def test_refuses_a_date_of_another_day() -> None:
    assert_that(
        Original("Срок с 02.09.2026").dated(date(2026, 9, 1)),
        equal_to(False),
        "Date of another day is not refused",
    )


def test_refuses_a_date_of_another_month_word() -> None:
    assert_that(
        Original("«01» октября 2026 г.").dated(date(2026, 9, 1)),
        equal_to(False),
        "Date of another month written as a word is not refused",
    )


def test_refuses_a_date_read_out_of_a_mistyped_year() -> None:
    assert_that(
        Original("Срок с 20.10.20217").dated(date(2021, 10, 20)),
        equal_to(False),
        "Date read out of a mistyped year is not refused",
    )


def test_refuses_a_date_read_out_of_a_clause_number() -> None:
    assert_that(
        Original("пункт 3.4.28.1").dated(date(2028, 4, 3)),
        equal_to(False),
        "Date read out of a clause number is not refused",
    )


def test_finds_a_sum_with_spaces_and_kopecks() -> None:
    assert_that(
        Original("Лимит 200 000 000,00 рублей").priced(Decimal("200000000"), "RUB"),
        equal_to(True),
        "Sum with spaces and kopecks is not found",
    )


def test_finds_a_sum_with_no_break_spaces() -> None:
    assert_that(
        Original("Лимит 200\xa0000\xa0000\xa0руб.").priced(Decimal("200000000.00"), "RUB"),
        equal_to(True),
        "Sum with no-break spaces is not found",
    )


def test_finds_a_sum_without_separators() -> None:
    value = random.randint(1000, 999999999)
    assert_that(
        Original(f"Лимит {value} USD").priced(Decimal(value), "USD"),
        equal_to(True),
        "Sum without separators is not found",
    )


def test_finds_a_sum_with_points_between_thousands() -> None:
    assert_that(
        Original("Лимит 1.500.000,00 евро").priced(Decimal("1500000"), "EUR"),
        equal_to(True),
        "Sum with points between thousands is not found",
    )


def test_finds_a_sum_with_a_fraction() -> None:
    assert_that(
        Original("Лимит 1 234,50 руб.").priced(Decimal("1234.5"), "RUB"),
        equal_to(True),
        "Sum with a fraction is not found",
    )


def test_finds_a_sum_with_the_currency_spelled_after_the_words() -> None:
    assert_that(
        Original("900 000 000 (девятьсот миллионов) рублей").priced(Decimal("900000000"), "RUB"),
        equal_to(True),
        "Sum with the currency spelled after the words is not found",
    )


def test_finds_a_sum_with_the_currency_code_before_it() -> None:
    assert_that(
        Original("Лимит: USD 5 000 000").priced(Decimal("5000000"), "USD"),
        equal_to(True),
        "Sum with the currency code before it is not found",
    )


def test_finds_a_sum_with_the_currency_in_the_next_cell() -> None:
    assert_that(
        Original("Лимит | 5 000 000 | EUR").priced(Decimal("5000000"), "EUR"),
        equal_to(True),
        "Sum with the currency in the next table cell is not found",
    )


def test_finds_a_sum_in_one_of_two_currencies_of_the_text() -> None:
    assert_that(
        Original("Лимит 7 000 долларов США, а также 9 000 рублей").priced(Decimal("9000"), "RUB"),
        equal_to(True),
        "Sum in one of two currencies of the text is not found",
    )


def test_refuses_a_sum_read_out_of_a_larger_number() -> None:
    assert_that(
        Original("Лимит 1 200 000 000 рублей").priced(Decimal("200000000"), "RUB"),
        equal_to(False),
        "Sum read out of a larger number is not refused",
    )


def test_refuses_a_sum_that_is_the_head_of_a_larger_number() -> None:
    assert_that(
        Original("Лимит 200 000 000 рублей").priced(Decimal("200000"), "RUB"),
        equal_to(False),
        "Sum that is the head of a larger number is not refused",
    )


def test_refuses_a_sum_with_other_kopecks() -> None:
    assert_that(
        Original("Лимит 1 000,50 рублей").priced(Decimal("1000"), "RUB"),
        equal_to(False),
        "Sum that differs only in kopecks is not refused",
    )


def test_refuses_a_sum_read_out_of_a_date() -> None:
    assert_that(
        Original("Подписан 01.09.2026 руб.").priced(Decimal("2026"), "RUB"),
        equal_to(False),
        "Sum read out of a date is not refused",
    )


def test_refuses_a_sum_that_stands_in_another_currency() -> None:
    assert_that(
        Original("Лимит 5 000 000 долларов США, премия уплачена в рублях").priced(
            Decimal("5000000"), "RUB"
        ),
        equal_to(False),
        "Sum that stands in another currency is not refused",
    )


def test_refuses_a_sum_with_the_currency_far_away() -> None:
    assert_that(
        Original("Лимит 5 000 000. " + "слово " * 40 + "Премия в рублях").priced(
            Decimal("5000000"), "RUB"
        ),
        equal_to(False),
        "Sum with the currency far away is not refused",
    )


def test_refuses_a_currency_read_out_of_a_common_word() -> None:
    assert_that(
        Original("Лимит 5 000 000, перевозки за рубеж и по Европе").priced(
            Decimal("5000000"), "RUB"
        ),
        equal_to(False),
        "Currency read out of a common word is not refused",
    )


def test_refuses_a_sum_in_an_unknown_currency() -> None:
    assert_that(
        Original("Лимит 5 000 000 рублей").priced(Decimal("5000000"), "XXX"),
        equal_to(False),
        "Sum in an unknown currency is not refused",
    )


def test_refuses_a_sum_without_a_currency() -> None:
    assert_that(
        Original("Лимит 5 000 000").priced(Decimal("5000000"), ""),
        equal_to(False),
        "Sum without a currency is not refused",
    )


def test_names_a_clause_replaced_by_an_amendment() -> None:
    point = random.randint(1, 20)
    assert_that(
        Original(f"Пункт {point} (Транспорт) Полиса принять в следующей редакции:").names(
            str(point)
        ),
        equal_to(True),
        "Clause replaced by an amendment is not named",
    )


def test_names_a_subclause_with_a_trailing_point() -> None:
    assert_that(
        Original("Подпункт 12.5. Полиса принять в следующей редакции").names("12.5"),
        equal_to(True),
        "Subclause with a trailing point is not named",
    )


def test_names_a_subclause_being_added() -> None:
    assert_that(
        Original("Добавить подпункт 12.7 следующего содержания").names("12.7"),
        equal_to(True),
        "Subclause being added is not named",
    )


def test_names_a_clause_abbreviated_without_a_space() -> None:
    assert_that(
        Original("Исключить п.3.4.28. из Полиса").names("3.4.28"),
        equal_to(True),
        "Clause abbreviated without a space is not named",
    )


def test_names_a_clause_in_a_table_cell() -> None:
    assert_that(
        Original("п. 5 | Новая редакция").names("5"),
        equal_to(True),
        "Clause in a table cell is not named",
    )


def test_names_every_clause_of_a_list() -> None:
    assert_that(
        Original("Пункты 8, 9 и 12 принять в следующей редакции").names("12"),
        equal_to(True),
        "Clause inside a list of clauses is not named",
    )


def test_refuses_a_point_that_only_begins_a_named_subclause() -> None:
    assert_that(
        Original("Подпункт 12.5. принять").names("12"),
        equal_to(False),
        "Point that only begins a named subclause is not refused",
    )


def test_refuses_a_point_that_only_ends_a_named_number() -> None:
    assert_that(
        Original("Пункт 12 принять").names("2"),
        equal_to(False),
        "Point that only ends a named number is not refused",
    )


def test_refuses_a_number_that_names_no_clause() -> None:
    assert_that(
        Original("Перевезено 8 вагонов").names("8"),
        equal_to(False),
        "Number that names no clause is not refused",
    )


def test_refuses_an_abbreviation_read_out_of_a_word() -> None:
    assert_that(
        Original("Склеп. 8 метров").names("8"),
        equal_to(False),
        "Abbreviation read out of a word is not refused",
    )


def test_refuses_an_empty_point() -> None:
    assert_that(
        Original("Пункт 8 принять").names(""),
        equal_to(False),
        "Empty point is not refused",
    )


def test_quotes_a_phrase_with_other_spaces_and_quotes() -> None:
    assert_that(
        Original("Страхователь: ООО «Ромашка  Плюс»").quotes('ооо "Ромашка Плюс"'),
        equal_to(True),
        "Phrase with other spaces and quotes is not quoted",
    )


def test_quotes_a_number_with_a_space_after_its_sign() -> None:
    number = uuid.uuid4().hex
    assert_that(
        Original(f"Полис №{number} от").quotes(f"№ {number}"),
        equal_to(True),
        "Number with a space after its sign is not quoted",
    )


def test_refuses_a_phrase_the_text_does_not_hold() -> None:
    assert_that(
        Original("Полис № 15").quotes(uuid.uuid4().hex),
        equal_to(False),
        "Phrase that the text does not hold is not refused",
    )


def test_refuses_a_number_inside_a_longer_number() -> None:
    assert_that(
        Original("Полис № 17").quotes("7"),
        equal_to(False),
        "Number inside a longer number is not refused",
    )


def test_refuses_a_number_that_is_a_part_of_a_compound_number() -> None:
    assert_that(
        Original("Полис № 12/АБ-7").quotes("12"),
        equal_to(False),
        "Number that is a part of a compound number is not refused",
    )


def test_refuses_an_empty_phrase() -> None:
    assert_that(
        Original(uuid.uuid4().hex).quotes(""),
        equal_to(False),
        "Empty phrase is not refused",
    )
