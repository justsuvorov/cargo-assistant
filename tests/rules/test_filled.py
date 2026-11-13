import random
import string

from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.place import Spot
from app.domain.policy import Vacant
from app.domain.status import Match, Mismatch, Review, Status
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


def _ruling(probe: Probe, key: str, texts: tuple[str, ...]) -> tuple[str, str]:
    verdict = probe.outcome(
        Fields().field(key, texts),
        Paper("6", "vertical", ({key: texts},)).shipments()[0],
        Vacant("1"),
    ).verdict(
        Spot("6", key), Comments({"match": "", "mismatch": "", "review": ""}), Replies((), ())
    )
    return (verdict.status().key(), verdict.reason().code())


def _status() -> Status:
    return random.choice((Match(), Mismatch(), Review()))


def _party() -> Party:
    return Party(
        ("ООО", "АО", "Общество с ограниченной ответственностью"),
        ("LLC", "GmbH", "Ltd"),
        {"foreign": Review(), "fused": Review(), "latin": Mismatch(), "unformed": Mismatch()},
    )


def _statused(name: str, status: Status) -> Party:
    return Party(
        ("ООО", "АО"),
        ("LLC", "Ltd"),
        {
            **{key: Review() for key in ("foreign", "fused", "latin", "unformed")},
            name: status,
        },
    )


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


def test_name_without_legal_form_is_unformed() -> None:
    assert_that(
        _code(_party(), "beneficiary", (f"{_name()} Трейд",)),
        equal_to("beneficiary.unformed"),
        "Party does not tell a name without a legal form",
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
        equal_to("beneficiary.unformed"),
        "Party does not ignore letters of a legal form inside a word",
    )


def test_foreign_legal_form_gets_the_status_of_the_card() -> None:
    status = _status()
    assert_that(
        _ruling(_statused("foreign", status), "carrier", (f"{_name()} Co., Ltd",)),
        equal_to((status.key(), "carrier.foreign")),
        "Party does not give the status of the card to a foreign legal form",
    )


def test_cyrillic_foreign_legal_form_gets_the_status_of_the_card() -> None:
    status = _status()
    assert_that(
        _ruling(
            Party(
                ("ООО",),
                ("ТОО",),
                {
                    **{key: Review() for key in ("foreign", "fused", "latin", "unformed")},
                    "foreign": status,
                },
            ),
            "beneficiary",
            ("ТОО «Степь»",),
        ),
        equal_to((status.key(), "beneficiary.foreign")),
        "Party does not give the status of the card to a foreign legal form in Cyrillic",
    )


def test_foreign_legal_form_fused_with_the_next_word_gets_the_status_of_the_card() -> None:
    status = _status()
    assert_that(
        _ruling(
            _statused("fused", status),
            "beneficiary",
            (f"{_name().upper()} LLCAddress: Moscow, {random.randint(1, 99)}",),
        ),
        equal_to((status.key(), "beneficiary.fused")),
        "Party does not tell a foreign legal form fused with the next word",
    )


def test_russian_legal_form_fused_with_the_next_word_gets_the_status_of_the_card() -> None:
    status = _status()
    assert_that(
        _ruling(_statused("fused", status), "beneficiary", ("ОООРомашка, г. Москва",)),
        equal_to((status.key(), "beneficiary.fused")),
        "Party does not tell a Russian legal form fused with the next word",
    )


def test_word_that_starts_with_letters_of_a_legal_form_is_not_fused() -> None:
    assert_that(
        _code(_statused("fused", Match()), "carrier", ("Аорта Трейд",)),
        equal_to("carrier.unformed"),
        "Party does not tell a word that starts with letters of a legal form from a fused form",
    )


def test_capitalised_word_that_starts_with_letters_of_a_legal_form_is_not_fused() -> None:
    assert_that(
        _code(_statused("fused", Match()), "carrier", ("LLCOMPANY TRADE",)),
        equal_to("carrier.latin"),
        "Party does not tell a word in capitals from a legal form fused with the next word",
    )


def test_name_only_in_latin_letters_gets_the_status_of_the_card() -> None:
    status = _status()
    assert_that(
        _ruling(_statused("latin", status), "carrier", (f"{_name()} AIRLINES-{_name()}",)),
        equal_to((status.key(), "carrier.latin")),
        "Party does not give the status of the card to a name only in Latin letters",
    )


def test_name_with_cyrillic_letters_is_not_latin() -> None:
    status = _status()
    assert_that(
        _ruling(_statused("unformed", status), "carrier", (f"{_name()} Логистик",)),
        equal_to((status.key(), "carrier.unformed")),
        "Party does not tell a name with Cyrillic letters from a name in Latin letters",
    )


def test_name_without_letters_is_not_latin() -> None:
    assert_that(
        _code(_party(), "carrier", (str(random.randint(100, 999)),)),
        equal_to("carrier.unformed"),
        "Party does not tell a name without letters from a name in Latin letters",
    )
