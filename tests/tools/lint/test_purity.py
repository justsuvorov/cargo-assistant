from hamcrest import assert_that, empty, has_length

from tools.lint.purity import Purity
from tools.lint.script import Code


def test_purity_rejects_isinstance() -> None:
    assert_that(
        Purity(frozenset({"isinstance"})).violations(Code("app/a.py", "isinstance(a, int)\n")),
        has_length(1),
        "Purity does not reject isinstance",
    )


def test_purity_rejects_optional_argument() -> None:
    assert_that(
        Purity(frozenset()).violations(Code("app/a.py", "def a(b: int | None) -> int: ...\n")),
        has_length(1),
        "Purity does not reject an optional argument",
    )


def test_purity_rejects_none_default() -> None:
    assert_that(
        Purity(frozenset()).violations(Code("app/a.py", "def a(b: int = None) -> int: ...\n")),
        has_length(1),
        "Purity does not reject a None default",
    )


def test_purity_rejects_returned_none() -> None:
    assert_that(
        Purity(frozenset()).violations(Code("app/a.py", "def a() -> int:\n    return None\n")),
        has_length(1),
        "Purity does not reject a returned None",
    )


def test_purity_accepts_command_returning_nothing() -> None:
    assert_that(
        Purity(frozenset()).violations(Code("app/a.py", "def a(b: int) -> None: ...\n")),
        empty(),
        "Purity does not accept a command",
    )
