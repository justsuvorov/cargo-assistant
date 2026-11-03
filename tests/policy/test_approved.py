import random
import uuid
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from hamcrest import assert_that, contains_string, equal_to

from app.domain.clause import Absent
from app.domain.errors import UnreadableError
from app.domain.field import Blank
from app.domain.policy import Policy
from app.domain.verdict import Verdict
from app.policy.approved import Approved
from app.policy.schema.profile import Profile, Sum, Wording
from app.rules.cards import Cards
from tests.rules.fakes import Mute, Paper


def test_approved_policy_gives_the_number_of_the_profile() -> None:
    number = uuid.uuid4().hex
    assert_that(
        Approved(_profile({}, number=number)).number(),
        equal_to(number),
        "Approved policy does not give the number of the profile",
    )


def test_approved_policy_gives_the_special_conditions_of_the_profile() -> None:
    conditions = (uuid.uuid4().hex, uuid.uuid4().hex)
    assert_that(
        Approved(_profile({}, conditions=conditions)).conditions(),
        equal_to(conditions),
        "Approved policy does not give the special conditions of the profile",
    )


def test_clause_missing_from_the_profile_is_absent() -> None:
    key = uuid.uuid4().hex
    assert_that(
        Approved(_profile({})).clause(key, _Trip("1", _day())).reference(),
        equal_to(Absent(key).reference()),
        "Clause missing from the profile is not absent",
    )


def test_clause_is_absent_when_no_revision_is_in_force_yet() -> None:
    day = _day()
    profile = _profile({"term": (_wording("ГП п. 6", day),)})
    assert_that(
        Approved(profile).clause("term", _Trip("1", day - timedelta(days=1))).reference(),
        equal_to(Absent("term").reference()),
        "Clause is not absent when no revision is in force yet",
    )


def test_clause_is_absent_when_every_revision_concerns_other_declarations() -> None:
    number = random.randint(100, 499)
    wording = _wording("ДС 3", date(2000, 1, 1), amendment=3, scope=(str(number),))
    assert_that(
        Approved(_profile({"limit": (wording,)}))
        .clause("limit", _Trip(str(number + 500), _day()))
        .reference(),
        equal_to(Absent("limit").reference()),
        "Clause is not absent when every revision concerns other declarations",
    )


def test_amendment_applies_to_a_shipment_that_starts_on_the_day_it_takes_effect() -> None:
    day = _day()
    assert_that(
        Approved(_succession(day)).clause("term", _Trip("1", day)).reference(),
        equal_to("ДС 1"),
        "Amendment does not apply to a shipment that starts on the day it takes effect",
    )


def test_amendment_waits_when_it_takes_effect_the_day_after_the_shipment_starts() -> None:
    day = _day()
    assert_that(
        Approved(_succession(day + timedelta(days=1))).clause("term", _Trip("1", day)).reference(),
        equal_to("ГП п. 6"),
        "Amendment does not wait when it takes effect the day after the shipment starts",
    )


def test_latest_revision_by_date_wins_over_a_greater_number() -> None:
    day = _day()
    profile = _profile(
        {
            "term": (
                _wording("ДС 9", day, amendment=9),
                _wording("ДС 3", day + timedelta(days=1), amendment=3),
            )
        }
    )
    assert_that(
        Approved(profile).clause("term", _Trip("1", day + timedelta(days=2))).reference(),
        equal_to("ДС 3"),
        "Latest revision by date does not win over a greater number",
    )


def test_greater_number_wins_among_amendments_of_one_date() -> None:
    day = _day()
    profile = _profile(
        {
            "limit": (
                _wording("ДС 23", day, amendment=23),
                _wording("ДС 20", day, amendment=20),
                _wording("ГП п. 12", day - timedelta(days=90)),
            )
        }
    )
    assert_that(
        Approved(profile).clause("limit", _Trip("1", day)).reference(),
        equal_to("ДС 23"),
        "Amendment 23 does not win over amendment 20 of the same date",
    )


def test_amendment_to_the_declaration_wins_over_a_later_general_one() -> None:
    day = _day()
    number = str(random.randint(100, 999))
    profile = _profile(
        {
            "limit": (
                _wording("ДС 1", day, amendment=1, scope=(number,)),
                _wording("ДС 2", day + timedelta(days=5), amendment=2),
            )
        }
    )
    assert_that(
        Approved(profile).clause("limit", _Trip(number, day + timedelta(days=9))).reference(),
        equal_to("ДС 1"),
        "Amendment to the declaration does not win over a later general amendment",
    )


