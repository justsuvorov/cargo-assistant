import uuid

from hamcrest import assert_that, equal_to

from app.domain.clause import Absent
from app.domain.place import Spot
from app.domain.semantics import Inquiry


def test_inquiry_keeps_declared_value() -> None:
    value = f"Продукты, Бумага, {uuid.uuid4().hex}"
    assert_that(
        Inquiry(Spot("113/1", "cargo"), value, Absent("object"), "каждая позиция").value(),
        equal_to(value),
        "Inquiry does not keep the declared value",
    )


def test_inquiry_keeps_card_rule() -> None:
    rule = uuid.uuid4().hex
    assert_that(
        Inquiry(Spot("113/1", "cargo"), "мех", Absent("object"), rule).rule(),
        equal_to(rule),
        "Inquiry does not keep the card rule",
    )


def test_inquiry_keeps_its_place() -> None:
    assert_that(
        Inquiry(Spot("113/3", "cargo"), "почта", Absent("object"), "")
        .place()
        .same(Spot("113/3", "cargo")),
        equal_to(True),
        "Inquiry does not keep its place",
    )


def test_inquiry_keeps_its_clause() -> None:
    key = uuid.uuid4().hex
    assert_that(
        Inquiry(Spot("1", "cargo"), "мясо", Absent(key), "").clause().reference(),
        equal_to(Absent(key).reference()),
        "Inquiry does not keep its clause",
    )
