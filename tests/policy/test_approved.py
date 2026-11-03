import random
import uuid
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from hamcrest import assert_that, contains_string, equal_to, has_length, raises

from app.domain.clause import Absent
from app.domain.errors import UnreadableError
from app.domain.field import Blank
from app.domain.money import Amount
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
    profile = _profile({"term": (_wording("ДС 1", day, amendment=1),)})
    assert_that(
        Approved(profile).clause("term", _Trip("1", day - timedelta(days=1))).reference(),
        equal_to(Absent("term").reference()),
        "Clause is not absent when no revision is in force yet",
    )


def test_policy_wording_applies_to_a_shipment_that_starts_before_its_date() -> None:
    day = _day()
    profile = _profile({"term": (_wording("ГП п. 6", day),)})
    assert_that(
        Approved(profile).clause("term", _Trip("1", day - timedelta(days=400))).reference(),
        equal_to("ГП п. 6"),
        "Policy wording does not apply to a shipment that starts before its date",
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


def test_revisions_of_equal_rank_name_both_sources_in_the_error() -> None:
    policy = Approved(_profile({"transport": _rivals()}))
    assert_that(
        lambda: policy.clause("transport", _Trip("1", _day())),
        raises(UnreadableError, "ДС 4 п. 1, ДС 4 п. 2"),
        "Revisions of equal rank do not name both sources in the error",
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


def test_amended_clause_cannot_be_chosen_for_a_shipment_without_a_start() -> None:
    policy = Approved(_profile({"limit": (_wording("ДС 1", _day(), amendment=1),)}))
    assert_that(
        lambda: policy.clause("limit", _Undated()),
        raises(UnreadableError),
        "Amended clause does not refuse a shipment without a start",
    )


def test_policy_wording_stays_readable_for_a_shipment_without_a_start() -> None:
    profile = _profile({"limit": (_wording("ГП п. 12", _day()),)})
    assert_that(
        Approved(profile).clause("limit", _Undated()).reference(),
        equal_to("ГП п. 12"),
        "Policy wording does not stay readable for a shipment without a start",
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


def test_real_cards_reject_a_shipment_that_starts_before_the_term() -> None:
    row = {**_row(), "period_start": ("01.02.2020",), "period_end": ("05.02.2020",)}
    verdict = _verdicts("period_start", _paper("1", row), Approved(_cover()))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("mismatch", "period_start.before_policy_start")),
        "Real cards do not reject a shipment that starts before the term",
    )


def test_real_cards_ask_a_person_about_an_amended_sum_of_a_shipment_without_a_start() -> None:
    row = {key: value for key, value in _row().items() if key != "period_start"}
    verdict = _verdicts("sum", _paper("1", row), Approved(_cover()))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person about an amended sum of a shipment without a start",
    )


def test_real_cards_check_a_sum_against_the_policy_limit_without_a_start() -> None:
    row = {key: value for key, value in _row().items() if key != "period_start"}
    limit = _wording("ГП п. 12", date(2026, 1, 15), amounts=(_rubles(1000000),))
    assert_that(
        _statuses("sum", _paper("1", row), Approved(_profile({"limit": (limit,)}))),
        equal_to(("match",)),
        "Real cards do not check a sum against the policy limit without a start",
    )


def test_real_cards_ask_a_person_about_a_carrier_when_the_risk_date_is_unknown() -> None:
    risk = _wording("ДС 2", date(2026, 3, 1), amendment=2)
    verdict = _verdicts(
        "carrier",
        Paper("1", "vertical", ({"carrier": ("ООО Ромашка",), "period": ("неизвестно",)},)),
        Approved(_profile({"carrier_risk": (risk,)})),
    )[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person about a carrier when the risk date is unknown",
    )


def test_real_cards_ask_a_person_about_a_carrier_when_the_risk_is_disputed() -> None:
    verdict = _verdicts(
        "carrier",
        Paper("1", "vertical", ({"carrier": ("ООО Ромашка",), "period": ("10.06.2026",)},)),
        Approved(_profile({"carrier_risk": _rivals()})),
    )[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person about a carrier when the risk is disputed",
    )


def test_real_cards_only_want_a_carrier_filled_when_the_profile_has_no_risk() -> None:
    assert_that(
        _statuses(
            "carrier",
            Paper("1", "vertical", ({"carrier": ("ООО Ромашка",), "period": ("неизвестно",)},)),
            Approved(_profile({})),
        ),
        equal_to(("match",)),
        "Real cards do not settle for a filled carrier when the profile has no risk",
    )


