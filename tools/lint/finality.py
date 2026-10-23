import ast
from typing import Final, final

from tools.lint.script import Script
from tools.lint.shape import Shape


@final
class Finality:
    """Rule that every class except an interface carries the final decorator."""

    __slots__ = ()

    def violations(self, script: Script) -> tuple[str, ...]:
        return tuple(
            script.mark(shape.line(), f"Класс {shape.name()} не помечен @final")
            for shape in map(Shape, self._classes(script))
            if not shape.protocol() and not shape.sealed()
        )

    def _classes(self, script: Script) -> tuple[ast.ClassDef, ...]:
        return tuple(node for node in ast.walk(script.tree()) if isinstance(node, ast.ClassDef))


@final
class Statics:
    """Rule that forbids static and class methods."""

    __slots__ = ()

    def violations(self, script: Script) -> tuple[str, ...]:
        return tuple(
            script.mark(node.lineno, f"Метод {node.name} объявлен через {ast.unparse(item)}")
            for node in ast.walk(script.tree())
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            for item in node.decorator_list
            if ast.unparse(item) in {"staticmethod", "classmethod"}
        )


@final
class Attributes:
    """Rule that a class freezes its state in slots and holds a few private attributes."""

    __slots__ = ("_limit",)

    def __init__(self, limit: int) -> None:
        self._limit: Final = limit

    def violations(self, script: Script) -> tuple[str, ...]:
        shapes = tuple(
            Shape(node)
            for node in ast.walk(script.tree())
            if isinstance(node, ast.ClassDef) and not Shape(node).protocol()
        )
        return (
            tuple(
                script.mark(shape.line(), f"Класс {shape.name()} не объявляет __slots__")
                for shape in shapes
                if not shape.slotted()
            )
            + tuple(
                script.mark(
                    shape.line(), f"Класс {shape.name()} хранит больше {self._limit} атрибутов"
                )
                for shape in shapes
                if len(shape.attributes()) > self._limit
            )
            + tuple(
                script.mark(shape.line(), f"Класс {shape.name()} открывает атрибут {name}")
                for shape in shapes
                for name in sorted(shape.attributes())
                if not name.startswith("_")
            )
        )
