from typing import Final, Protocol, final


class Identity(Protocol):
    """Person who sends requests, with the roles that define what they may do."""

    def id(self) -> str: ...

    def name(self) -> str: ...

    def allows(self, role: str) -> bool: ...

    def card(self) -> dict[str, str]: ...


@final
class Person:
    """Identity with a name and the roles that define what a person may do."""

    __slots__ = ("_id", "_name", "_roles")

    def __init__(self, ident: str, name: str, roles: frozenset[str]) -> None:
        self._id: Final = ident
        self._name: Final = name
        self._roles: Final = roles

    def id(self) -> str:
        return self._id

    def name(self) -> str:
        return self._name

    def allows(self, role: str) -> bool:
        return role in self._roles

    def card(self) -> dict[str, str]:
        return {
            "sub": self._id,
            "name": self._name,
            "roles": ",".join(sorted(self._roles)),
        }


@final
class Local:
    """Identity of the single shared user of a deployment without login."""

    __slots__ = ("_id", "_person")

    def __init__(self, user: str) -> None:
        self._id: Final = user
        self._person: Final = Person(
            user,
            "Локальный пользователь",
            frozenset({"user", "expert", "admin"}),
        )

    def id(self) -> str:
        return self._id

    def name(self) -> str:
        return self._person.name()

    def allows(self, role: str) -> bool:
        return self._person.allows(role)

    def card(self) -> dict[str, str]:
        return {**self._person.card(), "sub": self._id}
