import random
import string
from datetime import date

from hamcrest import assert_that, equal_to

from app.policy.assembled import Assembled, Listed
from app.policy.papers import Agreement, Opened


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_gives_back_every_part_it_was_made_of() -> None:
    policy = Opened(_word(), _word())
    amendment = Agreement(Opened(_word(), _word()), 1, date(2025, 1, 1), ())
    condition, carrier, problem = _word(), _word(), _word()
    package = Assembled(policy, (amendment,), Listed((condition,), (carrier,)), (problem,))
    assert_that(
        (
            package.policy(),
            package.amendments(),
            package.conditions(),
            package.carriers(),
            package.problems(),
        ),
        equal_to((policy, (amendment,), (condition,), (carrier,), (problem,))),
        "Assembled does not give back the parts it was made of",
    )
