import random
import uuid
from pathlib import Path

import openpyxl
from hamcrest import (
    assert_that,
    contains_exactly,
    contains_inanyorder,
    contains_string,
    equal_to,
    has_length,
)

from app.domain.status import Match, Review
from tools.eval.fields import Deck
from tools.eval.gold import Folder
from tools.eval.pipeline import Checked, Kept, Parsed, Result, Staged, Uniform
from tools.eval.shelf import Shelf


def _declaration(path: Path, rows: int, amount: str = "") -> None:
    book = openpyxl.Workbook()
    sheet = book.worksheets[0]
    head: dict[tuple[int, int], str | int] = {
        (8, 1): "Декларация №",
        (8, 5): "035",
        (14, 1): "№ п/п",
        (14, 4): "Наименование груза",
        (14, 13): "Страховая сумма",
        (14, 14): "Валюта",
        (15, 2): "начало",
        (15, 3): "окончание",
    }
    for (row, column), value in head.items():
        sheet.cell(row=row, column=column, value=value)
    for index in range(1, rows + 1):
        sheet.cell(row=15 + index, column=1, value=index)
        sheet.cell(row=15 + index, column=2, value="14.09.2026")
        sheet.cell(row=15 + index, column=4, value=uuid.uuid4().hex)
        sheet.cell(row=15 + index, column=13, value=amount or None)
        sheet.cell(row=15 + index, column=14, value="RUB" if amount else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def _cards(folder: Path) -> Deck:
    folder.mkdir()
    (folder / "sum.yaml").write_text(
        "field: sum\nforms:\n  psg: {order: 13, title: Страховая сумма}\n", encoding="utf-8"
    )
    (folder / "cargo.yaml").write_text(
        "field: cargo\nforms:\n  psg: {order: 5, title: Наименование груза}\n", encoding="utf-8"
    )
    return Deck(folder)


def _rules(folder: Path) -> Path:
    folder.mkdir()
    comments = (
        'comments: {match: "Заполнено", mismatch: "Пусто", review: "Проверить", '
        'policy_missing: "Нет номера", policy_unreadable: "Номер не распознан", '
        'policy_unknown: "Полис не найден", policy_ambiguous: "Полисов несколько", '
        'policy_profile: "Профиль не собран"}
'
    )
    (folder / "cargo.yaml").write_text(
        "field: cargo\nforms:\n  psg: {order: 5, title: Наименование груза}\n"
        "subject: Груз\nclause: none\ncheck: filled\nrule: Поле заполнено\n"
        f"if_empty: mismatch\n{comments}status: draft\n",
        encoding="utf-8",
    )
    (folder / "sum.yaml").write_text(
        "field: sum\nforms:\n  psg: {order: 13, title: Страховая сумма}\n"
        "subject: Лимит\nclause: limit\ncheck: lte_limit\nrule: Не больше лимита\n"
        f"if_empty: mismatch\n{comments}status: draft\n",
        encoding="utf-8",
    )
    (folder / "policy.yaml").write_text(
        "field: policy\nforms:\n  psg: {order: 1, title: Номер ГП}\n"
        "subject: Номер\nclause: number\ncheck: exact\nrule: Номер совпадает\n"
        f"if_empty: review\n{comments}status: draft\n",
        encoding="utf-8",
    )
    return folder


def test_checked_answers_every_card_of_form_in_every_shipment(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 2)
    assert_that(
        [
            (verdict.place().shipment(), verdict.place().field())
            for verdict in Checked(Shelf(tmp_path / "real").catalog(), _rules(tmp_path / "cards"))
            .reconcile("35")
            .verdicts()
        ],
        contains_inanyorder(
            ("035/1", "policy"),
            ("035/2", "policy"),
            ("035/1", "cargo"),
            ("035/2", "cargo"),
            ("035/1", "sum"),
            ("035/2", "sum"),
        ),
        "Checked does not answer every card of the form in every shipment",
    )


def test_checked_decides_by_rule_cards(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 1)
    assert_that(
        {
            verdict.place().field(): verdict.reason().code()
            for verdict in Checked(Shelf(tmp_path / "real").catalog(), _rules(tmp_path / "cards"))
            .reconcile("35")
            .verdicts()
        },
        equal_to({"policy": "policy.empty", "cargo": "cargo.filled", "sum": "sum.empty"}),
        "Checked does not decide each field by its rule card",
    )


def test_checked_asks_person_where_no_policy_is_known(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 1, str(random.randint(1000, 90000)))
    assert_that(
        [
            verdict.reason().code()
            for verdict in Checked(Shelf(tmp_path / "real").catalog(), _rules(tmp_path / "cards"))
            .reconcile("35")
            .verdicts()
            if verdict.place().field() == "sum"
        ],
        contains_exactly("policy.unknown"),
        "Checked does not ask a person with the code policy.unknown where no policy is known",
    )


def test_checked_reports_no_model_calls_without_semantic_questions(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 3)
    assert_that(
        Checked(Shelf(tmp_path / "real").catalog(), _rules(tmp_path / "cards"))
        .reconcile("35")
        .calls(),
        equal_to(0),
        "Checked does not report zero model calls when no semantic question was asked",
    )


def test_checked_reports_missing_file_as_fault(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 1)
    assert_that(
        Checked(Shelf(tmp_path / "real").catalog(), _rules(tmp_path / "cards"))
        .reconcile("97")
        .faults()[0],
        contains_string("Разбор (AbsentError): Файл декларации 97 не найден"),
        "Checked does not report a missing declaration file as a fault",
    )


def test_checked_reports_broken_card_as_fault(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 1)
    folder = _rules(tmp_path / "cards")
    (folder / "sum.yaml").write_text("field: sum\nforms: [\n", encoding="utf-8")
    assert_that(
        Checked(Shelf(tmp_path / "real").catalog(), folder).reconcile("35").faults()[0],
        contains_string("Проверки (CardError): Карточка sum.yaml не читается как YAML"),
        "Checked does not report a broken rule card as a fault of the checks",
    )


def test_checked_times_parsing_and_checks(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 1)
    assert_that(
        list(
            Checked(Shelf(tmp_path / "real").catalog(), _rules(tmp_path / "cards"))
            .reconcile("35")
            .stages()
        ),
        contains_exactly("разбор", "проверки"),
        "Checked does not time parsing and checks as separate stages",
    )


def test_staged_keeps_stage_seconds() -> None:
    seconds = random.uniform(0.1, 5.0)
    assert_that(
        Staged(Result((), 0, ()), {"разбор": seconds}).stages(),
        equal_to({"разбор": seconds}),
        "Staged does not keep the seconds of its stages",
    )


def test_result_has_no_stages() -> None:
    assert_that(Result((), 0, ()).stages(), equal_to({}), "Result does not report empty stages")


def test_kept_declaration_answers_with_its_values() -> None:
    policy = uuid.uuid4().hex
    assert_that(
        Kept("035", "psg", policy, ()).policy(),
        equal_to(policy),
        "Kept declaration does not answer with the policy it was given",
    )


def test_uniform_answers_every_gold_place_of_declaration(tmp_path: Path) -> None:
    (tmp_path / "113.csv").write_text(
        "declaration,shipment,field,status,basis,note\n"
        "113,113/1,sum,match,fsc-ok,\n113,113/2,sum,mismatch,fsc-ok,\n114,114/1,sum,match,fsc-ok,\n",
        encoding="utf-8",
    )
    assert_that(
        Uniform(Folder(tmp_path), Review()).reconcile("113").verdicts(),
        has_length(2),
        "Uniform does not answer exactly the places of the declaration",
    )


def test_uniform_gives_its_status(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n",
        encoding="utf-8",
    )
    assert_that(
        Uniform(Folder(tmp_path), Match()).reconcile("97").verdicts()[0].status().key(),
        equal_to("match"),
        "Uniform does not give its status",
    )


def test_uniform_never_calls_model(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n",
        encoding="utf-8",
    )
    assert_that(
        Uniform(Folder(tmp_path), Review()).reconcile("97").calls(),
        equal_to(0),
        "Uniform does not report zero model calls",
    )


def test_result_keeps_model_calls() -> None:
    calls = random.randint(1, 50)
    assert_that(Result((), calls, ()).calls(), equal_to(calls), "Result does not keep model calls")


def test_result_keeps_faults() -> None:
    fault = uuid.uuid4().hex
    assert_that(Result((), 0, (fault,)).faults(), equal_to((fault,)), "Result does not keep faults")


def test_parsed_answers_every_field_of_every_shipment(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 3)
    assert_that(
        [
            (verdict.place().shipment(), verdict.place().field())
            for verdict in Parsed(Shelf(tmp_path / "real").catalog(), _cards(tmp_path / "cards"))
            .reconcile("35")
            .verdicts()
        ],
        contains_exactly(
            ("035/1", "cargo"),
            ("035/1", "sum"),
            ("035/2", "cargo"),
            ("035/2", "sum"),
            ("035/3", "cargo"),
            ("035/3", "sum"),
        ),
        "Parsed does not answer every field of the form in every shipment of the file",
    )


def test_parsed_answers_with_review_stub(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 1)
    assert_that(
        {
            verdict.status().key()
            for verdict in Parsed(Shelf(tmp_path / "real").catalog(), _cards(tmp_path / "cards"))
            .reconcile("35")
            .verdicts()
        },
        equal_to({"review"}),
        "Parsed does not answer with the review stub",
    )


def test_parsed_reports_missing_file_as_fault(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35.xlsx", 1)
    assert_that(
        Parsed(Shelf(tmp_path / "real").catalog(), _cards(tmp_path / "cards"))
        .reconcile("97")
        .faults()[0],
        contains_string("Файл декларации 97 не найден"),
        "Parsed does not report a missing declaration file as a fault",
    )
