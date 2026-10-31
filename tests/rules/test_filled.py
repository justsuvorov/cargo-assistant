import random
import string

from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.place import Spot
from app.domain.policy import Vacant
from app.domain.status import Match
from app.rules.answers import Replies
from app.rules.filled import Parts, Party
from app.rules.probe import Constant, Probe
from app.rules.wording import Comments
from tests.rules.fakes import Paper


def _name() -> str:
    return "".join(random.choices(string.ascii_letters, k=7))


def _code(probe: Probe, key: str, texts: tuple[str, ...]) -> str:
    return (
        probe.outcome(
            Fields().field(key, texts),
            Paper("6", "vertical", ({key: texts},)).shipments()[0],
            Vacant("1"),
        )
        .verdict(
            Spot("6", key), Comments({"match": "", "mismatch": "", "review": ""}), Replies((), ())
        )
        .reason()
        .code()
    )


def _party() -> Party:
    return Party(("ООО", "АО", "Общество с ограниченной ответственностью"), ("LLC", "GmbH"))


def test_number_and_date_of_a_document_are_enough() -> None:
    assert_that(
        _code(
            Parts(("number", "date"), Constant(Match(), "filled")),
            "document",
            ("771-12306011 от 19.09.2026",),
        ),
        equal_to("document.filled"),
        "Parts does not accept a document with a number and a date",
    )


def test_document_without_date_is_incomplete() -> None:
    assert_that(
        _code(Parts(("number", "date"), Constant(Match(), "filled")), "document", ("771-1230",)),
        equal_to("document.incomplete"),
        "Parts does not reject a document without a date",
    )


def test_one_of_several_dates_is_enough() -> None:
    assert_that(
        _code(
            Parts(("date",), Constant(Match(), "filled")),
            "document_date",
            ("10.09, 16.09, 14.09.2026",),
        ),
        equal_to("document_date.filled"),
        "Parts does not accept a list of dates with one year",
    )


def test_party_with_legal_form_and_name_is_filled() -> None:
    assert_that(
        _code(_party(), "beneficiary", (f"ООО «{_name()}»",)),
        equal_to("beneficiary.filled"),
        "Party does not accept a legal form with a name",
    )


def test_full_legal_form_counts_too() -> None:
    assert_that(
        _code(_party(), "carrier", (f"Общество с ограниченной ответственностью {_name()}",)),
        equal_to("carrier.filled"),
        "Party does not accept a legal form spelled out in full",
    )


def test_name_without_legal_form_is_incomplete() -> None:
    assert_that(
        _code(_party(), "beneficiary", (f"{_name()} Трейд",)),
        equal_to("beneficiary.incomplete"),
        "Party does not reject a name without a legal form",
    )


def test_legal_form_without_name_is_incomplete() -> None:
    assert_that(
        _code(_party(), "beneficiary", ("ООО",)),
        equal_to("beneficiary.incomplete"),
        "Party does not reject a legal form without a name",
    )


def test_legal_form_inside_a_word_does_not_count() -> None:
    assert_that(
        _code(_party(), "beneficiary", ("Гаост Трейд",)),
        equal_to("beneficiary.incomplete"),
        "Party does not ignore letters of a legal form inside a word",
    )


def test_foreign_legal_form_needs_a_person() -> None:
    assert_that(
        _code(_party(), "carrier", (f"{_name()} GmbH",)),
        equal_to("carrier.foreign"),
        "Party does not ask for review of a foreign legal form",
    )
