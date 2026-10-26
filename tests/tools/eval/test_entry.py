import uuid

from hamcrest import assert_that, contains_exactly, equal_to

from tools.eval.entry import Dropped, Open, Settled
from tools.eval.sheet import Line


def test_settled_entry_gives_gold_cells() -> None:
    note = uuid.uuid4().hex
    assert_that(
        Settled(
            Line("113", ("113/2", "Сумма", "", "совпадает", "", "верно")),
            "sum",
            ("match", "fsc-ok", note),
        ).cells(),
        contains_exactly("113", "113/2", "sum", "match", "fsc-ok", note),
        "Settled entry does not give the gold cells",
    )


def test_open_entry_is_question() -> None:
    assert_that(
        Open(Line("35", ("35", "Груз", "", "совпадает", "", "x")), "cargo", "why", "").kind(),
        equal_to("question"),
        "Open entry does not report itself as a question",
    )


def test_open_entry_quotes_remark() -> None:
    remark = uuid.uuid4().hex
    assert_that(
        Open(Line("35", ("35", "Груз", "", "совпадает", "", remark)), "cargo", "y", "").cells()[4],
        equal_to(remark),
        "Open entry does not quote the remark",
    )


def test_open_entry_without_remark_is_unmarked() -> None:
    assert_that(
        Open(Line("114", ("114/1", "Груз", "", "совпадает", "", "")), "cargo", "y", "").marked(),
        equal_to(False),
        "Open entry does not see that the row has no remark",
    )


def test_dropped_entry_is_exclusion() -> None:
    assert_that(
        Dropped(
            Line("35", ("35", "Пломбирование", "", "совпадает", "", "x")), "sealing", "D-14"
        ).kind(),
        equal_to("excluded"),
        "Dropped entry does not report itself as an exclusion",
    )
