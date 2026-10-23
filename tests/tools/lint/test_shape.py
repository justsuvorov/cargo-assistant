import ast

from hamcrest import assert_that, equal_to, has_length

from tools.lint.shape import Shape


def test_shape_recognises_protocol() -> None:
    assert_that(
        Shape(
            next(
                node
                for node in ast.walk(ast.parse("class A(typing.Protocol):\n    pass\n"))
                if isinstance(node, ast.ClassDef)
            )
        ).protocol(),
        equal_to(True),
        "Shape does not recognise a protocol",
    )


def test_shape_recognises_final_decorator() -> None:
    assert_that(
        Shape(
            next(
                node
                for node in ast.walk(ast.parse("@typing.final\nclass A:\n    pass\n"))
                if isinstance(node, ast.ClassDef)
            )
        ).sealed(),
        equal_to(True),
        "Shape does not recognise the final decorator",
    )


def test_shape_recognises_slots() -> None:
    assert_that(
        Shape(
            next(
                node
                for node in ast.walk(ast.parse("class A:\n    __slots__ = ()\n"))
                if isinstance(node, ast.ClassDef)
            )
        ).slotted(),
        equal_to(True),
        "Shape does not recognise slots",
    )


def test_shape_collects_attributes_assigned_to_self() -> None:
    assert_that(
        Shape(
            next(
                node
                for node in ast.walk(
                    ast.parse(
                        "class A:\n"
                        "    def __init__(self, a, b):\n"
                        "        self._a = a\n"
                        "        self._b: int = b\n"
                        "        other.c = 1\n"
                    )
                )
                if isinstance(node, ast.ClassDef)
            )
        ).attributes(),
        equal_to(frozenset({"_a", "_b"})),
        "Shape does not collect only attributes of self",
    )


def test_shape_lists_methods() -> None:
    assert_that(
        Shape(
            next(
                node
                for node in ast.walk(
                    ast.parse(
                        "class A:\n    x = 1\n    def a(self): ...\n    async def b(self): ...\n"
                    )
                )
                if isinstance(node, ast.ClassDef)
            )
        ).methods(),
        has_length(2),
        "Shape does not list sync and async methods",
    )


def test_shape_knows_its_name() -> None:
    assert_that(
        Shape(
            next(
                node
                for node in ast.walk(ast.parse("class Alpha:\n    pass\n"))
                if isinstance(node, ast.ClassDef)
            )
        ).name(),
        equal_to("Alpha"),
        "Shape does not know its name",
    )


def test_shape_knows_its_line() -> None:
    assert_that(
        Shape(
            next(
                node
                for node in ast.walk(ast.parse("x = 1\nclass A:\n    pass\n"))
                if isinstance(node, ast.ClassDef)
            )
        ).line(),
        equal_to(2),
        "Shape does not know its line",
    )
