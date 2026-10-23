import ast
from typing import final

from tools.lint.script import Script


@final
class Density:
    """Rule that function bodies contain no blank lines."""

    __slots__ = ()

    def violations(self, script: Script) -> tuple[str, ...]:
        lines = script.lines()
        return tuple(
            script.mark(number, "Пустая строка внутри тела функции")
            for number in sorted(
                {
                    number
                    for node in ast.walk(script.tree())
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                    for number in range(node.body[0].lineno, (node.end_lineno or 0) + 1)
                    if not lines[number - 1].strip()
                }
            )
        )
