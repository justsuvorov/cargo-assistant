import uuid

from hamcrest import assert_that, empty, equal_to

from app.domain.field import Blank


def test_blank_field_is_not_filled() -> None:
    assert_that(
        Blank(uuid.uuid4().hex).filled(), equal_to(False), "Blank field does not admit it is empty"
    )


def test_blank_field_keeps_its_key() -> None:
    key = uuid.uuid4().hex
    assert_that(Blank(key).key(), equal_to(key), "Blank field does not keep its key")


def test_blank_field_has_no_text() -> None:
    assert_that(
        Blank(uuid.uuid4().hex).text(), equal_to(""), "Blank field does not stay without text"
    )


def test_blank_field_has_no_dates() -> None:
    assert_that(Blank(uuid.uuid4().hex).dates(), empty(), "Blank field does not stay without dates")


def test_blank_field_has_no_amounts() -> None:
    assert_that(
        Blank(uuid.uuid4().hex).amounts(), empty(), "Blank field does not stay without amounts"
    )


def test_blank_field_has_no_entries() -> None:
    assert_that(
        Blank(uuid.uuid4().hex).entries(), empty(), "Blank field does not stay without entries"
    )
