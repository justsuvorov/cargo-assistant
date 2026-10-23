from hamcrest import assert_that, empty, has_length

from tools.lint.angry import Angry
from tools.lint.script import Code


def test_angry_accepts_single_negative_assertion() -> None:
    assert_that(
        Angry(r"\bnot\b", frozenset({"tmp_path"})).violations(
            Code("tests/test_a.py", "def test_a(tmp_path):\n    assert_that(1, x, 'A is not B')\n")
        ),
        empty(),
        "Angry rule does not accept a proper test",
    )


def test_angry_rejects_plain_assert() -> None:
    assert_that(
        Angry(r"\bnot\b", frozenset()).violations(
            Code("tests/test_a.py", "def test_a():\n    assert 1\n    assert_that(1, x, 'not 1')\n")
        ),
        has_length(1),
        "Angry rule does not reject a plain assert",
    )


def test_angry_rejects_two_assertions() -> None:
    assert_that(
        Angry(r"\bnot\b", frozenset()).violations(
            Code(
                "tests/test_a.py",
                "def test_a():\n    assert_that(1, x, 'not 1')\n    assert_that(2, y, 'not 2')\n",
            )
        ),
        has_length(1),
        "Angry rule does not reject two assertions",
    )


def test_angry_rejects_assertion_before_last_statement() -> None:
    assert_that(
        Angry(r"\bnot\b", frozenset()).violations(
            Code("tests/test_a.py", "def test_a():\n    assert_that(1, x, 'not 1')\n    y = 2\n")
        ),
        has_length(1),
        "Angry rule does not reject an assertion before the last statement",
    )


def test_angry_rejects_shared_fixture() -> None:
    assert_that(
        Angry(r"\bnot\b", frozenset({"tmp_path"})).violations(
            Code("tests/test_a.py", "def test_a(client):\n    assert_that(1, x, 'not 1')\n")
        ),
        has_length(1),
        "Angry rule does not reject a shared fixture",
    )


def test_angry_rejects_positive_message() -> None:
    assert_that(
        Angry(r"\bnot\b", frozenset()).violations(
            Code("tests/test_a.py", "def test_a():\n    assert_that(1, x, 'A equals B')\n")
        ),
        has_length(1),
        "Angry rule does not reject a positive message",
    )


def test_angry_rejects_missing_message() -> None:
    assert_that(
        Angry(r"\bnot\b", frozenset()).violations(
            Code("tests/test_a.py", "def test_a():\n    assert_that(1, x)\n")
        ),
        has_length(1),
        "Angry rule does not reject a missing message",
    )


def test_angry_rejects_apostrophe() -> None:
    assert_that(
        Angry(r"\bnot\b|n't", frozenset()).violations(
            Code("tests/test_a.py", 'def test_a():\n    assert_that(1, x, "A isn\'t B")\n')
        ),
        has_length(1),
        "Angry rule does not reject an apostrophe",
    )
