import uuid

from hamcrest import assert_that, contains_exactly, equal_to, raises

from tools.eval.fields import Key
from tools.eval.rulings import Asked, Decided, Rulings, Silent
from tools.eval.sheet import Line


def test_silent_ruling_lets_target_decide() -> None:
    assert_that(
        Silent()
        .entry(Line("97", ("97", "Сумма", "", "совпадает", "", "верно")), Key("sum"))
        .kind(),
        equal_to("gold"),
        "Silent ruling does not let the target decide",
    )


def test_decided_ruling_gives_expected_status() -> None:
    assert_that(
        Decided("review", "D-22", "валюта")
        .entry(Line("70", ("70", "Сумма", "", "не совпадает", "", "x")), Key("sum"))
        .cells(),
        equal_to(("70", "70", "sum", "review", "D-22", "валюта")),
        "Decided ruling does not give the expected status",
    )


def test_decided_ruling_refuses_unknown_status() -> None:
    assert_that(
        lambda: Decided(uuid.uuid4().hex, "fsc-note", "").entry(
            Line("70", ("70", "Сумма", "", "совпадает", "", "x")), Key("sum")
        ),
        raises(ValueError),
        "Decided ruling does not refuse an unknown status",
    )


def test_asked_ruling_offers_answer() -> None:
    offer = uuid.uuid4().hex
    assert_that(
        Asked("why", offer)
        .entry(Line("35", ("35", "Груз", "", "совпадает", "", "x")), Key("cargo"))
        .cells()[6],
        equal_to(offer),
        "Asked ruling does not offer its answer",
    )


def test_rulings_find_written_ruling() -> None:
    assert_that(
        Rulings(({"shipment": "97", "field": "sum", "status": "mismatch", "basis": "D-23"},), {})
        .ruling("97", "sum")
        .entry(Line("97", ("97", "Сумма", "", "совпадает", "", "x")), Key("sum"))
        .cells()[3],
        equal_to("mismatch"),
        "Rulings do not find a written ruling",
    )


def test_rulings_ask_about_broken_shipment() -> None:
    reason = uuid.uuid4().hex
    assert_that(
        Rulings((), {"114/4": reason})
        .ruling("114/4", "sum")
        .entry(Line("114", ("114/4", "Сумма", "", "совпадает", "", "верно")), Key("sum"))
        .cells()[5],
        equal_to(reason),
        "Rulings do not ask about a broken shipment row",
    )


def test_rulings_refuse_two_rulings_for_one_place() -> None:
    case = {"shipment": "97", "field": "sum", "ask": "x"}
    assert_that(
        lambda: Rulings((case, case), {}).ruling("97", "sum"),
        raises(ValueError),
        "Rulings do not refuse two rulings for one place",
    )


def test_rulings_report_ruling_without_mark() -> None:
    assert_that(
        Rulings(
            (
                {"shipment": "97", "field": "sum", "ask": "x"},
                {"shipment": "35", "field": "cargo", "ask": "y"},
            ),
            {},
        ).unused(frozenset({("97", "sum")})),
        contains_exactly("35 × cargo"),
        "Rulings do not report a ruling that matches no mark",
    )
