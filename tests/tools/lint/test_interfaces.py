from hamcrest import assert_that, empty, equal_to, has_length

from tools.lint.interfaces import Declared, Interfaces
from tools.lint.script import Code


def test_declared_collects_protocol_methods() -> None:
    assert_that(
        Declared([Code("a.py", "class A(Protocol):\n    def text(self) -> str: ...\n")]).names(),
        equal_to(frozenset({"text"})),
        "Declared does not collect protocol methods",
    )


def test_declared_ignores_final_class_methods() -> None:
    assert_that(
        Declared([Code("a.py", "@final\nclass A:\n    def text(self) -> str: ...\n")]).names(),
        empty(),
        "Declared does not ignore methods of final classes",
    )


def test_interfaces_reject_undeclared_public_method() -> None:
    assert_that(
        Interfaces(Declared([])).violations(
            Code("app/a.py", "@final\nclass A:\n    def text(self) -> str: ...\n")
        ),
        has_length(1),
        "Interfaces do not reject an undeclared method",
    )


def test_interfaces_accept_declared_method() -> None:
    assert_that(
        Interfaces(
            Declared([Code("p.py", "class P(Protocol):\n    def text(self): ...\n")])
        ).violations(Code("app/a.py", "@final\nclass A:\n    def text(self) -> str: ...\n")),
        empty(),
        "Interfaces do not accept a declared method",
    )


def test_interfaces_skip_private_method() -> None:
    assert_that(
        Interfaces(Declared([])).violations(
            Code("app/a.py", "@final\nclass A:\n    def _text(self) -> str: ...\n")
        ),
        empty(),
        "Interfaces do not skip a private method",
    )
