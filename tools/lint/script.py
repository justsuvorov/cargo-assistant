import ast
import fnmatch
import io
import tokenize
from typing import Final, Protocol, final


class Script(Protocol):
    """Python source file that project conventions are checked against."""

    def path(self) -> str: ...

    def tree(self) -> ast.Module: ...

    def lines(self) -> tuple[str, ...]: ...

    def comments(self) -> tuple[tuple[int, str], ...]: ...

    def matches(self, pattern: str) -> bool: ...

    def mark(self, line: int, message: str) -> str: ...


@final
class Code:
    """Source text together with its path relative to the repository root."""

    __slots__ = ("_path", "_text")

    def __init__(self, path: str, text: str) -> None:
        self._path: Final = path
        self._text: Final = text

    def path(self) -> str:
        return self._path

    def tree(self) -> ast.Module:
        return ast.parse(self._text, self._path)

    def lines(self) -> tuple[str, ...]:
        return tuple(self._text.splitlines())

    def comments(self) -> tuple[tuple[int, str], ...]:
        return tuple(
            (token.start[0], token.string)
            for token in tokenize.generate_tokens(io.StringIO(self._text).readline)
            if token.type == tokenize.COMMENT
        )

    def matches(self, pattern: str) -> bool:
        return fnmatch.fnmatch(self._path, pattern)

    def mark(self, line: int, message: str) -> str:
        return f"{self._path}:{line}: {message}"
