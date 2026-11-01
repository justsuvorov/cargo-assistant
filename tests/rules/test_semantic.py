import uuid

from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.clause import Absent
from app.domain.place import Spot
from app.rules.semantic import Asking, Joint
from tests.rules.fakes import Paper, Profile, Text


def test_joint_clause_leaves_out_absent_parts() -> None:
    assert_that(
        Joint((Text("ГП п. 5", "объект"), Absent("exclusions_cargo"))).reference(),
        equal_to("ГП п. 5"),
        "Joint does not leave out an absent clause",
    )


def test_joint_clause_joins_texts_in_order() -> None:
    assert_that(
        Joint((Text("ГП п. 5", "объект"), Text("ГП п. 4", "исключения"))).text(),
        equal_to("объект\nисключения"),
        "Joint does not join the texts of its clauses in order",
    )


def test_question_holds_the_whole_value_and_the_exclusions() -> None:
    value = f"Продукты, {uuid.uuid4().hex}"
    question = (
        Asking(("exclusions_cargo",), "правило")
        .outcome(
            Fields().field("cargo", (value,)),
            Text("ГП п. 5", "объект"),
            Paper("13", "psg", ({"cargo": (value,)},)).shipments()[0],
            Profile({"exclusions_cargo": Text("ГП п. 4", "мех")}),
        )
        .questions(Spot("13", "cargo"))[0]
    )
    assert_that(
        (question.value(), question.clause().reference(), question.rule()),
        equal_to((value, "ГП п. 5; ГП п. 4", "правило")),
        "Asking does not ask the whole value against the clause and its exclusions",
    )
