import uuid

from hamcrest import assert_that, equal_to

from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Review
from app.domain.verdict import Ruling


def test_ruling_keeps_its_status() -> None:
    assert_that(
        Ruling(
            Spot("200/1", uuid.uuid4().hex),
            Review(),
            Cause("llm.invalid_json", "llm"),
            Note("", ""),
        )
        .status()
        .key(),
        equal_to("review"),
        "Ruling does not keep its status",
    )


def test_ruling_keeps_its_place() -> None:
    field = uuid.uuid4().hex
    assert_that(
        Ruling(Spot("7", field), Review(), Cause("x", "rule"), Note("", ""))
        .place()
        .same(Spot("7", field)),
        equal_to(True),
        "Ruling does not keep its place",
    )


def test_ruling_keeps_its_reason() -> None:
    code = uuid.uuid4().hex
    assert_that(
        Ruling(Spot("7", "sum"), Review(), Cause(code, "rule"), Note("", "")).reason().code(),
        equal_to(code),
        "Ruling does not keep its reason",
    )


def test_ruling_keeps_its_remark() -> None:
    comment = uuid.uuid4().hex
    assert_that(
        Ruling(Spot("7", "sum"), Review(), Cause("x", "rule"), Note(comment, ""))
        .remark()
        .comment(),
        equal_to(comment),
        "Ruling does not keep its remark",
    )
