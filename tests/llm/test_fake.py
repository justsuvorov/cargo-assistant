import random

from hamcrest import assert_that, equal_to, raises

from app.llm.errors import MalformedError, MisconfiguredError
from app.llm.fake import FakeModel
from app.llm.messages import User
from tests.llm.answers import Match


def test_answers_purpose_with_recorded_json() -> None:
    same = random.choice([True, False])
    assert_that(
        FakeModel({"cargo": f'{{"same": {str(same).lower()}}}'})
        .answer("cargo", (User("q"),), Match)
        .same,
        equal_to(same),
        "Recorded answer is not given for its purpose",
    )


def test_counts_every_call() -> None:
    calls = random.randint(1, 9)
    model = FakeModel({"cargo": '{"same": true}', "route": '{"same": false}'})
    for index in range(calls):
        model.answer(("cargo", "route")[index % 2], (User("q"),), Match)
    assert_that(model.count(), equal_to(calls), "Calls are not counted")


def test_refuses_purpose_without_recorded_answer() -> None:
    model = FakeModel({})
    assert_that(
        lambda: model.answer("cargo", (User("q"),), Match),
        raises(MisconfiguredError),
        "Purpose without a recorded answer does not raise a configuration error",
    )


def test_refuses_recorded_answer_that_breaks_schema() -> None:
    model = FakeModel({"cargo": '{"same": "может быть"}'})
    assert_that(
        lambda: model.answer("cargo", (User("q"),), Match),
        raises(MalformedError),
        "Recorded answer that breaks the schema does not raise a malformed answer error",
    )
