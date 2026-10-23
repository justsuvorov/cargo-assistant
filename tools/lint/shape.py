import ast
from typing import Final, Protocol, final

type Method = ast.FunctionDef | ast.AsyncFunctionDef


class Outline(Protocol):
    """Class declaration seen through the properties that conventions care about."""

    def name(self) -> str: ...

    def line(self) -> int: ...

    def protocol(self) -> bool: ...

    def sealed(self) -> bool: ...

    def slotted(self) -> bool: ...

    def methods(self) -> tuple[Method, ...]: ...

    def attributes(self) -> frozenset[str]: ...


@final
class Shape:
    """Outline of one class declaration in a syntax tree."""

    __slots__ = ("_node",)

    def __init__(self, node: ast.ClassDef) -> None:
        self._node: Final = node

    def name(self) -> str:
        return self._node.name

    def line(self) -> int:
        return self._node.lineno

    def protocol(self) -> bool:
        return "Protocol" in {ast.unparse(base).rsplit(".", 1)[-1] for base in self._node.bases}

    def sealed(self) -> bool:
        return "final" in {
            ast.unparse(item).rsplit(".", 1)[-1] for item in self._node.decorator_list
        }

    def slotted(self) -> bool:
        return any(
            ast.unparse(target) == "__slots__"
            for node in self._node.body
            for target in self._targets(node)
        )

    def methods(self) -> tuple[Method, ...]:
        return tuple(
            node
            for node in self._node.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )

    def attributes(self) -> frozenset[str]:
        return frozenset(
            target.attr
            for node in ast.walk(self._node)
            for target in self._targets(node)
            if isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        )

    def _targets(self, node: ast.AST) -> tuple[ast.expr, ...]:
        if isinstance(node, ast.Assign):
            return tuple(node.targets)
        if isinstance(node, ast.AnnAssign | ast.AugAssign):
            return (node.target,)
        return ()
