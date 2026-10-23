from hamcrest import assert_that, empty, has_length

from tools.lint.finality import Attributes, Finality, Statics
from tools.lint.script import Code


def test_finality_rejects_class_without_decorator() -> None:
    assert_that(
        Finality().violations(Code("app/a.py", "class A:\n    pass\n")),
        has_length(1),
        "Finality does not reject an open class",
    )


def test_finality_accepts_final_class() -> None:
    assert_that(
        Finality().violations(Code("app/a.py", "@final\nclass A:\n    pass\n")),
        empty(),
        "Finality does not accept a final class",
    )


def test_finality_accepts_protocol() -> None:
    assert_that(
        Finality().violations(Code("app/a.py", "class A(Fact, Protocol):\n    pass\n")),
        empty(),
        "Finality does not accept a protocol",
    )


def test_statics_reject_static_method() -> None:
    assert_that(
        Statics().violations(Code("app/a.py", "class A:\n    @staticmethod\n    def a(): ...\n")),
        has_length(1),
        "Statics do not reject a static method",
    )


def test_statics_reject_class_method() -> None:
    assert_that(
        Statics().violations(Code("app/a.py", "class A:\n    @classmethod\n    def a(c): ...\n")),
        has_length(1),
        "Statics do not reject a class method",
    )


def test_attributes_reject_class_without_slots() -> None:
    assert_that(
        Attributes(4).violations(Code("app/a.py", "class A:\n    pass\n")),
        has_length(1),
        "Attributes do not reject a class without slots",
    )


def test_attributes_reject_crowded_class() -> None:
    assert_that(
        Attributes(2).violations(
            Code(
                "app/a.py",
                "class A:\n"
                "    __slots__ = ('_a', '_b', '_c')\n"
                "    def __init__(self):\n"
                "        self._a = 1\n"
                "        self._b = 2\n"
                "        self._c = 3\n",
            )
        ),
        has_length(1),
        "Attributes do not reject a crowded class",
    )


def test_attributes_reject_public_attribute() -> None:
    assert_that(
        Attributes(4).violations(
            Code(
                "app/a.py",
                "class A:\n    __slots__ = ('a',)\n    def __init__(self):\n        self.a = 1\n",
            )
        ),
        has_length(1),
        "Attributes do not reject a public attribute",
    )


def test_attributes_skip_protocol() -> None:
    assert_that(
        Attributes(4).violations(Code("app/a.py", "class A(Protocol):\n    def a(self): ...\n")),
        empty(),
        "Attributes do not skip a protocol",
    )
