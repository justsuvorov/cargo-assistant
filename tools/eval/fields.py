from collections.abc import Mapping
from pathlib import Path
from typing import Final, Protocol, final

import yaml

from tools.eval.entry import Dropped, Entry, Open, Settled
from tools.eval.sheet import Mark


class Target(Protocol):
    """Field key of an MVP label, or the reason why the label has no single key in its form."""

    def field(self) -> str: ...

    def settle(self, mark: Mark, verdict: tuple[str, str, str]) -> Entry: ...

    def default(self, mark: Mark) -> Entry: ...


class Labels(Protocol):
    """Translation of MVP field labels into field keys for the form of each declaration."""

    def target(self, mark: Mark) -> Target: ...


@final
class Key:
    """Label that names exactly one field of the declaration form."""

    __slots__ = ("_key",)

    def __init__(self, key: str) -> None:
        self._key: Final = key

    def field(self) -> str:
        return self._key

    def settle(self, mark: Mark, verdict: tuple[str, str, str]) -> Entry:
        return Settled(mark, self._key, verdict)

    def default(self, mark: Mark) -> Entry:
        remark = mark.remark().strip(" .!").lower()
        if remark == "верно":
            return Settled(mark, self._key, (mark.answer(), "fsc-ok", ""))
        if not remark:
            return Open(mark, self._key, "Нет отметки ФСЦ", "")
        return Open(mark, self._key, "Замечание ФСЦ без решения eval", "")


@final
class Absent:
    """Label of a field that the form of the declaration does not have (D-14)."""

    __slots__ = ("_key", "_reason")

    def __init__(self, key: str, reason: str) -> None:
        self._key: Final = key
        self._reason: Final = reason

    def field(self) -> str:
        return self._key

    def settle(self, mark: Mark, verdict: tuple[str, str, str]) -> Entry:
        raise ValueError(
            f"Решение «{verdict[0]}» для строки {mark.shipment()} относится к полю {self._key}, "
            f"которого нет в форме декларации"
        )

    def default(self, mark: Mark) -> Entry:
        return Dropped(mark, self._key, self._reason)


@final
class Unmapped:
    """Label that matches no field key, or several keys, in the form of the declaration."""

    __slots__ = ("_label", "_reason")

    def __init__(self, label: str, reason: str) -> None:
        self._label: Final = label
        self._reason: Final = reason

    def field(self) -> str:
        return self._label

    def settle(self, mark: Mark, verdict: tuple[str, str, str]) -> Entry:
        raise ValueError(
            f"Решение «{verdict[0]}» для строки {mark.shipment()} относится к подписи "
            f"«{self._label}», у которой нет одного ключа поля"
        )

    def default(self, mark: Mark) -> Entry:
        return Open(mark, self._label, self._reason, "")


class Titles(Protocol):
    """Result titles of every field key by declaration form."""

    def titles(self) -> dict[str, dict[str, str]]: ...


@final
class Deck:
    """Titles read from the forms section of rule cards, one YAML file per field key."""

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def titles(self) -> dict[str, dict[str, str]]:
        return {
            str(card["field"]): {
                str(form): str(spec["title"]) for form, spec in card["forms"].items()
            }
            for card in (
                yaml.safe_load(path.read_text(encoding="utf-8"))
                for path in sorted(self._path.glob("*.yaml"))
            )
        }


@final
class Cards:
    """Labels matched with card titles in the form that the gold settings give each declaration."""

    __slots__ = ("_settings", "_titles")

    def __init__(
        self, titles: Mapping[str, Mapping[str, str]], settings: Mapping[str, Mapping[str, str]]
    ) -> None:
        self._titles: Final = titles
        self._settings: Final = settings

    def target(self, mark: Mark) -> Target:
        form = self._settings["forms"][mark.declaration()]
        key = self._keys().get(" ".join(mark.label().split()), "")
        if not key:
            return Unmapped(mark.label(), "Подпись MVP не сопоставлена ключу поля")
        if form in self._titles[key]:
            return Key(key)
        if key in self._settings["unmapped"]:
            return Unmapped(mark.label(), self._settings["unmapped"][key])
        return Absent(key, f"D-14: поля {key} нет в форме {form}")

    def _keys(self) -> dict[str, str]:
        return {
            " ".join(title.split()): key
            for key, forms in self._titles.items()
            for title in forms.values()
        }
