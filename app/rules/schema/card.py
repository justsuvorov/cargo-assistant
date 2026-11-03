from collections.abc import Callable, Mapping
from pathlib import Path
from string import Formatter
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic import Field as Attribute

from app.domain.card import Card
from app.domain.semantics import Semantics
from app.domain.status import Match, Mismatch, Review, Status
from app.rules.card import Ruled
from app.rules.ceiling import Ceiling
from app.rules.errors import CardError
from app.rules.exact import Exact
from app.rules.filled import Parts, Party
from app.rules.fork import Condition, Flag, Fork, Mixed
from app.rules.fuzzy import Fuzzy
from app.rules.modes import Conveyance, Modes
from app.rules.probe import Accepted, Constant, Doubted, Emptied, Grounded, Probe
from app.rules.rows import Rowwise
from app.rules.semantic import Asking
from app.rules.window import Window
from app.rules.wording import PLACEHOLDERS, Comments

type _Check = Literal[
    "exact", "fuzzy", "date_range", "lte_limit", "filled", "in_list", "conditional", "semantic"
]
type _Status = Literal["match", "mismatch", "review"]

_STATUSES: Mapping[str, Status] = {"match": Match(), "mismatch": Mismatch(), "review": Review()}
_GROUNDED = frozenset({"exact", "fuzzy", "date_range", "lte_limit", "in_list", "semantic"})
_BRANCHES = frozenset({*_GROUNDED, "filled", *_STATUSES})
_FORMS = frozenset({"vertical", "psg"})
_MIXED = ".mixed"


class Form(BaseModel):
    """Place of a card in the result of one declaration form: row order and field title."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order: int
    title: str


class Params(BaseModel):
    """Parameters of the check types; each check reads only its own ones."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    blank_words: tuple[str, ...] = ()
    shape: Literal["", "party"] = ""
    legal_forms: tuple[str, ...] = ()
    foreign_forms: tuple[str, ...] = ()
    parts: tuple[Literal["number", "date"], ...] = ()
    ignore: tuple[str, ...] = ()
    synonyms: dict[str, str] = Attribute(default_factory=dict)
    bounds: tuple[Literal["start", "end"], ...] = ()
    extension: str = ""
    foreign_currency: _Status = "review"
    modes: dict[str, tuple[str, ...]] = Attribute(default_factory=dict)
    exclusions: str = ""
    when: str = ""
    then: str = "filled"
    otherwise: str = Attribute(default="", alias="else")
    then_if_empty: Literal["", "match", "mismatch", "review"] = ""


