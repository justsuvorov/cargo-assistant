import random
from datetime import datetime, timedelta

from hamcrest import assert_that, equal_to, raises

from app.auth.errors import DeniedError
from app.auth.identity import Person
from app.auth.seal import Sealed, Signed


class Moment:
    """Test double named moment."""

    def __init__(self) -> None:
        self.at = datetime(2030, 1, 1, 12, 0, 0)

    def now(self) -> datetime:
        return self.at


def secret() -> str:
    return f"s{random.randint(10**6, 10**9)}"


def test_gives_back_record_it_has_sealed() -> None:
    word = secret()
    record = Signed(word, Moment()).open(Signed(word, Moment()).seal({"sub": "u1"}, 60))
    assert_that(record["sub"], equal_to("u1"), "Sealed record does not come back unchanged")


def test_refuses_record_sealed_with_another_secret() -> None:
    text = Signed(secret(), Moment()).seal({"sub": "u1"}, 60)
    assert_that(
        lambda: Signed(secret(), Moment()).open(text),
        raises(DeniedError),
        "Record with a foreign signature is not refused",
    )


def test_refuses_record_with_changed_body() -> None:
    word = secret()
    text = Signed(word, Moment()).seal({"sub": "u1"}, 60)
    other = Signed(word, Moment()).seal({"sub": "u2"}, 60)
    assert_that(
        lambda: Signed(word, Moment()).open(other.split(".")[0] + "." + text.split(".")[1]),
        raises(DeniedError),
        "Record with a swapped body is not refused",
    )


def test_refuses_record_after_its_time_is_over() -> None:
    word, moment = secret(), Moment()
    text = Signed(word, moment).seal({"sub": "u1"}, 60)
    moment.at += timedelta(seconds=61)
    assert_that(
        lambda: Signed(word, moment).open(text),
        raises(DeniedError, "Срок cookie истёк"),
        "Expired record is not refused",
    )


def test_refuses_empty_secret() -> None:
    assert_that(
        lambda: Signed("", Moment()),
        raises(ValueError, "SESSION_SECRET"),
        "Empty secret is accepted",
    )


def test_builds_person_from_session_card() -> None:
    signer = Signed(secret(), Moment())
    who = Sealed(signer).identity(
        signer.seal(Person("u7", "ivanov", frozenset({"user"}), frozenset({"fsc"})).card(), 60)
    )
    assert_that(
        (who.id(), who.name(), who.allows("user"), who.sees("fsc")),
        equal_to(("u7", "ivanov", True, True)),
        "Session does not give id, name, roles and groups back",
    )


def test_refuses_session_without_sub() -> None:
    signer = Signed(secret(), Moment())
    assert_that(
        lambda: Sealed(signer).identity(signer.seal({"name": "x"}, 60)),
        raises(DeniedError, "sub"),
        "Session without sub is accepted",
    )
