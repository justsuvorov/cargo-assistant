import random
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path

from hamcrest import assert_that, contains_string, equal_to, has_item, raises

from app.domain.money import Amount
from app.domain.policy import Policy, Unbound, Vacant
from app.domain.status import Match
from app.rules.cards import Cards
from app.rules.errors import CardError
from tests.rules.fakes import (
    Doubtful,
    Listening,
    Mute,
    Oracle,
    Paper,
    Profile,
    Text,
    Unsettled,
)


def _folder() -> Path:
    return Path(__file__).resolve().parents[2] / "cards"


def _card(folder: Path, name: str, lines: Mapping[str, str]) -> Path:
    body = {
        "field": name,
        "forms": "{vertical: {order: 1, title: Поле}}",
        "subject": "Пункт",
        "clause": "none",
        "check": "filled",
        "rule": "Поле заполнено",
        "if_empty": "mismatch",
        "comments": '{match: "Заполнено", mismatch: "Пусто", review: ""}',
        "status": "draft",
        **lines,
    }
    (folder / f"{name}.yaml").write_text(
        "".join(f"{key}: {value}\n" for key, value in body.items()), encoding="utf-8"
    )
    return folder


def _policy() -> Policy:
    return Profile(
        {
            "insurer": Text("ГП, преамбула", "ООО «Тест»"),
            "number": Text("ГП, преамбула", "0000T00GR0000", dates=(date(2026, 8, 26),)),
            "term": Text("ГП п. 6", "срок", dates=(date(2026, 1, 1), date(2026, 12, 31))),
            "limit": Text("ГП п. 12", "лимит", amounts=(Amount(Decimal(900000000), "RUB"),)),
            "object": Text("ГП п. 5", "грузы"),
            "transport": Text("ГП п. 8", "автомобильным, авиационным транспортом"),
            "territory": Text("ГП п. 9", "РФ"),
        }
    )


def _row(cargo: str, transport: str, transshipment: str) -> Mapping[str, tuple[str, ...]]:
    return {
        "insurer": ("ООО «Тест»",),
        "policy": ("№ 0000T00GR0000 от 26.08.2026 г.",),
        "period_start": ("14.09.2026",),
        "period_end": ("30.09.2026",),
        "cargo": (cargo,),
        "beneficiary": ("ООО «Получатель»",),
        "document_number": ("13444-2/Р",),
        "document_date": ("14.09.2026",),
        "transport": (transport,),
        "departure": ("г. Первый",),
        "transshipment": (transshipment,) if transshipment else (),
        "destination": ("г. Второй",),
        "sum": ("1 000 000", "RUB"),
    }


def _codes(paper: Paper, policy: Policy, field: str) -> tuple[str, ...]:
    card = next(
        card for card in Cards(_folder(), Oracle(Match())).cards("psg") if card.field() == field
    )
    return tuple(verdict.reason().code() for verdict in card.verdicts(paper, policy))


def test_vertical_form_gets_fifteen_cards_in_order() -> None:
    assert_that(
        tuple(card.field() for card in Cards(_folder(), Mute()).cards("vertical")),
        equal_to(
            (
                "insurer",
                "policy",
                "cargo",
                "packaging",
                "beneficiary",
                "sum",
                "transport",
                "departure",
                "transshipment",
                "destination",
                "period",
                "document",
                "carrier",
                "sealing",
                "other",
            )
        ),
        "Cards does not give the fifteen vertical cards in the order of the form",
    )


def test_table_form_gets_thirteen_cards_without_carrier() -> None:
    assert_that(
        tuple(card.field() for card in Cards(_folder(), Mute()).cards("psg")),
        equal_to(
            (
                "insurer",
                "policy",
                "period_start",
                "period_end",
                "cargo",
                "beneficiary",
                "document_number",
                "document_date",
                "transport",
                "departure",
                "transshipment",
                "destination",
                "sum",
            )
        ),
        "Cards does not give the thirteen table cards in the order of the form",
    )


def test_draft_card_is_loaded(tmp_path: Path) -> None:
    assert_that(
        len(Cards(_card(tmp_path, "packaging", {"status": "draft"}), Mute()).cards("vertical")),
        equal_to(1),
        "Cards does not load a draft card",
    )


