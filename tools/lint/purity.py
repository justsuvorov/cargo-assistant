import ast
from typing import Final, final

from tools.lint.script import Script


@final
class Purity:
    """Rule that domain code neither inspects types nor passes None around."""

    __slots__ = ("_banned",)

    def __init__(self, banned: frozenset[str]) -> None:
        self._banned: Final = banned

    def violations(self, script: Script) -> tuple[str, ...]:
        tree = script.tree()
        commands = {
            id(node.returns)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        return tuple(
            script.mark(node.lineno, f"Интроспекция через {node.func.id}")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in self._banned
        ) + tuple(
            script.mark(node.lineno, "None допустим только как результат команды")
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value is None and id(node) not in commands
        )
