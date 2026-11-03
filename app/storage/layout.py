from typing import Protocol, final

from app.storage.errors import EscapeError
from app.storage.relative import Relative


class Layout(Protocol):
    """Rules that turn identifiers and file names into storage keys."""

    def policy(self, policy_id: int, name: str) -> str: ...

    def package(self, policy_id: int) -> str: ...

    def document(self, policy_id: int, path: str) -> str: ...

    def source(self, declaration_id: int, name: str) -> str: ...

    def result(self, declaration_id: int, number: str) -> str: ...

    def knowledge(self, ruleset_id: int, name: str) -> str: ...


@final
class Keys:
    """Layout of the storage tree, where a file name never contains a path."""

    __slots__ = ()

    def policy(self, policy_id: int, name: str) -> str:
        return f"policies/{policy_id}/documents/{self._name(name)}"

    def package(self, policy_id: int) -> str:
        return f"policies/{policy_id}/documents"

    def document(self, policy_id: int, path: str) -> str:
        return f"{self.package(policy_id)}/{Relative(path).path()}"

    def source(self, declaration_id: int, name: str) -> str:
        return f"declarations/{declaration_id}/source/{self._name(name)}"

    def result(self, declaration_id: int, number: str) -> str:
        return (
            f"declarations/{declaration_id}/result/"
            f"{self._name(number.replace('/', '_'))} – результат проверки.xlsx"
        )

    def knowledge(self, ruleset_id: int, name: str) -> str:
        return f"knowledge/{ruleset_id}/source/{self._name(name)}"

    def _name(self, name: str) -> str:
        if not name or name in {".", ".."} or "/" in name or "\\" in name or "\0" in name:
            raise EscapeError(f"Имя файла {name!r} содержит путь")
        return name
