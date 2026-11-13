from typing import Final, Protocol, final

from app.auth.errors import DeniedError


class Identity(Protocol):
    """Person who sends requests, with the roles and groups that define what they may do."""

    def id(self) -> str: ...

    def name(self) -> str: ...

    def allows(self, role: str) -> bool: ...

    def sees(self, group: str) -> bool: ...

    def group(self) -> str: ...


@final
class Person:
    """Identity with roles and groups; the group star stands for every group."""

    __slots__ = ("_groups", "_name", "_roles")

    def __init__(self, name: str, roles: frozenset[str], groups: frozenset[str]) -> None:
        self._name: Final = name
        self._roles: Final = roles
        self._groups: Final = groups

    def id(self) -> str:
        return self._name

    def name(self) -> str:
        return self._name

    def allows(self, role: str) -> bool:
        return role in self._roles

    def sees(self, group: str) -> bool:
        return group in self._groups or "*" in self._groups

    def group(self) -> str:
        owned = sorted(self._groups - {"*"})
        if not owned:
            raise DeniedError(f"У пользователя {self._name} нет группы доступа")
        return owned[0]


@final
class Local:
    """Identity of the single shared user of a deployment without login."""

    __slots__ = ("_id", "_person")

    def __init__(self, user: str) -> None:
        self._id: Final = user
        self._person: Final = Person(
            "Локальный пользователь",
            frozenset({"user", "expert", "admin"}),
            frozenset({"*", "dev"}),
        )

    def id(self) -> str:
        return self._id

    def name(self) -> str:
        return self._person.name()

    def allows(self, role: str) -> bool:
        return self._person.allows(role)

    def sees(self, group: str) -> bool:
        return self._person.sees(group)

    def group(self) -> str:
        return self._person.group()
