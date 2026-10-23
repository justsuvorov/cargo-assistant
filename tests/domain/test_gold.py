import uuid

from hamcrest import assert_that, equal_to

from app.domain.gold import Expectation
from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Match, Mismatch
from app.domain.verdict import Ruling


def test_expectation_agrees_with_same_status_in_same_place() -> None:
    field = uuid.uuid4().hex
    assert_that(
        Expectation(Spot("97", field), Mismatch()).agrees(
            Ruling(Spot("97", field), Mismatch(), Cause("x", "rule"), Note("", ""))
        ),
        equal_to(True),
        "Expectation does not accept the expected status",
    )


def test_expectation_rejects_other_status() -> None:
    field = uuid.uuid4().hex
    assert_that(
        Expectation(Spot("97", field), Mismatch()).agrees(
            Ruling(Spot("97", field), Match(), Cause("x", "rule"), Note("", ""))
        ),
        equal_to(False),
        "Expectation does not reject a wrong status",
    )


def test_expectation_rejects_verdict_from_other_place() -> None:
    assert_that(
        Expectation(Spot("97", "sum"), Match()).agrees(
            Ruling(Spot("97", "cargo"), Match(), Cause("x", "rule"), Note("", ""))
        ),
        equal_to(False),
        "Expectation does not reject a verdict for another field",
    )


def test_expectation_keeps_its_place() -> None:
    field = uuid.uuid4().hex
    assert_that(
        Expectation(Spot("35", field), Match()).place().same(Spot("35", field)),
        equal_to(True),
        "Expectation does not keep its place",
    )