def test_amendment_to_the_declaration_waits_for_its_date_behind_the_general_wording() -> None:
    day = _day()
    number = str(random.randint(100, 999))
    profile = _profile(
        {
            "limit": (
                _wording("ГП п. 12", day - timedelta(days=30)),
                _wording("ДС 1", day + timedelta(days=1), amendment=1, scope=(number,)),
            )
        }
    )
    assert_that(
        Approved(profile).clause("limit", _Trip(number, day)).reference(),
        equal_to("ГП п. 12"),
        "Amendment to the declaration does not wait for its date behind the general wording",
    )


def test_latest_amendment_wins_among_those_to_one_declaration() -> None:
    day = _day()
    number = str(random.randint(100, 999))
    profile = _profile(
        {
            "limit": (
                _wording("ДС 1", day, amendment=1, scope=(number,)),
                _wording("ДС 2", day + timedelta(days=5), amendment=2, scope=(number,)),
            )
        }
    )
    assert_that(
        Approved(profile).clause("limit", _Trip(number, day + timedelta(days=9))).reference(),
        equal_to("ДС 2"),
        "Latest amendment does not win among those to one declaration",
    )


def test_later_amendments_to_other_declarations_leave_the_general_wording_in_force() -> None:
    day = _day()
    number = random.randint(100, 499)
    others = tuple(
        _wording(f"ДС {each}", day + timedelta(days=each), amendment=each, scope=(str(other),))
        for each, other in ((25, number + 500), (26, number + 501), (27, number + 502))
    )
    profile = _profile(
        {
            "limit": (
                _wording("ДС 23", day, amendment=23),
                _wording("ДС 20", day, amendment=20),
                *others,
            )
        }
    )
    assert_that(
        Approved(profile).clause("limit", _Trip(str(number), day + timedelta(days=99))).reference(),
        equal_to("ДС 23"),
        "Later amendments to other declarations do not leave the general wording in force",
    )


def test_general_amendment_stays_in_force_after_the_term_in_its_text() -> None:
    day = _day()
    profile = _profile(
        {
            "term": (
                _wording("ГП п. 6", day - timedelta(days=30)),
                _wording("ДС 8", day, amendment=8, dates=(day, day + timedelta(days=1))),
            )
        }
    )
    assert_that(
        Approved(profile).clause("term", _Trip("1", day + timedelta(days=200))).reference(),
        equal_to("ДС 8"),
        "General amendment does not stay in force after the term in its text",
    )


def test_clause_finds_the_declaration_by_digits_only() -> None:
    wording = _wording("ДС 4", date(2000, 1, 1), amendment=4, scope=("Р-070",))
    assert_that(
        Approved(_profile({"limit": (wording,)})).clause("limit", _Trip("70", _day())).reference(),
        equal_to("ДС 4"),
        "Clause does not find the declaration by digits only",
    )


def test_revisions_of_equal_rank_name_both_sources_for_a_person() -> None:
    assert_that(
        Approved(_rivals(_day())).clause("transport", _Trip("1", _day())).reference(),
        contains_string("ДС 4 п. 1, ДС 4 п. 2"),
        "Revisions of equal rank do not name both sources for a person",
    )


def test_revisions_of_equal_rank_state_no_facts() -> None:
    assert_that(
        Approved(_rivals(_day())).clause("transport", _Trip("1", _day())).text(),
        equal_to(""),
        "Revisions of equal rank do not stay without a chosen text",
    )


def test_repeated_revision_counts_once() -> None:
    day = _day()
    wording = _wording("ДС 4", day, amendment=4)
    assert_that(
        Approved(_profile({"transport": (wording, wording)}))
        .clause("transport", _Trip("1", day))
        .text(),
        equal_to(wording.text),
        "Repeated revision does not count once",
    )


def test_clause_of_a_shipment_without_a_start_explains_it_in_the_reference() -> None:
    profile = _profile({"limit": (_wording("ГП п. 12", _day()),)})
    assert_that(
        Approved(profile).clause("limit", _Undated()).reference(),
        contains_string("дата начала перевозки"),
        "Clause of a shipment without a start does not explain it in the reference",
    )


def test_number_clause_comes_from_the_requisites_of_the_profile() -> None:
    number = uuid.uuid4().hex
    assert_that(
        Approved(_profile({}, number=number)).clause("number", _Trip("1", _day())).text(),
        equal_to(number),
        "Number clause does not come from the requisites of the profile",
    )


def test_number_clause_dates_the_policy_by_its_issue() -> None:
    issued = _day()
    assert_that(
        Approved(_profile({}, issued=issued)).clause("number", _Trip("1", _day())).dates(),
        equal_to((issued,)),
        "Number clause does not date the policy by its issue",
    )


