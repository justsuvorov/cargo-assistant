from hamcrest import assert_that, empty, has_length

from tools.lint.density import Density
from tools.lint.script import Code


def test_density_rejects_blank_line_in_body() -> None:
    assert_that(
        Density().violations(Code("a.py", "def a():\n    x = 1\n\n    return x\n")),
        has_length(1),
        "Density does not reject a blank line in a body",
    )


def test_density_accepts_blank_lines_between_methods() -> None:
    assert_that(
        Density().violations(
            Code("a.py", "class A:\n    def a(self): ...\n\n    def b(self):\n        return 1\n")
        ),
        empty(),
        "Density does not accept blank lines between methods",
    )


def test_density_reports_nested_blank_line_once() -> None:
    assert_that(
        Density().violations(
            Code(
                "a.py", "def a():\n    def b():\n        x = 1\n\n        return x\n    return b\n"
            )
        ),
        has_length(1),
        "Density does not report a nested blank line once",
    )
