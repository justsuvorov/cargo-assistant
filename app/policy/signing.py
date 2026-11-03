from datetime import date
from typing import Final, final

from app.policy.outcome import Outcome, Result
from app.policy.package import Amendment, Paper
from app.policy.papers import Agreement
from app.policy.terms import Terms
from app.policy.title import Title


@final
class Signing:
    """Step that turns a paper with the title of an amendment into a signed amendment.

    A paper with no number, with no signing date or with no entry into force is a draft, and a
    paper whose declarations are named but blank has an unknown scope. Both are left out and
    named in problems. An entry into force that precedes signing is kept and named in problems.
    """

    __slots__ = ("_paper",)

    def __init__(self, paper: Paper) -> None:
        self._paper: Final = paper

    def survey(self) -> Outcome[Amendment]:
        title, terms = Title(self._paper.text()), Terms(self._paper.text())
        if not title.number():
            return Result(
                (),
                (
                    f"В файле {self._paper.reference()} не прочитан номер ДС,"
                    " документ исключён из пакета",
                ),
            )
        label = f"ДС {title.number()[0]} ({self._paper.reference()})"
        if not (terms.signed() and terms.effective()):
            return Result((), (f"{label} исключено как проект: не указана {self._missing(terms)}",))
        if terms.unclear():
            return Result(
                (),
                (f"{label} исключено: область действия названа, но номера деклараций не читаются",),
            )
        return Result(
            (Agreement(self._paper, title.number()[0], terms.effective()[0], terms.scope()),),
            self._order(label, terms.signed()[0], terms.effective()[0]),
        )

    def _missing(self, terms: Terms) -> str:
        return "дата " + " и ".join(
            word
            for word, known in (("подписания", terms.signed()), ("вступления", terms.effective()))
            if not known
        )

    def _order(self, label: str, signed: date, effective: date) -> tuple[str, ...]:
        return (
            (
                f"{label}: дата вступления {effective:%d.%m.%Y} раньше даты подписания"
                f" {signed:%d.%m.%Y}",
            )
            if effective < signed
            else ()
        )
