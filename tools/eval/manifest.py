import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, Protocol, final

import yaml

from tools.eval.gold import Gold, Sample
from tools.eval.number import Digits

_PARTS = ("dev", "holdout")

type _Order = Callable[[int], str]


class Edition(Protocol):
    """Version of the gold and the part, dev or holdout, that each of its declarations is in."""

    def version(self) -> str: ...

    def part(self, declaration: str) -> str: ...


class Division(Protocol):
    """Parts and policy groups of declarations, written into the manifest of the gold."""

    def entries(self) -> dict[str, dict[str, str]]: ...


@final
class Manifest:
    """Edition read from the manifest YAML: version, change log and the part of each declaration.

    Declarations of one policy group must be in one part, otherwise the holdout part would hint
    at the rules of a policy that the dev part tunes.
    """

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def version(self) -> str:
        return str(yaml.safe_load(self._text())["version"])

    def part(self, declaration: str) -> str:
        entries = self._entries()
        if Digits(declaration).text() not in entries:
            raise LookupError(
                f"Декларации {declaration} нет в манифесте эталона {self._path}: "
                f"выполните python -m tools.eval split"
            )
        return entries[Digits(declaration).text()][1]

    def _entries(self) -> dict[str, tuple[str, str]]:
        entries = {
            Digits(str(number)).text(): (str(entry["policy"]), str(entry["part"]))
            for number, entry in yaml.safe_load(self._text())["declarations"].items()
        }
        wrong = sorted(number for number, (_, part) in entries.items() if part not in _PARTS)
        if wrong:
            raise ValueError(
                f"В манифесте {self._path} у деклараций {', '.join(wrong)} "
                f"часть не dev и не holdout"
            )
        split = sorted(
            policy
            for policy in {policy for policy, _ in entries.values()}
            if len({part for group, part in entries.values() if group == policy}) > 1
        )
        if split:
            raise ValueError(
                f"В манифесте {self._path} декларации полисов {', '.join(split)} "
                f"попали в разные части"
            )
        return entries

    def _text(self) -> str:
        if not self._path.exists():
            raise FileNotFoundError(f"Манифест эталона {self._path} не найден")
        return self._path.read_text(encoding="utf-8")


@final
class Part:
    """Gold limited to the declarations whose part in the edition is one of the chosen parts."""

    __slots__ = ("_edition", "_gold", "_parts")

    def __init__(self, gold: Gold, edition: Edition, parts: frozenset[str]) -> None:
        self._gold: Final = gold
        self._edition: Final = edition
        self._parts: Final = parts

    def samples(self) -> tuple[Sample, ...]:
        samples = self._gold.samples()
        parts = {
            declaration: self._edition.part(declaration)
            for declaration in {sample.declaration() for sample in samples}
        }
        return tuple(sample for sample in samples if parts[sample.declaration()] in self._parts)


@final
class Split:
    """Division that keeps known parts and sends new policy groups to holdout up to a share.

    Declarations with one policy number form a group. A group keeps the part that the manifest
    already gives its declarations. New groups go to holdout in a fixed pseudo-random order while
    the holdout part stays within its share of all declarations, the rest go to dev.
    """

    __slots__ = ("_known", "_policies", "_share")

    def __init__(
        self, known: Mapping[str, Mapping[str, str]], policies: Mapping[str, str], share: float
    ) -> None:
        self._known: Final = known
        self._policies: Final = policies
        self._share: Final = share

    def entries(self) -> dict[str, dict[str, str]]:
        groups = self._groups()
        parts = self._parts(groups)
        return {
            declaration: {"policy": f"Полис-{index}", "part": parts[index - 1]}
            for index, group in enumerate(groups, start=1)
            for declaration in group
        }

    def _groups(self) -> tuple[tuple[str, ...], ...]:
        keys = {
            declaration: " ".join(policy.casefold().split()) or f"декларация {declaration}"
            for declaration, policy in self._policies.items()
        }
        return tuple(
            sorted(
                (
                    tuple(sorted(d for d in keys if keys[d] == key))
                    for key in dict.fromkeys(keys.values())
                ),
                key=lambda group: tuple(Digits(d).text().zfill(9) for d in group),
            )
        )

    def _parts(self, groups: tuple[tuple[str, ...], ...]) -> list[str]:
        parts = [self._known_part(group) for group in groups]
        room = self._share * sum(map(len, groups)) - sum(
            len(group) for group, part in zip(groups, parts, strict=True) if part == "holdout"
        )
        for index in sorted(
            (i for i, part in enumerate(parts) if not part), key=self._order(groups)
        ):
            parts[index] = "holdout" if len(groups[index]) <= room else "dev"
            room -= len(groups[index]) if parts[index] == "holdout" else 0
        return parts

    def _known_part(self, group: tuple[str, ...]) -> str:
        known = {Digits(number).text(): entry["part"] for number, entry in self._known.items()}
        found = {known[Digits(d).text()] for d in group if Digits(d).text() in known}
        if len(found) > 1:
            raise ValueError(
                f"Декларации {', '.join(group)} одного полиса уже стоят в разных частях: "
                f"{', '.join(sorted(found))}"
            )
        return next(iter(found), "")

    def _order(self, groups: tuple[tuple[str, ...], ...]) -> _Order:
        return lambda index: hashlib.sha256(
            ",".join(Digits(d).text() for d in groups[index]).encode()
        ).hexdigest()
