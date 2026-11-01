from collections import Counter
from pathlib import Path
from typing import Final, Protocol, final

from app.domain.card import Card
from app.domain.semantics import Semantics
from app.rules.errors import CardError
from app.rules.schema.card import Spec, spec


class Deck(Protocol):
    """Rule cards that serve one declaration form, in the order of its result rows."""

    def cards(self, form: str) -> tuple[Card, ...]: ...


@final
class Cards:
    """Deck read from the YAML files of a folder, one card per field, drafts included.

    Every file is read and checked on each call, so a broken card fails loudly before any
    declaration is checked.
    """

    __slots__ = ("_folder", "_semantics")

    def __init__(self, folder: Path, semantics: Semantics) -> None:
        self._folder: Final = folder
        self._semantics: Final = semantics

    def cards(self, form: str) -> tuple[Card, ...]:
        specs = {path.stem: spec(path) for path in sorted(self._folder.glob("*.yaml"))}
        chosen = sorted(
            (each for each in specs.values() if each.covers(form)),
            key=lambda each: each.order(form),
        )
        if not chosen:
            raise CardError(f"В каталоге {self._folder} нет карточек для формы {form}")
        self._unique(chosen, form)
        return tuple(each.card(specs, self._semantics) for each in chosen)

    def _unique(self, chosen: list[Spec], form: str) -> None:
        twins = sorted(
            order
            for order, count in Counter(each.order(form) for each in chosen).items()
            if count > 1
        )
        if twins:
            raise CardError(f"В форме {form} у нескольких карточек одинаковый order {twins}")
