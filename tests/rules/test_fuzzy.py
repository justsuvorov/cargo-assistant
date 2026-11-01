import random
import string

from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.place import Spot
from app.domain.policy import Vacant
from app.rules.answers import Replies
from app.rules.fuzzy import Fuzzy
from app.rules.wording import Comments
from tests.rules.fakes import Paper, Text


def _name() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=6))


def _code(declared: str, clause: Text) -> str:
    return (
        Fuzzy({"ТД": "Торговый дом", "ООО": "Общество с ограниченной ответственностью"})
        .outcome(
            Fields().field("insurer", (declared,)),
            clause,
            Paper("2", "psg", ({"insurer": (declared,)},)).shipments()[0],
            Vacant("1"),
        )
        .verdict(
            Spot("2", "insurer"),
            Comments({"match": "", "mismatch": "", "review": ""}),
            Replies((), ()),
        )
        .reason()
        .code()
    )


def test_abbreviation_and_full_form_are_the_same_name() -> None:
    name = _name()
    assert_that(
        _code(f"Торговый дом «{name}»", Text("ГП", f'ТД "{name.upper()}"')),
        equal_to("insurer.same"),
        "Fuzzy does not match an abbreviation with its full form",
    )


def test_other_name_is_different() -> None:
    assert_that(
        _code(f"ООО «{_name()}»", Text("ГП", f"ООО «{_name()}»")),
        equal_to("insurer.different"),
        "Fuzzy does not reject another name",
    )


def test_contained_name_needs_a_person() -> None:
    name = _name()
    assert_that(
        _code(f"ООО «{name}»", Text("ГП", f"ООО «{name} логистик»")),
        equal_to("insurer.partial"),
        "Fuzzy does not ask for review of a name contained in another",
    )


def test_one_of_the_listed_names_is_enough() -> None:
    name = _name()
    assert_that(
        _code(f"АО {name}", Text("Перечень", entries=("ООО Первый", f"АО «{name}»"))),
        equal_to("insurer.same"),
        "Fuzzy does not find a name among the items of the clause",
    )
