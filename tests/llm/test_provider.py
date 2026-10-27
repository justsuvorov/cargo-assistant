import contextlib
import random

from hamcrest import assert_that, equal_to, raises

from app.llm.deadline import Countdown, Rhythm
from app.llm.errors import UnavailableError
from app.llm.messages import User
from app.llm.provider import Insistent
from app.llm.schema.shape import Shape
from tests.llm.answers import Point
from tests.llm.stub import Quiet, Scripted


def test_asks_again_after_empty_answer() -> None:
    answer = f'{{"n": {random.randint(1, 99)}}}'
    assert_that(
        Insistent(Scripted(["", answer]), Rhythm(3, 0.01), Quiet())
        .reply((User("q"),), Shape(Point), Countdown(5.0))
        .text(),
        equal_to(answer),
        "Empty answer is not asked again",
    )


def test_treats_answer_of_bare_reasoning_as_empty() -> None:
    backend = Scripted(["<think>думаю", '{"n": 1}'])
    Insistent(backend, Rhythm(3, 0.01), Quiet()).reply((User("q"),), Shape(Point), Countdown(5.0))
    assert_that(backend.calls, equal_to(2), "Answer of unclosed reasoning is not asked again")


def test_fails_after_empty_answers_run_out() -> None:
    insistent = Insistent(Scripted([""]), Rhythm(3, 0.01), Quiet())
    assert_that(
        lambda: insistent.reply((User("q"),), Shape(Point), Countdown(5.0)),
        raises(UnavailableError),
        "Endless empty answers do not end in an unavailable model error",
    )


def test_makes_no_more_requests_than_attempts() -> None:
    attempts = random.randint(1, 4)
    backend = Scripted([""])
    with contextlib.suppress(UnavailableError):
        Insistent(backend, Rhythm(attempts, 0.0), Quiet()).reply(
            (User("q"),), Shape(Point), Countdown(5.0)
        )
    assert_that(
        backend.calls, equal_to(attempts), "Empty answers do not stop at the allowed attempts"
    )
