import random
import string

from hamcrest import assert_that, equal_to

from app.domain.declaration import Declaration
from app.domain.place import Spot
from app.domain.policy import Policy, Vacant
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Match
from app.domain.verdict import Ruling, Verdict
from app.reconcile.reconciliation import Carded
from tests.rules.fakes import Paper


class Fixed:
    """Card that gives a verdict per given shipment number, twice for the first one."""

    def __init__(self, field: str, *, twice: bool) -> None:
        self._field = field
        self._twice = twice

    def field(self) -> str:
        return self._field

    def covers(self, form: str) -> bool:
        return bool(form)

    def title(self, form: str) -> str:
        return form

    def subject(self) -> str:
        return self._field

    def verdicts(self, declaration: Declaration, policy: Policy) -> tuple[Verdict, ...]:
        rows = tuple(each.number() for each in declaration.shipments())
        return tuple(
            Ruling(
                Spot(number, self._field),
                Match(),
                Cause(f"{self._field}.{index}", "rule"),
                Note(policy.number(), ""),
            )
            for index, number in enumerate((*rows, rows[0]) if self._twice else rows)
        )


class Deck:
    """Deck of two fixed cards."""

    def cards(self, form: str) -> tuple[Fixed, ...]:
        return (Fixed("a" + form, twice=True), Fixed("b" + form, twice=False))


def word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=6))


def test_gives_verdicts_row_after_row_with_cards_in_order_and_first_verdict_of_a_place() -> None:
    form = word()
    declaration = Paper(word(), form, ({"x": ("1",)}, {"x": ("2",)}))
    first, second = (each.number() for each in declaration.shipments())
    found = Carded(Deck()).findings(declaration, Vacant("0000"))
    assert_that(
        (
            [
                (each.place().shipment(), each.place().field(), each.reason().code())
                for each in found.verdicts()
            ],
            found.expected(),
        ),
        equal_to(
            (
                [
                    (first, "a" + form, "a" + form + ".0"),
                    (first, "b" + form, "b" + form + ".0"),
                    (second, "a" + form, "a" + form + ".1"),
                    (second, "b" + form, "b" + form + ".1"),
                ],
                4,
            )
        ),
        "Reconciliation does not give one verdict per row and card in the order of the result",
    )