def test_insurer_clause_comes_from_the_requisites_of_the_profile() -> None:
    insurer = uuid.uuid4().hex
    assert_that(
        Approved(_profile({}, insurer=insurer)).clause("insurer", _Trip("1", _day())).text(),
        equal_to(insurer),
        "Insurer clause does not come from the requisites of the profile",
    )


def test_requisites_need_no_start_of_the_shipment() -> None:
    number = uuid.uuid4().hex
    assert_that(
        Approved(_profile({}, number=number)).clause("number", _Undated()).text(),
        equal_to(number),
        "Requisites do not stay readable without a start of the shipment",
    )


def test_insurer_stated_among_the_clauses_replaces_the_requisite() -> None:
    day = _day()
    profile = _profile({"insurer": (_wording("ДС 2", day, amendment=2, text="Новое имя"),)})
    assert_that(
        Approved(profile).clause("insurer", _Trip("1", day)).text(),
        equal_to("Новое имя"),
        "Insurer stated among the clauses does not replace the requisite",
    )


def test_real_cards_match_a_start_inside_the_term() -> None:
    assert_that(
        _statuses("period_start", _paper("1", _row()), Approved(_cover())),
        equal_to(("match",)),
        "Real cards do not match a start inside the term",
    )


def test_real_cards_reject_an_end_after_the_term() -> None:
    row = {**_row(), "period_end": ("15.02.2030",)}
    assert_that(
        _statuses("period_end", _paper("1", row), Approved(_cover())),
        equal_to(("mismatch",)),
        "Real cards do not reject an end after the term",
    )


def test_real_cards_match_a_start_within_the_term_extended_by_an_amendment() -> None:
    row = {**_row(), "period_start": ("10.03.2028",), "period_end": ("20.03.2028",)}
    assert_that(
        _statuses("period_start", _paper("1", row), Approved(_cover())),
        equal_to(("match",)),
        "Real cards do not match a start within the term extended by an amendment",
    )


def test_real_cards_match_a_sum_within_the_limit() -> None:
    assert_that(
        _statuses("sum", _paper("1", _row()), Approved(_cover())),
        equal_to(("match",)),
        "Real cards do not match a sum within the limit",
    )


def test_real_cards_reject_a_sum_over_the_general_limit() -> None:
    row = {**_row(), "sum": ("5 000 000", "RUB")}
    assert_that(
        _statuses("sum", _paper("1", row), Approved(_cover())),
        equal_to(("mismatch",)),
        "Real cards do not reject a sum over the general limit",
    )


def test_real_cards_match_a_sum_within_the_limit_of_an_amendment_to_the_declaration() -> None:
    row = {**_row(), "sum": ("5 000 000", "RUB")}
    assert_that(
        _statuses("sum", _paper("Р-070", row), Approved(_cover())),
        equal_to(("match",)),
        "Real cards do not apply the limit of an amendment to its own declaration",
    )


def test_real_cards_cite_the_general_amendment_that_set_the_limit() -> None:
    row = {**_row(), "sum": ("5 000 000", "RUB")}
    assert_that(
        _verdicts("sum", _paper("512", row), Approved(_cover()))[0].remark().comment(),
        contains_string("ДС 23"),
        "Real cards do not cite the general amendment that set the limit",
    )


def test_real_cards_match_the_number_and_date_of_the_policy() -> None:
    assert_that(
        _statuses("policy", _paper("1", _row()), Approved(_cover())),
        equal_to(("match",)),
        "Real cards do not match the number and date of the policy",
    )


def test_real_cards_reject_another_policy_number() -> None:
    row = {**_row(), "policy": ("№ 9999X от 15.01.2026 г.",)}
    assert_that(
        _statuses("policy", _paper("1", row), Approved(_cover())),
        equal_to(("mismatch",)),
        "Real cards do not reject another policy number",
    )


def test_real_cards_ask_a_person_when_the_limit_is_absent() -> None:
    assert_that(
        _verdicts("sum", _paper("1", _row()), Approved(_profile({})))[0].reason().code(),
        equal_to("clause.absent"),
        "Real cards do not ask a person when the limit is absent",
    )


def test_real_cards_ask_a_person_when_no_term_is_in_force_on_the_start() -> None:
    row = {**_row(), "period_start": ("01.02.2020",), "period_end": ("05.02.2020",)}
    verdict = _verdicts("period_start", _paper("1", row), Approved(_cover()))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.absent")),
        "Real cards do not ask a person when no term is in force on the start",
    )


