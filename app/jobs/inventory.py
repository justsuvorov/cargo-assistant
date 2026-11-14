import hashlib
from pathlib import Path
from typing import Final, Protocol, final

from app.declarations.declared import Declared
from app.domain.errors import UnreadableError
from app.ingest.source import Source
from app.policy.layout import Layout
from app.storage.relative import Relative

_SHEETS = frozenset({".xls", ".xlsx", ".xlsm"})
_SUFFIXES = _SHEETS | {".doc", ".docx"}


class Inspected(Protocol):
    """Folder that a user opened: the declarations in it and the signature of the policy files."""

    def declarations(self) -> tuple[str, ...]: ...

    def signature(self) -> str: ...


@final
class Inventory:
    """Folder of a policy on a disk. The policy files lie in the folder itself, in the folder of
    addenda, of special conditions and of carriers, as the layout of a policy folder says; every
    other document of a subfolder, at any depth, is a declaration. Documents lying in the folder
    itself are policy files, never declarations. A spreadsheet in a folder of the policy that reads
    as a declaration, like an appendix to an addendum, is a declaration, told by its content."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root: Final = root

    def declarations(self) -> tuple[str, ...]:
        policy = {path for _, path in self._policy()}
        return tuple(
            sorted(
                found
                for path in self._root.rglob("*")
                for found in (path.relative_to(self._root).as_posix(),)
                if path.is_file()
                and path not in policy
                and path.parent != self._root
                and path.suffix.lower() in _SUFFIXES
                and not Relative(found).service()
            )
        )

    def signature(self) -> str:
        return hashlib.sha256(
            "\n".join(
                sorted(
                    f"{role}:{path.relative_to(self._root).as_posix()}:"
                    f"{hashlib.sha256(path.read_bytes()).hexdigest()}"
                    for role, path in self._policy()
                )
            ).encode()
        ).hexdigest()

    def _policy(self) -> tuple[tuple[str, Path], ...]:
        layout = Layout(self._root)
        return tuple(
            (role, path)
            for role, paths in (
                ("policy", layout.policies()),
                ("addendum", layout.amendments()),
                ("conditions", layout.conditions()),
                ("carriers", layout.carriers()),
            )
            for path in paths
            if not self._declaration(path)
        )

    def _declaration(self, path: Path) -> bool:
        if path.parent == self._root or path.suffix.lower() not in _SHEETS:
            return False
        try:
            Declared(Source(path)).shipments()
        except UnreadableError:
            return False
        return True