class Spec(BaseModel):
    """Rule card as written in its YAML file, checked against the card schema of the
    contracts and able to build the card object of the engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    forms: dict[str, Form]
    subject: str
    clause: str
    check: _Check
    rule: str
    params: Params = Params()
    if_empty: Literal["match", "mismatch", "review", "skip"]
    comments: dict[str, str]
    status: Literal["draft", "approved"]
    evidence: tuple[str, ...] = ()
    clarify: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _known_forms(self) -> "Spec":
        if not self.forms or set(self.forms) - _FORMS:
            raise ValueError(f"формы карточки должны быть из {sorted(_FORMS)}")
        return self

    @model_validator(mode="after")
    def _worded(self) -> "Spec":
        if {"match", "mismatch", "review"} - set(self.comments):
            raise ValueError("в comments нужны шаблоны match, mismatch и review")
        unknown = {
            name
            for template in self.comments.values()
            for _, name, _, _ in Formatter().parse(template)
            if name is not None and name not in PLACEHOLDERS
        }
        if unknown:
            raise ValueError(f"в шаблонах неизвестные подстановки {sorted(unknown)}")
        return self

    @model_validator(mode="after")
    def _supported(self) -> "Spec":
        if self.if_empty == "skip":
            raise ValueError("if_empty skip движок пока не поддерживает")
        grounded = (
            {self.check, self.params.then} & _GROUNDED
            if self.check == "conditional"
            else {self.check} & _GROUNDED
        )
        if grounded and self.clause == "none":
            raise ValueError(f"проверке {sorted(grounded)} нужен пункт полиса, а clause равен none")
        return self

    @model_validator(mode="after")
    def _parametrised(self) -> "Spec":
        problems = (
            ("date_range требует bounds", self.check == "date_range" and not self.params.bounds),
            (
                "conditional требует when и else",
                self.check == "conditional" and not (self.params.when and self.params.otherwise),
            ),
            (
                f"ветви conditional должны быть из {sorted(_BRANCHES)}",
                self.check == "conditional"
                and bool({self.params.then, self.params.otherwise} - _BRANCHES),
            ),
            (
                "shape party требует legal_forms",
                self.params.shape == "party" and not self.params.legal_forms,
            ),
        )
        broken = [text for text, failed in problems if failed]
        if broken:
            raise ValueError(broken[0])
        return self

    def covers(self, form: str) -> bool:
        return form in self.forms

    def order(self, form: str) -> int:
        return self.forms[form].order

    def card(self, specs: Mapping[str, "Spec"], semantics: Semantics) -> Card:
        return Ruled(
            self.field,
            {form: place.title for form, place in self.forms.items()},
            self.subject,
            Rowwise(self.field, Doubted(self._probe(specs)), Comments(self.comments), semantics),
        )

    def _probe(self, specs: Mapping[str, "Spec"]) -> Probe:
        if self.check == "conditional":
            return Accepted(
                self.field,
                Fork(
                    self._condition(specs),
                    self._branch(
                        self.params.then, self.params.then_if_empty or self.if_empty, "then"
                    ),
                    self._branch(self.params.otherwise, self.if_empty, "otherwise"),
                ),
            )
        return Emptied(
            self.params.blank_words,
            _STATUSES[self.if_empty],
            Accepted(self.field, self._core(self.check)),
        )

    def _branch(self, name: str, empty: str, label: str) -> Probe:
        if name in _STATUSES:
            return Constant(_STATUSES[name], label)
        return Emptied(self.params.blank_words, _STATUSES[empty], self._core(name))

    def _condition(self, specs: Mapping[str, "Spec"]) -> Condition:
        if not self.params.when.endswith(_MIXED):
            return Flag(self.params.when)
        key = self.params.when.removesuffix(_MIXED)
        if key not in specs or not specs[key].params.modes:
            raise CardError(
                f"Карточка {self.field} ссылается на {self.params.when}, "
                f"но у карточки {key} нет словаря modes"
            )
        return Mixed(key, Modes(specs[key].params.modes))

    def _core(self, check: str) -> Probe:
        params = self.params
        cores: Mapping[str, Callable[[], Probe]] = {
            "exact": lambda: Grounded(self.clause, Exact(params.parts, params.ignore)),
            "fuzzy": lambda: Grounded(self.clause, Fuzzy(params.synonyms)),
            "date_range": lambda: Grounded(self.clause, Window(params.bounds, params.extension)),
            "lte_limit": lambda: Grounded(self.clause, Ceiling(_STATUSES[params.foreign_currency])),
            "in_list": lambda: Grounded(
                self.clause,
                Conveyance(Modes(params.modes)) if params.modes else Fuzzy(params.synonyms),
            ),
            "semantic": lambda: Grounded(
                self.clause,
                Asking((params.exclusions,) if params.exclusions else (), self.rule),
            ),
            "filled": lambda: Parts(
                params.parts,
                Party(params.legal_forms, params.foreign_forms)
                if params.shape == "party"
                else Constant(Match(), "filled"),
            ),
        }
        return cores[check]()


def spec(path: Path) -> Spec:
    try:
        written = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise CardError(
            f"Карточка {path.name} не читается как YAML: {str(error).splitlines()[0]}"
        ) from error
    try:
        found = Spec.model_validate(written)
    except ValidationError as error:
        problem = error.errors()[0]
        raise CardError(
            f"Карточка {path.name} не соответствует схеме: "
            f"{'.'.join(str(part) for part in problem['loc']) or 'карточка'} — {problem['msg']}"
        ) from error
    if found.field != path.stem:
        raise CardError(f"Карточка {path.name} описывает поле {found.field}, а не {path.stem}")
    return found