def test_unknown_check_fails_loudly(tmp_path: Path) -> None:
    assert_that(
        lambda: Cards(_card(tmp_path, "packaging", {"check": "guess"}), Mute()).cards("vertical"),
        raises(CardError, "packaging.yaml"),
        "Cards does not reject an unknown check",
    )


def test_broken_yaml_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "other.yaml").write_text("field: [other\nforms: {", encoding="utf-8")
    assert_that(
        lambda: Cards(tmp_path, Mute()).cards("vertical"),
        raises(CardError, "YAML"),
        "Cards does not reject a broken YAML file",
    )


def test_card_without_review_template_fails_loudly(tmp_path: Path) -> None:
    folder = _card(tmp_path, "sealing", {"comments": '{match: "Да", mismatch: "Нет"}'})
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "review"),
        "Cards does not reject a card without a review template",
    )


def test_unknown_placeholder_fails_loudly(tmp_path: Path) -> None:
    folder = _card(
        tmp_path, "sealing", {"comments": '{match: "{client}", mismatch: "", review: ""}'}
    )
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "client"),
        "Cards does not reject an unknown placeholder",
    )


def test_card_of_another_field_than_its_file_fails_loudly(tmp_path: Path) -> None:
    folder = _card(tmp_path, "sealing", {"field": "other"})
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "sealing.yaml"),
        "Cards does not reject a card whose field differs from its file name",
    )


def test_two_cards_on_one_row_fail_loudly(tmp_path: Path) -> None:
    folder = _card(_card(tmp_path, "sealing", {}), "other", {})
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "order"),
        "Cards does not reject two cards with the same order",
    )


def test_check_that_needs_a_clause_without_one_fails_loudly(tmp_path: Path) -> None:
    folder = _card(tmp_path, "insurer", {"check": "fuzzy"})
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "clause"),
        "Cards does not reject a fuzzy card without a clause",
    )


def test_condition_on_a_field_without_modes_fails_loudly(tmp_path: Path) -> None:
    folder = _card(
        tmp_path,
        "transshipment",
        {"check": "conditional", "params": "{when: transport.mixed, else: match}"},
    )
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "modes"),
        "Cards does not reject a condition on a card without modes",
    )


def test_form_without_cards_fails_loudly(tmp_path: Path) -> None:
    assert_that(
        lambda: Cards(_card(tmp_path, "sealing", {}), Mute()).cards("psg"),
        raises(CardError, "psg"),
        "Cards does not fail for a form without cards",
    )


def test_same_values_in_different_rows_get_the_same_result() -> None:
    row = _row("Бумага", "Авто", "")
    paper = Paper("16", "psg", (row, _row("Мех", "Авиа", "нет"), row))
    verdicts = tuple(
        verdict
        for card in Cards(_folder(), Oracle(Match())).cards("psg")
        for verdict in card.verdicts(paper, _policy())
    )
    assert_that(
        tuple(
            (verdict.status().key(), verdict.reason().code(), verdict.remark().comment())
            for verdict in verdicts
            if verdict.place().shipment() == "16/1"
        ),
        equal_to(
            tuple(
                (verdict.status().key(), verdict.reason().code(), verdict.remark().comment())
                for verdict in verdicts
                if verdict.place().shipment() == "16/3"
            )
        ),
        "Cards does not give the same result to the same values in different rows",
    )


def _calls(count: int) -> int:
    oracle = Oracle(Match())
    paper = Paper(
        "17",
        "psg",
        tuple(_row(random.choice(("Бумага", "Мех")), "Авто", "") for _ in range(count)),
    )
    for card in Cards(_folder(), oracle).cards("psg"):
        card.verdicts(paper, _policy())
    return len(oracle.batches)


def _party(field: str, text: str) -> tuple[str, str]:
    card = next(
        card for card in Cards(_folder(), Mute()).cards("vertical") if card.field() == field
    )
    verdict = card.verdicts(
        Paper("23", "vertical", ({field: (text,), "period": ("14.09.2026",)},)), Vacant("1")
    )[0]
    return (verdict.status().key(), verdict.reason().code())


