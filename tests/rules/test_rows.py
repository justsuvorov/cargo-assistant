import random

from hamcrest import assert_that, equal_to

from app.domain.status import Match, Mismatch
from app.rules.probe import Constant, Grounded
from app.rules.rows import Rowwise
from app.rules.semantic import Asking
from app.rules.wording import Comments
from tests.rules.fakes import Mute, Oracle, Paper, Profile, Text


def _rows(count: int) -> Paper:
    return Paper(
        "14",
        "psg",
        tuple(
            {"cargo": (random.choice(("Бумага", "Мех", "Продукты, Бумага")),)} for _ in range(count)
        ),
    )


def test_semantic_card_asks_one_batch_whatever_the_number_of_rows() -> None:
    oracle = Oracle(Match())
    Rowwise(
        "cargo",
        Grounded("object", Asking((), "правило")),
        Comments({}),
        oracle,
    ).verdicts(_rows(random.randint(20, 60)), Profile({"object": Text("ГП п. 5", "грузы")}))
    assert_that(
        (len(oracle.batches), len(oracle.batches[0]) <= 3),
        equal_to((1, True)),
        "Rowwise does not ask the distinct values of all rows in one batch",
    )


def test_same_values_get_the_same_verdict() -> None:
    verdicts = Rowwise(
        "cargo", Grounded("object", Asking((), "")), Comments({}), Oracle(Mismatch())
    ).verdicts(
        Paper("15", "psg", ({"cargo": ("Мех",)}, {"cargo": ("Бумага",)}, {"cargo": ("Мех",)})),
        Profile({"object": Text("ГП п. 5", "грузы")}),
    )
    assert_that(
        (verdicts[0].remark().comment(), verdicts[2].remark().comment()),
        equal_to(("оценено: Мех", "оценено: Мех")),
        "Rowwise does not give the same verdict to the same value",
    )


def test_each_shipment_gets_its_own_place() -> None:
    assert_that(
        tuple(
            verdict.place().shipment()
            for verdict in Rowwise(
                "cargo", Grounded("object", Asking((), "")), Comments({}), Oracle(Match())
            ).verdicts(
                Paper("15", "psg", ({"cargo": ("Мех",)}, {"cargo": ("Мех",)})),
                Profile({"object": Text("ГП п. 5", "грузы")}),
            )
        ),
        equal_to(("15/1", "15/2")),
        "Rowwise does not place a shared answer in every shipment",
    )


def test_code_check_never_asks_the_semantic_judge() -> None:
    assert_that(
        len(
            Rowwise(
                "packaging", Constant(Match(), "filled"), Comments({"match": ""}), Mute()
            ).verdicts(_rows(5), Profile({}))
        ),
        equal_to(5),
        "Rowwise does not check every row without the semantic judge",
    )
