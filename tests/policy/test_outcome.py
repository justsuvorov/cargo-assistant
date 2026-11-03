import random
import string

from hamcrest import assert_that, equal_to

from app.policy.outcome import Result


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_keeps_items_and_problems_apart() -> None:
    item, problem = _word(), _word()
    result = Result((item,), (problem,))
    assert_that(
        (result.items(), result.problems()),
        equal_to(((item,), (problem,))),
        "Result does not keep found items apart from problems",
    )
