from hamcrest import assert_that, empty, has_length

from tools.lint.naming import Names
from tools.lint.script import Code


def test_names_reject_agent_noun() -> None:
    assert_that(
        Names(r"(?:Check|Load)er$").violations(Code("app/a.py", "class CardLoader:\n    pass\n")),
        has_length(1),
        "Names do not reject an agent noun",
    )


def test_names_accept_plain_noun() -> None:
    assert_that(
        Names(r"(?:Check|Load)er$").violations(Code("app/a.py", "class Cards:\n    pass\n")),
        empty(),
        "Names do not accept a plain noun",
    )
