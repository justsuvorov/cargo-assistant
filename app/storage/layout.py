from typing import Protocol, final

from app.storage.errors import EscapeError
from app.storage.relative import Relative


class Layout(Protocol):
    """Rules that turn owners, sessions and file names into storage keys; every key of a user
    starts with the owner, so a key never reaches the files of another one."""

    def folder(self, owner: str, session: int) -> str: ...

    def entry(self, owner: str, session: int, path: str) -> str: ...

    def special(self, owner: str, session: int) -> str: ...

    def chosen(self, owner: str, session: int, name: str) -> str: ...

    def result(self, owner: str, session: int, declaration_id: int, number: str) -> str: ...

    def knowledge(self, ruleset_id: int, name: str) -> str: ...


@final
class Keys:
    """Layout of the storage tree, where an owner and a file name never contain a path."""

    __slots__ = ()

    def folder(self, owner: str, session: int) -> str:
        return f"{self._name(owner)}/{session}/folder"

    def entry(self, owner: str, session: int, path: str) -> str:
        return f"{self.folder(owner, session)}/{Relative(path).path()}"

    def special(self, owner: str, session: int) -> str:
        return f"{self._name(owner)}/{session}/conditions"

    def chosen(self, owner: str, session: int, name: str) -> str:
        return f"{self.special(owner, session)}/{self._name(name)}"

    def result(self, owner: str, session: int, declaration_id: int, number: str) -> str:
        return (
            f"{self._name(owner)}/{session}/results/{declaration_id}/"
            f"{self._name(number.replace('/', '_'))} – результат проверки.xlsx"
        )

    def knowledge(self, ruleset_id: int, name: str) -> str:
        return f"knowledge/{ruleset_id}/source/{self._name(name)}"

    def _name(self, name: str) -> str:
        if not name or name in {".", ".."} or "/" in name or "\\" in name or "\0" in name:
            raise EscapeError(f"Имя файла {name!r} содержит путь")
        return name
