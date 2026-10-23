import ast
import re
from typing import Final, final

from tools.lint.script import Script


@final
class Angry:
    """Rule that every test ends with its only assertion, which explains a failure negatively."""

    __slots__ = ("_negative", "_params")

    def __init__(self, negative: str, params: frozenset[str]) -> None:
        self._negative: Final = negative
        self._params: Final = params

    def violations(self, script: Script) -> tuple[str, ...]:
        return tuple(
            script.mark(test.lineno, f"Тест {test.name} {problem}")
            for test in script.tree().body
            if isinstance(test, ast.FunctionDef) and test.name.startswith("test_")
            for problem in self._problems(test)
        )

    def _problems(self, test: ast.FunctionDef) -> tuple[str, ...]:
        messages = self._messages(test)
        return tuple(
            problem
            for problem, broken in (
                ("использует assert вместо assert_that", self._asserts(test)),
                ("должен содержать ровно один assert_that", len(self._calls(test)) != 1),
                ("должен заканчиваться вызовом assert_that", not self._closed(test)),
                ("принимает недопустимые аргументы", self._arguments(test)),
                ("не сообщает о провале отрицанием", not self._negated(messages)),
                ("пишет сокращение с апострофом", any("'" in text for text in messages)),
            )
            if broken
        )

    def _calls(self, test: ast.FunctionDef) -> tuple[ast.Call, ...]:
        return tuple(
            node
            for node in ast.walk(test)
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "assert_that"
        )

    def _messages(self, test: ast.FunctionDef) -> tuple[str, ...]:
        return tuple(
            message.value
            for call in self._calls(test)
            for message in call.args[2:3]
            if isinstance(message, ast.Constant) and isinstance(message.value, str)
        )

    def _asserts(self, test: ast.FunctionDef) -> bool:
        return any(isinstance(node, ast.Assert) for node in ast.walk(test))

    def _closed(self, test: ast.FunctionDef) -> bool:
        last = test.body[-1]
        return (
            isinstance(last, ast.Expr)
            and isinstance(last.value, ast.Call)
            and ast.unparse(last.value.func) == "assert_that"
        )

    def _arguments(self, test: ast.FunctionDef) -> bool:
        return bool({argument.arg for argument in test.args.args} - self._params)

    def _negated(self, messages: tuple[str, ...]) -> bool:
        return bool(messages) and all(
            re.search(self._negative, text, re.IGNORECASE) for text in messages
        )
