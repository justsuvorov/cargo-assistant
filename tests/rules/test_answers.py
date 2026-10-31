import uuid

from hamcrest import assert_that, equal_to

from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Inquiry
from app.domain.status import Mismatch
from app.domain.verdict import Ruling
from app.rules.answers import Distinct, Replies
from tests.rules.fakes import Text


def test_distinct_keeps_one_question_per_value_and_clause() -> None:
    value = uuid.uuid4().hex
    clause = Text("ГП п. 5", "объект")
    assert_that(
        tuple(
            question.place().shipment()
            for question in Distinct(
                (
                    Inquiry(Spot("7/1", "cargo"), value, clause, "правило"),
                    Inquiry(Spot("7/2", "cargo"), "другое", clause, "правило"),
                    Inquiry(Spot("7/3", "cargo"), value, clause, "правило"),
                )
            ).questions()
        ),
        equal_to(("7/1", "7/2")),
        "Distinct does not keep the first question of each value in order",
    )


def test_twin_question_gets_the_answer_of_the_first() -> None:
    clause = Text("ГП п. 9", "территория")
    first = Inquiry(Spot("8/1", "departure"), "г. Энск", clause, "")
    assert_that(
        Replies(
            (first,),
            (Ruling(first.place(), Mismatch(), Cause("departure.x", "llm"), Note("", "")),),
        )
        .reply(Inquiry(Spot("8/5", "departure"), "г. Энск", clause, ""))[0]
        .status()
        .key(),
        equal_to("mismatch"),
        "Replies does not give a twin question the answer of the first one",
    )


def test_question_without_answer_gets_none() -> None:
    clause = Text("ГП п. 9", "территория")
    assert_that(
        Replies((Inquiry(Spot("8/1", "departure"), "г. Энск", clause, ""),), ()).reply(
            Inquiry(Spot("8/1", "departure"), "г. Энск", clause, "")
        ),
        equal_to(()),
        "Replies does not leave an unanswered question without verdicts",
    )
