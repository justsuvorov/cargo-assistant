import uuid

from hamcrest import assert_that, contains_string, empty, equal_to

from app.domain.clause import Absent


def test_absent_clause_names_missing_key_in_reference() -> None:
    key = uuid.uuid4().hex
    assert_that(
        Absent(key).reference(), contains_string(key), "Absent clause does not name its key"
    )


def test_absent_clause_has_no_text() -> None:
    assert_that(
        Absent(uuid.uuid4().hex).text(), equal_to(""), "Absent clause does not stay without text"
    )


def test_absent_clause_has_no_entries() -> None:
    assert_that(
        Absent(uuid.uuid4().hex).entries(), empty(), "Absent clause does not stay without entries"
    )


def test_absent_clause_has_no_dates() -> None:
    assert_that(
        Absent(uuid.uuid4().hex).dates(), empty(), "Absent clause does not stay without dates"
    )


def test_absent_clause_has_no_amounts() -> None:
    assert_that(
        Absent(uuid.uuid4().hex).amounts(), empty(), "Absent clause does not stay without amounts"
    )
