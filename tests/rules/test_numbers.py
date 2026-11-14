import random
import string

from hamcrest import assert_that, equal_to

from app.rules.numbers import Numbered


def digits() -> str:
    return "".join(random.choices(string.digits, k=7))


def test_finds_number_among_words_of_declared_text() -> None:
    number = digits()
    assert_that(
        Numbered(("№",)).same(f"№ {number} от 26.08.2026", number),
        equal_to(True),
        "Number inside the declared text is not found",
    )


def test_finds_number_split_by_spaces_in_declared_text() -> None:
    number = digits()
    assert_that(
        Numbered(()).same(f"{number[:3]} {number[3:]}", number),
        equal_to(True),
        "Number that the declaration splits by a space is not found",
    )


def test_does_not_find_another_number() -> None:
    assert_that(
        Numbered(()).same(f"{digits()}1", f"{digits()}2"),
        equal_to(False),
        "Different numbers are not told apart",
    )


def test_ignores_characters_of_the_card_in_both_texts() -> None:
    number = digits()
    assert_that(
        Numbered(("№",)).same(f"№{number}", f"№ {number}"),
        equal_to(True),
        "Character of the card is not ignored",
    )


def test_does_not_find_blank_number() -> None:
    assert_that(
        Numbered(("№",)).same(digits(), " № "),
        equal_to(False),
        "Blank number is not refused",
    )


def test_tells_blank_text_from_text_with_a_number() -> None:
    blank = Numbered(("№",))
    assert_that(
        (blank.blank(" № "), blank.blank("№ 1")),
        equal_to((True, False)),
        "Text that holds only ignored characters is not blank",
    )
