from datetime import date

from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.place import Spot
from app.domain.policy import Vacant
from app.rules.answers import Replies
from app.rules.exact import Exact
from app.rules.wording import Comments
from tests.rules.fakes import Paper, Text


def _code(exact: Exact, declared: str, clause: Text) -> str:
    return (
        exact.outcome(
            Fields().field("policy", (declared,)),
            clause,
            Paper("1", "vertical", ({"policy": (declared,)},)).shipments()[0],
            Vacant("1"),
        )
        .verdict(
            Spot("1", "policy"),
            Comments({"match": "", "mismatch": "", "review": ""}),
            Replies((), ()),
        )
        .reason()
        .code()
    )


def test_number_and_date_of_the_policy_match() -> None:
    assert_that(
        _code(
            Exact(("number", "date"), ("№",)),
            "№ 0000T00GR0000 от 26.08.2026 г.",
            Text("Преамбула", "0000T00GR0000", dates=(date(2026, 8, 26),)),
        ),
        equal_to("policy.same"),
        "Exact does not match the same number and date",
    )


def test_spaces_inside_the_number_do_not_matter() -> None:
    assert_that(
        _code(
            Exact(("number",), ("№",)),
            "№0000 T00 GR0000 от 26.08.2026",
            Text("Преамбула", "0000T00GR0000"),
        ),
        equal_to("policy.same"),
        "Exact does not ignore spaces and the number sign",
    )


def test_longer_number_is_different() -> None:
    assert_that(
        _code(
            Exact(("number",), ("№",)),
            "№ 10000T00GR0000 от 26.08.2026",
            Text("Преамбула", "0000T00GR0000"),
        ),
        equal_to("policy.different"),
        "Exact does not reject a number that only contains the policy number",
    )


def test_start_of_the_term_is_not_the_policy_date() -> None:
    assert_that(
        _code(
            Exact(("number", "date"), ("№",)),
            "№ 0000T00GR0000 от 01.01.2026",
            Text("Преамбула", "0000T00GR0000", dates=(date(2025, 12, 22),)),
        ),
        equal_to("policy.different"),
        "Exact does not reject another date of the policy",
    )


def test_unreadable_date_needs_a_person() -> None:
    assert_that(
        _code(
            Exact(("number", "date"), ("№",)),
            "№ 0000T00GR0000",
            Text("Преамбула", "0000T00GR0000", dates=(date(2025, 12, 22),)),
        ),
        equal_to("policy.unreadable"),
        "Exact does not ask for review when the date is not read",
    )


def test_whole_value_is_compared_without_parts() -> None:
    assert_that(
        _code(Exact((), ()), "AB 12", Text("п. 1", "AB12")),
        equal_to("policy.same"),
        "Exact does not compare the whole value without spaces",
    )
