import ast
from collections.abc import Iterable
from typing import Final, Protocol, final

from tools.lint.script import Script
from tools.lint.shape import Shape


class Vocabulary(Protocol):
    """Method names that interfaces of a code base declare."""

    def names(self) -> frozenset[str]: ...


@final
class Declared:
    """Vocabulary collected from every protocol class in a set of scripts."""

    __slots__ = ("_scripts",)

    def __init__(self, scripts: Iterable[Script]) -> None:
        self._scripts: Final = tuple(scripts)

    def names(self) -> frozenset[str]:
        return frozenset(
            method.name
            for script in self._scripts
            for node in ast.walk(script.tree())
            if isinstance(node, ast.ClassDef) and Shape(node).protocol()
            for method in Shape(node).methods()
        )


@final
class Interfaces:
    """Rule that every public method of a final class is first declared in some interface."""

    __slots__ = ("_vocabulary",)

    def __init__(self, vocabulary: Vocabulary) -> None:
        self._vocabulary: Final = vocabulary

    def violations(self, script: Script) -> tuple[str, ...]:
        names = self._vocabulary.names()
        return tuple(
            script.mark(method.lineno, f"Метод {method.name} не объявлен ни в одном интерфейсе")
            for node in ast.walk(script.tree())
            if isinstance(node, ast.ClassDef) and Shape(node).sealed()
            for method in Shape(node).methods()
            if not method.name.startswith("_") and method.name not in names
        )
