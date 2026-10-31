import random
import uuid
from datetime import date

from hamcrest import assert_that, contains_string, empty, equal_to

from app.domain.field import Blank
from app.domain.policy import Vacant


def test_vacant_policy_has_no_clause() -> None:
    key = uuid.uuid4().hex
    assert_that(
        Vacant(str(random.randint(1, 999))).clause(key, _Row()).reference(),
        contains_string(key),
        "Vacant policy does not answer with an absent clause",
    )


def test_vacant_policy_keeps_the_cited_number() -> None:
    number = f"{random.randint(1000, 9999)}T00GR{random.randint(1000, 9999)}"
    assert_that(Vacant(number).number(), equal_to(number), "Vacant policy does not keep its number")


def test_vacant_policy_has_no_special_conditions() -> None:
    assert_that(Vacant("1").conditions(), empty(), "Vacant policy does not stay without conditions")


class _Row:
    """Shipment stand-in that the vacant policy never asks about."""

    __slots__ = ()

    def number(self) -> str:
        return "1"

    def declaration(self) -> str:
        return "1"

    def field(self, key: str) -> Blank:
        return Blank(key)

    def start(self) -> date:
        return date(2026, random.randint(1, 12), random.randint(1, 28))
