import random
import uuid

from hamcrest import assert_that, contains_exactly, equal_to

from app.domain.clause import Absent
from app.domain.place import Spot
from app.domain.semantics import Inquiry
from tools.eval.semantics import Doubt


def _questions(count: int) -> tuple[Inquiry, ...]:
    return tuple(
        Inquiry(Spot(f"35/{index}", "cargo"), uuid.uuid4().hex, Absent("object"), "правило")
        for index in range(1, count + 1)
    )


def test_doubt_answers_every_question_with_review() -> None:
    assert_that(
        {verdict.status().key() for verdict in Doubt().verdicts(_questions(random.randint(1, 9)))},
        equal_to({"review"}),
        "Doubt does not answer every question with review",
    )


def test_doubt_answers_in_place_of_each_question() -> None:
    assert_that(
        [verdict.place().shipment() for verdict in Doubt().verdicts(_questions(3))],
        contains_exactly("35/1", "35/2", "35/3"),
        "Doubt does not answer in the place of each question",
    )


def test_doubt_gives_reason_code_of_stub() -> None:
    assert_that(
        Doubt().verdicts(_questions(1))[0].reason().code(),
        equal_to("eval.semantic"),
        "Doubt does not give the reason code of the semantic stub",
    )


def test_doubt_counts_each_batch_as_one_call() -> None:
    judge = Doubt()
    batches = random.randint(1, 7)
    for _ in range(batches):
        judge.verdicts(_questions(random.randint(1, 5)))
    assert_that(judge.count(), equal_to(batches), "Doubt does not count each batch as one call")


def test_doubt_counts_no_call_before_any_question() -> None:
    assert_that(Doubt().count(), equal_to(0), "Doubt does not start with zero calls")