def test_real_cards_ask_a_person_about_an_end_past_the_term_when_extension_is_disputed() -> None:
    row = {**_row(), "period_end": ("15.02.2030",)}
    profile = _profile({**_cover().clauses, "term_extension": _rivals()})
    verdict = _verdicts("period_end", _paper("1", row), Approved(profile))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person about an end past the term when extension is disputed",
    )


def test_real_cards_match_an_end_inside_the_term_whatever_the_extension() -> None:
    profile = _profile({**_cover().clauses, "term_extension": _rivals()})
    assert_that(
        _statuses("period_end", _paper("1", _row()), Approved(profile)),
        equal_to(("match",)),
        "Real cards do not match an end inside the term whatever the extension",
    )


def test_real_cards_ask_a_person_about_cargo_when_the_exclusions_are_disputed() -> None:
    profile = _profile(
        {"object": (_wording("ГП п. 5", date(2026, 1, 15)),), "exclusions_cargo": _rivals()}
    )
    row = {**_row(), "cargo": ("Мебель",)}
    verdict = _verdicts("cargo", _paper("1", row), Approved(profile))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person about cargo when the exclusions are disputed",
    )


def test_real_cards_ask_a_person_when_the_accepted_values_are_disputed() -> None:
    profile = _profile({**_cover().clauses, "accepted.sum": _rivals()})
    verdict = _verdicts("sum", _paper("1", _row()), Approved(profile))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person when the accepted values are disputed",
    )


def test_every_real_card_answers_about_a_shipment_without_a_start() -> None:
    row = {key: value for key, value in _row().items() if key != "period_start"}
    cards = Cards(Path(__file__).resolve().parents[2] / "cards", Mute()).cards("psg")
    assert_that(
        tuple(len(card.verdicts(_paper("1", row), Approved(_cover()))) for card in cards),
        equal_to((1,) * len(cards)),
        "Real cards do not answer about a shipment without a start",
    )


def test_amendment_of_a_new_point_leaves_the_limit_of_another_point() -> None:
    day = _day()
    assert_that(
        tuple(
            amount.text()
            for amount in Approved(_points(day))
            .clause("limit", _Trip("1", day + timedelta(days=1)))
            .amounts()
        ),
        equal_to((Amount(Decimal(1000000), "RUB").text(),)),
        "Amendment of point 12.7 does not leave the limit of point 12.5",
    )


def test_clause_refers_to_every_point_in_force() -> None:
    day = _day()
    assert_that(
        Approved(_points(day)).clause("limit", _Trip("1", day + timedelta(days=1))).reference(),
        equal_to("ГП п. 12.5, ДС 27 п. 12.7"),
        "Clause does not refer to every point in force",
    )


def test_clause_gives_the_text_of_every_point_in_force_in_the_order_of_points() -> None:
    day = _day()
    late = _wording("ГП п. 5.10", day, point="5.10", text="десятый")
    early = _wording("ГП п. 5.9", day, point="5.9", text="девятый")
    assert_that(
        Approved(_profile({"object": (late, early)})).clause("object", _Trip("1", day)).text(),
        equal_to("девятый\nдесятый"),
        "Clause does not give the text of every point in the order of points",
    )


def test_clause_gives_the_entries_of_every_point_in_force_in_the_order_of_points() -> None:
    day = _day()
    late = _wording("ГП п. 12", day, point="12", entries=("второй",))
    early = _wording("ГП п. 9", day, point="9", entries=("первый",))
    assert_that(
        Approved(_profile({"object": (late, early)})).clause("object", _Trip("1", day)).entries(),
        equal_to(("первый", "второй")),
        "Clause does not give the entries of every point in the order of points",
    )


def test_clause_gives_the_dates_of_every_point_in_force_in_the_order_of_points() -> None:
    day = _day()
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    late = _wording("ГП п. 6.2", day, point="6.2", dates=(end,))
    early = _wording("ГП п. 6.1", day, point="6.1", dates=(start,))
    assert_that(
        Approved(_profile({"term": (late, early)})).clause("term", _Trip("1", day)).dates(),
        equal_to((start, end)),
        "Clause does not give the dates of every point in the order of points",
    )


