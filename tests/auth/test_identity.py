import random

from hamcrest import assert_that, equal_to, raises

from app.auth.errors import DeniedError
from app.auth.identity import Person


def test_sees_only_own_groups() -> None:
    group = f"g{random.randint(1, 999)}"
    assert_that(
        Person("i", "a", frozenset(), frozenset({group})).sees(f"{group}x"),
        equal_to(False),
        "Person sees a group they do not belong to",
    )


def test_sees_every_group_with_star() -> None:
    assert_that(
        Person("i", "a", frozenset(), frozenset({"*"})).sees(f"g{random.randint(1, 999)}"),
        equal_to(True),
        "Star group does not see every group",
    )


def test_cannot_upload_without_group() -> None:
    assert_that(
        lambda: Person("i", "a", frozenset({"user"}), frozenset()).group(),
        raises(DeniedError),
        "Person without a group is not refused",
    )