def test_model_calls_do_not_grow_with_rows() -> None:
    assert_that(
        (_calls(2), _calls(40)),
        equal_to((3, 3)),
        "Cards does not keep one model call per semantic card whatever the number of rows",
    )


def test_mixed_carriage_without_transshipment_is_a_mismatch() -> None:
    assert_that(
        _codes(
            Paper("18", "psg", (_row("Бумага", "Авто+авиа+авто", "нет"),)),
            _policy(),
            "transshipment",
        ),
        equal_to(("transshipment.empty",)),
        "Cards does not require a transshipment point in a mixed carriage",
    )


def test_road_carriage_without_transshipment_matches() -> None:
    assert_that(
        _codes(Paper("18", "psg", (_row("Бумага", "Авто", ""),)), _policy(), "transshipment"),
        equal_to(("transshipment.otherwise",)),
        "Cards does not let a road carriage skip the transshipment point",
    )


def test_blank_word_in_beneficiary_is_a_mismatch() -> None:
    row = {**_row("Бумага", "Авто", ""), "beneficiary": ("нет",)}
    assert_that(
        _codes(Paper("19", "psg", (row,)), Vacant("1"), "beneficiary"),
        equal_to(("beneficiary.empty",)),
        "Cards does not reject the blank word «нет» in the beneficiary",
    )


def test_sum_in_another_currency_names_the_declared_amount() -> None:
    row = {**_row("Бумага", "Авто", ""), "sum": ("7 492 870", "юаней")}
    card = next(card for card in Cards(_folder(), Mute()).cards("psg") if card.field() == "sum")
    assert_that(
        card.verdicts(Paper("20", "psg", (row,)), _policy())[0].remark().comment(),
        contains_string("7 492 870,00 CNY"),
        "Cards does not name the declared amount when the currencies differ",
    )


def test_carrier_is_checked_against_the_list_when_the_risk_is_included() -> None:
    policy = Profile(
        {
            "carrier_risk": Text("ГП п. 3.4.28", "риск"),
            "carriers": Text("Приложение 3", entries=("ООО «Перевозчик»",)),
        }
    )
    card = next(
        card for card in Cards(_folder(), Mute()).cards("vertical") if card.field() == "carrier"
    )
    assert_that(
        card.verdicts(
            Paper("21", "vertical", ({"carrier": ("ООО «Другой»",), "period": ("14.09.2026",)},)),
            policy,
        )[0]
        .reason()
        .code(),
        equal_to("carrier.different"),
        "Cards does not check the carrier against the list when the risk is included",
    )


def test_carrier_without_the_risk_is_only_filled() -> None:
    card = next(
        card for card in Cards(_folder(), Mute()).cards("vertical") if card.field() == "carrier"
    )
    assert_that(
        card.verdicts(
            Paper("22", "vertical", ({"carrier": ("ООО «Другой»",), "period": ("14.09.2026",)},)),
            Vacant("1"),
        )[0]
        .reason()
        .code(),
        equal_to("carrier.filled"),
        "Cards does not check only the filling of the carrier without the risk",
    )


def test_special_conditions_accept_a_transport_value() -> None:
    policy = Profile(
        {
            "transport": Text("ГП п. 8", "автомобильным транспортом"),
            "accepted.transport": Text("Особые условия", entries=("в соответствии с п.8 ГП",)),
        }
    )
    row = {
        **_row("Бумага", "в соответствии с п.8 ГП", ""),
        "transport": ("В соответствии с п.8 ГП",),
    }
    assert_that(
        _codes(Paper("23", "psg", (row,)), policy, "transport"),
        has_item("transport.accepted"),
        "Cards does not accept a transport value from the special conditions",
    )


def test_card_asks_a_person_when_the_policy_cannot_choose_a_revision() -> None:
    assert_that(
        _codes(
            Paper("1", "psg", (_row("Мебель", "авто", ""),)),
            Doubtful("редакция не выбрана"),
            "sum",
        ),
        equal_to(("clause.unsettled",)),
        "Card does not ask a person when the policy cannot choose a revision",
    )