def test_amendment_of_a_point_replaces_only_this_point() -> None:
    day = _day()
    profile = _profile(
        {
            "object": (
                _wording("ГП п. 5.1", day, point="5.1"),
                _wording("ГП п. 5.2", day, point="5.2"),
                _wording("ДС 3 п. 5.2", day, point="5.2", amendment=3),
            )
        }
    )
    assert_that(
        Approved(profile).clause("object", _Trip("1", day)).reference(),
        equal_to("ГП п. 5.1, ДС 3 п. 5.2"),
        "Amendment of a point does not replace only this point",
    )


def test_amendment_of_the_whole_point_after_one_of_a_nested_point_replaces_both() -> None:
    day = _day()
    assert_that(
        Approved(_nested(day)).clause("object", _Trip("1", day + timedelta(days=9))).reference(),
        equal_to("ДС 8 п. 5"),
        "Amendment of point 5 after one of point 5.2 does not replace both",
    )


def test_amendment_of_the_whole_point_waits_for_its_date_behind_the_nested_one() -> None:
    day = _day()
    assert_that(
        Approved(_nested(day)).clause("object", _Trip("1", day + timedelta(days=4))).reference(),
        equal_to("ГП п. 5, ДС 7 п. 5.2"),
        "Amendment of point 5 does not wait for its date behind the one of point 5.2",
    )


def test_amendment_of_a_nested_point_after_one_of_the_whole_point_stands_beside_it() -> None:
    day = _day()
    profile = _profile(
        {
            "object": (
                _wording("ДС 8 п. 5.2", day, point="5.2", amendment=8),
                _wording("ДС 7 п. 5", day - timedelta(days=1), point="5", amendment=7),
            )
        }
    )
    assert_that(
        Approved(profile).clause("object", _Trip("1", day)).reference(),
        equal_to("ДС 7 п. 5, ДС 8 п. 5.2"),
        "Amendment of point 5.2 after one of point 5 does not stand beside it",
    )


def test_amendment_without_a_point_replaces_every_point() -> None:
    day = _day()
    profile = _profile(
        {
            "object": (
                _wording("ГП п. 5.1", day, point="5.1"),
                _wording("ДС 3 п. 5.2", day, point="5.2", amendment=3),
                _wording("ДС 4", day, amendment=4),
            )
        }
    )
    assert_that(
        Approved(profile).clause("object", _Trip("1", day)).reference(),
        equal_to("ДС 4"),
        "Amendment without a point does not replace every point",
    )


def test_amendment_to_another_declaration_leaves_the_point_of_the_policy() -> None:
    day = _day()
    number = random.randint(100, 499)
    assert_that(
        Approved(_foreign(day, number))
        .clause("limit", _Trip(str(number + 500), day + timedelta(days=1)))
        .reference(),
        equal_to("ГП п. 12.5"),
        "Amendment to another declaration does not leave the point of the policy",
    )


def test_amendment_to_the_declaration_replaces_the_point_of_the_policy() -> None:
    day = _day()
    number = random.randint(100, 499)
    assert_that(
        Approved(_foreign(day, number))
        .clause("limit", _Trip(str(number), day + timedelta(days=1)))
        .reference(),
        equal_to("ДС 5 п. 12.5"),
        "Amendment to the declaration does not replace the point of the policy",
    )


def test_amendment_of_a_point_to_the_declaration_stays_under_a_later_general_one() -> None:
    day = _day()
    profile = _profile(
        {
            "object": (
                _wording("ДС 1 п. 5.2", day, point="5.2", amendment=1, scope=("77",)),
                _wording("ДС 2 п. 5", day + timedelta(days=1), point="5", amendment=2),
            )
        }
    )
    assert_that(
        Approved(profile).clause("object", _Trip("77", day + timedelta(days=2))).reference(),
        equal_to("ДС 2 п. 5, ДС 1 п. 5.2"),
        "Amendment of a point to the declaration does not stay under a later general one",
    )


def test_policy_wordings_of_different_points_are_not_rivals() -> None:
    day = _day()
    profile = _profile(
        {
            "object": (
                _wording("ГП п. 5", day, point="5"),
                _wording("ГП п. 5.2", day, point="5.2"),
                _wording("ГП п. 6", day, point="6"),
            )
        }
    )
    assert_that(
        Approved(profile).clause("object", _Trip("1", day)).reference(),
        equal_to("ГП п. 5, ГП п. 5.2, ГП п. 6"),
        "Policy wordings of different points do not stand side by side",
    )


