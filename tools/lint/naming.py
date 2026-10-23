import ast
import re
from typing import Final, final

from tools.lint.script import Script


@final
class Names:
    """Rule that rejects class names built as agent nouns, such as Parser or Manager."""

    __slots__ = ("_agent",)

    def __init__(self, agent: str) -> None:
        self._agent: Final = agent

    def violations(self, script: Script) -> tuple[str, ...]:
        return tuple(
            script.mark(node.lineno, f"Класс {node.name} назван по действию, а не по сущности")
            for node in ast.walk(script.tree())
            if isinstance(node, ast.ClassDef) and re.search(self._agent, node.name)
        )