def test_vertical_period_ending_before_its_start_is_a_mismatch_without_a_profile() -> None:
    card = next(
        card for card in Cards(_folder(), Mute()).cards("vertical") if card.field() == "period"
    )
    verdict = card.verdicts(
        Paper("24", "vertical", ({"period": ("с 12.09.2026 по 12.08.2026",)},)), Vacant("1")
    )[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code(), verdict.remark().comment()),
        equal_to(("mismatch", "period.end_before_start", "Дата окончания раньше даты начала")),
        "Cards does not reject a vertical period ending before its start without a profile",
    )


def test_table_end_before_the_row_start_is_a_mismatch_when_the_term_is_unsettled() -> None:
    row = {
        **_row("Paper", "Road", ""),
        "period_start": ("12.09.2026",),
        "period_end": ("12.08.2026",),
    }
    card = next(
        card for card in Cards(_folder(), Mute()).cards("psg") if card.field() == "period_end"
    )
    verdict = card.verdicts(Paper("25", "psg", (row,)), Unsettled("term", "две редакции"))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("mismatch", "period_end.end_before_start")),
        "Cards does not reject a table end before the row start when the term is unsettled",
    )


def test_date_range_with_an_end_without_its_order_status_fails_loudly(tmp_path: Path) -> None:
    folder = _card(
        tmp_path,
        "period",
        {"clause": "term", "check": "date_range", "params": "{bounds: [start, end]}"},
    )
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "end_before_start"),
        "Cards does not reject a date range with an end but without the status of disorder",
    )


def test_foreign_legal_form_of_a_beneficiary_matches() -> None:
    assert_that(
        _party("beneficiary", f"{random.choice(('Neva', 'Ural'))} Trading LLC"),
        equal_to(("match", "beneficiary.foreign")),
        "Cards does not accept a foreign legal form of the beneficiary",
    )


def test_cyrillic_foreign_legal_form_of_a_carrier_matches() -> None:
    assert_that(
        _party("carrier", "ТОО «Степной транзит»"),
        equal_to(("match", "carrier.foreign")),
        "Cards does not accept a foreign legal form of the carrier written in Cyrillic",
    )


def test_foreign_legal_form_of_a_carrier_matches() -> None:
    assert_that(
        _party("carrier", f"Shenzhen {random.randint(1, 9)} Freight Forwarding Co., Ltd"),
        equal_to(("match", "carrier.foreign")),
        "Cards does not accept a foreign legal form of the carrier",
    )


def test_english_legal_form_fused_with_an_address_needs_a_person() -> None:
    assert_that(
        _party("beneficiary", "NORTH TECHNOLOGIES LLCAddress: Moscow, Lenina St., 1"),
        equal_to(("review", "beneficiary.fused")),
        "Cards does not ask for review of a legal form fused with the next word",
    )


def test_russian_legal_form_fused_with_a_name_needs_a_person() -> None:
    assert_that(
        _party("carrier", "ОООТранспортная компания, г. Тверь"),
        equal_to(("review", "carrier.fused")),
        "Cards does not ask for review of a Russian legal form fused with the name",
    )


def test_beneficiary_without_legal_form_is_a_mismatch() -> None:
    assert_that(
        (_party("beneficiary", "СЕВЕР"), _party("beneficiary", "SEVER TRADE")),
        equal_to((("mismatch", "beneficiary.unformed"), ("mismatch", "beneficiary.latin"))),
        "Cards does not reject a beneficiary without a legal form",
    )


def test_foreign_carrier_without_legal_form_matches() -> None:
    assert_that(
        _party("carrier", "NORTHERN AIRLINES-NRA"),
        equal_to(("match", "carrier.latin")),
        "Cards does not accept a carrier without a legal form written only in Latin letters",
    )


def test_resident_carrier_without_legal_form_needs_a_person() -> None:
    assert_that(
        _party("carrier", "Транспортная компания Север"),
        equal_to(("review", "carrier.unformed")),
        "Cards does not ask for review of a carrier without a legal form in Cyrillic",
    )