def test_policy_wordings_of_one_point_cannot_be_chosen_between() -> None:
    day = _day()
    profile = _profile(
        {
            "object": (
                _wording("ГП п. 5.2", day, point="5.2"),
                _wording("ГП п. 5.2", day, point="5.2"),
            )
        }
    )
    assert_that(
        lambda: Approved(profile).clause("object", _Trip("1", day)),
        raises(UnreadableError, "ГП п. 5.2"),
        "Policy wordings of one point do not stop the choice",
    )


def test_rivals_on_a_point_do_not_matter_once_an_amendment_replaces_it() -> None:
    day = _day()
    profile = _profile(
        {
            "object": (
                _wording("ГП п. 5.2", day, point="5.2"),
                _wording("ГП п. 5.2", day, point="5.2"),
                _wording("ДС 1 п. 5.2", day, point="5.2", amendment=1),
            )
        }
    )
    assert_that(
        Approved(profile).clause("object", _Trip("1", day)).reference(),
        equal_to("ДС 1 п. 5.2"),
        "Rivals on a point do not give way to an amendment that replaced them",
    )


def test_point_that_is_no_number_stops_the_choice() -> None:
    day = _day()
    profile = _profile({"object": (_wording("ГП п. пять", day, point="пять"),)})
    assert_that(
        lambda: Approved(profile).clause("object", _Trip("1", day)),
        raises(UnreadableError, "пять"),
        "Point that is no number does not stop the choice",
    )


def test_amended_point_cannot_be_chosen_for_a_shipment_without_a_start() -> None:
    day = _day()
    assert_that(
        lambda: Approved(_points(day)).clause("limit", _Undated()),
        raises(UnreadableError),
        "Amended point does not refuse a shipment without a start",
    )


def test_limit_with_two_sums_of_one_currency_in_one_point_cannot_be_read() -> None:
    day = _day()
    wording = _wording("ГП п. 12.5", day, point="12.5", amounts=(_rubles(1), _rubles(2)))
    assert_that(
        lambda: Approved(_profile({"limit": (wording,)})).clause("limit", _Trip("1", day)),
        raises(UnreadableError, "ГП п. 12.5"),
        "Limit with two sums of one currency in one point does not stop the check",
    )


def test_limit_with_sums_of_one_currency_in_two_points_cannot_be_read() -> None:
    day = _day()
    assert_that(
        lambda: Approved(_aggregate(day)).clause("limit", _Trip("1", day)),
        raises(UnreadableError, "ГП п. 12.5, ДС 27 п. 12.7"),
        "Limit with sums of one currency in two points does not stop the check",
    )


def test_limit_may_state_the_same_sum_in_two_points() -> None:
    day = _day()
    profile = _profile(
        {
            "limit": (
                _wording("ГП п. 12.5", day, point="12.5", amounts=(_rubles(7),)),
                _wording("ГП п. 12.6", day, point="12.6", amounts=(_rubles(7),)),
            )
        }
    )
    assert_that(
        Approved(profile).clause("limit", _Trip("1", day)).amounts(),
        has_length(1),
        "Limit does not accept the same sum stated in two points",
    )


def test_limit_may_state_one_sum_in_each_currency() -> None:
    day = _day()
    dollars = Sum(value=Decimal(5), currency="USD")
    wording = _wording("ГП п. 12.5", day, point="12.5", amounts=(_rubles(7), dollars))
    assert_that(
        Approved(_profile({"limit": (wording,)})).clause("limit", _Trip("1", day)).amounts(),
        has_length(2),
        "Limit does not accept one sum in each currency",
    )


def test_replaced_sum_does_not_count_against_the_limit() -> None:
    day = _day()
    profile = _profile(
        {
            "limit": (
                _wording("ГП п. 12.5", day, point="12.5", amounts=(_rubles(7),)),
                _wording("ДС 1 п. 12.5", day, point="12.5", amendment=1, amounts=(_rubles(9),)),
            )
        }
    )
    assert_that(
        Approved(profile).clause("limit", _Trip("1", day)).amounts(),
        has_length(1),
        "Replaced sum does not leave the limit",
    )


def test_clause_of_another_key_may_state_several_sums_of_one_currency() -> None:
    day = _day()
    wording = _wording("ГП п. 5", day, point="5", amounts=(_rubles(1), _rubles(2)))
    assert_that(
        Approved(_profile({"object": (wording,)})).clause("object", _Trip("1", day)).amounts(),
        has_length(2),
        "Clause of another key does not accept several sums of one currency",
    )