def test_real_cards_ask_a_person_about_a_sum_of_a_shipment_without_a_start() -> None:
    row = {key: value for key, value in _row().items() if key != "period_start"}
    verdict = _verdicts("sum", _paper("1", row), Approved(_cover()))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.absent")),
        "Real cards do not ask a person about a sum of a shipment without a start",
    )


def test_every_real_card_answers_about_a_shipment_without_a_start() -> None:
    row = {key: value for key, value in _row().items() if key != "period_start"}
    cards = Cards(Path(__file__).resolve().parents[2] / "cards", Mute()).cards("psg")
    assert_that(
        tuple(len(card.verdicts(_paper("1", row), Approved(_cover()))) for card in cards),
        equal_to((1,) * len(cards)),
        "Real cards do not answer about a shipment without a start",
    )


def _day() -> date:
    return date(2026, random.randint(1, 12), random.randint(1, 28))


def _wording(source: str, effective: date, **values: object) -> Wording:
    return Wording.model_validate(
        {"source": source, "effective": effective, "text": uuid.uuid4().hex, **values}
    )


def _profile(
    clauses: Mapping[str, tuple[Wording, ...]],
    number: str = "0000X",
    issued: date = date(2026, 1, 15),
    insurer: str = "ООО Страхователь",
    conditions: tuple[str, ...] = (),
) -> Profile:
    return Profile(
        number=number,
        issued=issued,
        insurer=insurer,
        clauses=dict(clauses),
        conditions=conditions,
    )


def _succession(day: date) -> Profile:
    return _profile(
        {
            "term": (
                _wording("ГП п. 6", day - timedelta(days=60)),
                _wording("ДС 1", day, amendment=1),
            )
        }
    )


def _rivals(day: date) -> Profile:
    start = day - timedelta(days=400)
    return _profile(
        {
            "transport": (
                _wording("ДС 4 п. 1", start, amendment=4),
                _wording("ДС 4 п. 2", start, amendment=4),
            )
        }
    )


def _cover() -> Profile:
    start = date(2026, 1, 15)
    return _profile(
        {
            "term": (
                _wording("ГП п. 6", start, dates=(start, date(2026, 12, 31))),
                _wording("ДС 1", date(2026, 3, 1), amendment=1, dates=(start, date(2028, 12, 31))),
            ),
            "limit": (
                _wording("ГП п. 12", start, amounts=(_rubles(1000000),)),
                _wording("ДС 20", date(2026, 5, 1), amendment=20, amounts=(_rubles(2000000),)),
                _wording("ДС 23", date(2026, 5, 1), amendment=23, amounts=(_rubles(3000000),)),
                _wording(
                    "ДС 25",
                    date(2026, 6, 1),
                    amendment=25,
                    scope=("70",),
                    amounts=(_rubles(9000000),),
                ),
            ),
        }
    )


def _rubles(value: int) -> Sum:
    return Sum(value=Decimal(value), currency="RUB")


def _row() -> Mapping[str, tuple[str, ...]]:
    return {
        "insurer": ("ООО Страхователь",),
        "policy": ("№ 0000X от 15.01.2026 г.",),
        "period_start": ("10.06.2026",),
        "period_end": ("20.06.2026",),
        "sum": ("500 000", "RUB"),
    }


def _paper(number: str, row: Mapping[str, tuple[str, ...]]) -> Paper:
    return Paper(number, "psg", (row,))


def _verdicts(field: str, paper: Paper, policy: Policy) -> tuple[Verdict, ...]:
    folder = Path(__file__).resolve().parents[2] / "cards"
    card = next(card for card in Cards(folder, Mute()).cards("psg") if card.field() == field)
    return card.verdicts(paper, policy)


def _statuses(field: str, paper: Paper, policy: Policy) -> tuple[str, ...]:
    return tuple(verdict.status().key() for verdict in _verdicts(field, paper, policy))


class _Trip:
    """Shipment of a declaration that starts on a given day."""

    __slots__ = ("_declaration", "_start")

    def __init__(self, declaration: str, start: date) -> None:
        self._declaration = declaration
        self._start = start

    def number(self) -> str:
        return self._declaration

    def declaration(self) -> str:
        return self._declaration

    def field(self, key: str) -> Blank:
        return Blank(key)

    def start(self) -> date:
        return self._start


class _Undated:
    """Shipment whose start date cannot be read."""

    __slots__ = ()

    def number(self) -> str:
        return "1"

    def declaration(self) -> str:
        return "1"

    def field(self, key: str) -> Blank:
        return Blank(key)

    def start(self) -> date:
        raise UnreadableError("Не найдена дата начала периода страхования")
