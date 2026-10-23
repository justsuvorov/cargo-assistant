import random

from hamcrest import assert_that, empty, has_length

from tools.lint.remarks import Remarks
from tools.lint.script import Code


def test_remarks_accept_puzzle() -> None:
    assert_that(
        Remarks(r"# @todo #\d+:\d+(min|h) \S.*").violations(
            Code("a.py", f"x = 1  # @todo #{random.randint(1, 99)}:30min Read dates in English\n")
        ),
        empty(),
        "Remarks do not accept a puzzle",
    )


def test_remarks_reject_plain_comment() -> None:
    assert_that(
        Remarks(r"# @todo #\d+:\d+(min|h) \S.*").violations(Code("a.py", "x = 1  # explain\n")),
        has_length(1),
        "Remarks do not reject a plain comment",
    )


def test_remarks_reject_puzzle_without_estimate() -> None:
    assert_that(
        Remarks(r"# @todo #\d+:\d+(min|h) \S.*").violations(Code("a.py", "# @todo #5 Fix\n")),
        has_length(1),
        "Remarks do not reject a puzzle without estimate",
    )


def test_remarks_reject_suppression() -> None:
    assert_that(
        Remarks(r"# @todo #\d+:\d+(min|h) \S.*").violations(Code("a.py", "x = 1  # noqa: E501\n")),
        has_length(1),
        "Remarks do not reject a linter suppression",
    )