def test_term_with_more_than_a_start_and_an_end_cannot_be_read() -> None:
    assert_that(
        lambda: Approved(_prolonged()).clause("term", _Trip("1", date(2026, 6, 1))),
        raises(UnreadableError, "ГП п. 6, ДС 3 п. 6.2"),
        "Term with more than a start and an end does not stop the check",
    )


def test_real_cards_check_a_sum_against_the_limit_beside_a_new_point() -> None:
    row = {**_row(), "sum": ("500 000", "RUB")}
    assert_that(
        _statuses("sum", _paper("1", row), Approved(_points(date(2026, 6, 1)))),
        equal_to(("match",)),
        "Real cards do not check a sum against the limit beside a new point",
    )


def test_real_cards_reject_a_sum_over_the_limit_beside_a_new_point() -> None:
    row = {**_row(), "sum": ("5 000 000", "RUB")}
    assert_that(
        _statuses("sum", _paper("1", row), Approved(_points(date(2026, 6, 1)))),
        equal_to(("mismatch",)),
        "Real cards do not reject a sum over the limit beside a new point",
    )


def test_real_cards_keep_the_policy_limit_beside_an_amendment_to_another_declaration() -> None:
    row = {**_row(), "sum": ("5 000 000", "RUB")}
    assert_that(
        _statuses("sum", _paper("1", row), Approved(_foreign(date(2026, 6, 1), 700))),
        equal_to(("mismatch",)),
        "Real cards do not keep the policy limit beside an amendment to another declaration",
    )


def test_real_cards_apply_the_limit_of_an_amendment_to_the_point_for_its_declaration() -> None:
    row = {**_row(), "sum": ("5 000 000", "RUB")}
    assert_that(
        _statuses("sum", _paper("700", row), Approved(_foreign(date(2026, 6, 1), 700))),
        equal_to(("match",)),
        "Real cards do not apply the limit of an amendment to the point for its declaration",
    )


def test_real_cards_ask_a_person_when_the_limit_holds_an_aggregate_sum() -> None:
    verdict = _verdicts("sum", _paper("1", _row()), Approved(_aggregate(date(2026, 6, 1))))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person when the limit holds an aggregate sum",
    )


def test_real_cards_ask_a_person_when_the_term_is_split_between_points() -> None:
    verdict = _verdicts("period_end", _paper("1", _row()), Approved(_prolonged()))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.unsettled")),
        "Real cards do not ask a person when the term is split between points",
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


def _rivals() -> tuple[Wording, ...]:
    return (
        _wording("ДС 4 п. 1", date(2020, 1, 1), amendment=4),
        _wording("ДС 4 п. 2", date(2020, 1, 1), amendment=4),
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


def _points(day: date) -> Profile:
    return _profile(
        {
            "limit": (
                _wording("ГП п. 12.5", day, point="12.5", amounts=(_rubles(1000000),)),
                _wording("ДС 27 п. 12.7", day, point="12.7", amendment=27),
            )
        }
    )


def _aggregate(day: date) -> Profile:
    return _profile(
        {
            "limit": (
                _wording("ДС 27 п. 12.7", day, point="12.7", amendment=27, amounts=(_rubles(9),)),
                _wording("ГП п. 12.5", day, point="12.5", amounts=(_rubles(1000000),)),
            )
        }
    )


def _foreign(day: date, number: int) -> Profile:
    return _profile(
        {
            "limit": (
                _wording("ГП п. 12.5", day, point="12.5", amounts=(_rubles(1000000),)),
                _wording(
                    "ДС 5 п. 12.5",
                    day,
                    point="12.5",
                    amendment=5,
                    scope=(str(number),),
                    amounts=(_rubles(9000000),),
                ),
            )
        }
    )


def _nested(day: date) -> Profile:
    return _profile(
        {
            "object": (
                _wording("ГП п. 5", day - timedelta(days=30), point="5"),
                _wording("ДС 7 п. 5.2", day, point="5.2", amendment=7),
                _wording("ДС 8 п. 5", day + timedelta(days=5), point="5", amendment=8),
            )
        }
    )


def _prolonged() -> Profile:
    start, end = date(2026, 1, 15), date(2026, 12, 31)
    return _profile(
        {
            "term": (
                _wording("ГП п. 6", start, point="6", dates=(start, end)),
                _wording("ДС 3 п. 6.2", start, point="6.2", amendment=3, dates=(date(2028, 1, 1),)),
            )
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
    cards = Cards(folder, Mute()).cards(paper.form())
    card = next(card for card in cards if card.field() == field)
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
