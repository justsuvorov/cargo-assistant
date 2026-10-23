from hamcrest import assert_that, empty, has_length

from tools.lint.remarks import Remarks
from tools.lint.scope import Scoped
from tools.lint.script import Code


def test_scoped_rule_checks_included_script() -> None:
    assert_that(
        Scoped(Remarks(r"# @todo .+"), ("app/*",), ()).violations(Code("app/a.py", "x = 1  # x\n")),
        has_length(1),
        "Scoped rule does not check an included script",
    )


def test_scoped_rule_skips_excluded_script() -> None:
    assert_that(
        Scoped(Remarks(r"# @todo .+"), ("app/*",), ("app/web/*",)).violations(
            Code("app/web/a.py", "x = 1  # x\n")
        ),
        empty(),
        "Scoped rule does not skip an excluded script",
    )


def test_scoped_rule_skips_script_outside_inclusion() -> None:
    assert_that(
        Scoped(Remarks(r"# @todo .+"), ("app/*",), ()).violations(
            Code("docs/a.py", "x = 1  # x\n")
        ),
        empty(),
        "Scoped rule does not skip a script outside its inclusion",
    )
