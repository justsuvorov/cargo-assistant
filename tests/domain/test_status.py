from hamcrest import assert_that, equal_to, is_not

from app.domain.status import Match, Mismatch, Review


def test_match_reads_as_russian_word() -> None:
    assert_that(Match().text(), equal_to("совпадает"), "Match does not read as совпадает")


def test_mismatch_reads_as_russian_words() -> None:
    assert_that(Mismatch().text(), equal_to("не совпадает"), "Mismatch does not read right")


def test_review_reads_as_russian_words() -> None:
    assert_that(Review().text(), equal_to("требует проверки"), "Review does not read right")


def test_match_and_mismatch_have_different_keys() -> None:
    assert_that(Match().key(), is_not(equal_to(Mismatch().key())), "Statuses do not differ by key")


def test_review_and_match_have_different_keys() -> None:
    assert_that(Review().key(), is_not(equal_to(Match().key())), "Statuses do not differ by key")