def test_party_card_without_statuses_of_its_cases_fails_loudly(tmp_path: Path) -> None:
    folder = _card(tmp_path, "beneficiary", {"params": '{shape: party, legal_forms: ["ООО"]}'})
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "party"),
        "Cards does not reject a party card without the statuses of its cases",
    )


def _full(form: str) -> Paper:
    return Paper(
        "25",
        form,
        (
            {
                **_row("Бумага", "Авто+авиа", "г. Третий"),
                "period": ("с 14.09.2026 по 30.09.2026",),
                "document": ("CMR 1 от 14.09.2026",),
                "carrier": ("ООО «Перевозчик»",),
                "packaging": ("Коробки",),
                "sealing": ("Пломба 1",),
                "other": ("Без особенностей",),
            },
        ),
    )


def _asking(form: str) -> tuple[str, ...]:
    asking = []
    for card in Cards(_folder(), Mute()).cards(form):
        listening = Listening()
        card.verdicts(_full(form), listening)
        if any(not key.startswith("accepted.") for key in listening.keys):
            asking.append(card.field())
    return tuple(asking)


def _unbound(form: str, reason: str) -> dict[str, tuple[tuple[str, str], ...]]:
    return {
        card.field(): tuple(
            (verdict.status().key(), verdict.reason().code())
            for verdict in card.verdicts(_full(form), Unbound(reason, "1"))
        )
        for card in Cards(_folder(), Oracle(Match())).cards(form)
    }


def test_card_with_a_policy_clause_never_matches_a_declaration_bound_to_no_policy() -> None:
    reasons = ("policy_missing", "policy_unreadable", "policy_unknown", "policy_ambiguous")
    matched = tuple(
        (form, reason, field)
        for form in ("vertical", "psg")
        for reason in reasons
        for field, found in _unbound(form, reason).items()
        if field in _asking(form) and any(status == "match" for status, _ in found)
    )
    assert_that(
        (bool(_asking("vertical")), bool(_asking("psg")), matched),
        equal_to((True, True, ())),
        "Card that asks a policy clause matches a declaration bound to no policy",
    )


def test_card_with_a_policy_clause_names_the_binding_for_a_declaration_bound_to_no_policy() -> None:
    reason = random.choice(("missing", "unreadable", "unknown", "ambiguous"))
    found = _unbound("vertical", f"policy_{reason}")
    assert_that(
        {found[field] for field in _asking("vertical")},
        equal_to({(("review", f"policy.{reason}"),)}),
        "Card that asks a policy clause does not name the binding of an unbound declaration",
    )


def test_card_without_a_policy_clause_works_as_before_for_a_declaration_bound_to_no_policy() -> (
    None
):
    unbound = _unbound("vertical", "policy_unknown")
    assert_that(
        {
            card.field(): tuple(
                (verdict.status().key(), verdict.reason().code())
                for verdict in card.verdicts(_full("vertical"), Vacant("1"))
            )
            for card in Cards(_folder(), Mute()).cards("vertical")
            if card.field() not in _asking("vertical")
        },
        equal_to(
            {field: found for field, found in unbound.items() if field not in _asking("vertical")}
        ),
        "Card without a policy clause does not work as before for an unbound declaration",
    )


def test_comment_of_an_unbound_declaration_comes_from_the_card() -> None:
    card = next(card for card in Cards(_folder(), Mute()).cards("psg") if card.field() == "sum")
    assert_that(
        len(
            {
                card.verdicts(_full("psg"), Unbound(reason, "1"))[0].remark().comment()
                for reason in (
                    "policy_missing",
                    "policy_unreadable",
                    "policy_unknown",
                    "policy_ambiguous",
                )
            }
            - {""}
        ),
        equal_to(4),
        "Card does not give its own comment for each reason of a missing binding",
    )


def test_card_with_a_clause_without_comments_of_the_binding_fails_loudly(tmp_path: Path) -> None:
    folder = _card(tmp_path, "insurer", {"clause": "insurer", "check": "fuzzy"})
    assert_that(
        lambda: Cards(folder, Mute()).cards("vertical"),
        raises(CardError, "policy_unknown"),
        "Cards does not reject a card with a clause but without comments for an unbound policy",
    )
